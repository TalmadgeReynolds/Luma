"""
Answer service - generates answers from retrieved chunks.

Orchestrates Claude answer generation with citation validation.
"""
from uuid import UUID

from app.config import get_settings
from app.db.schemas import AskResponse, SourceCard
from app.errors import AnswerServiceError
from app.services import claude_service
from app.services.retrieval_service import RetrievedChunk

settings = get_settings()


def format_time(seconds: float) -> str:
    """Format seconds as HH:MM:SS."""
    total = int(seconds)
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def format_time_range(start_seconds: float, end_seconds: float) -> str:
    """Format time range as HH:MM:SS–HH:MM:SS."""
    return f"{format_time(start_seconds)}–{format_time(end_seconds)}"


async def generate_answer(
    question: str,
    retrieved_chunks: list[RetrievedChunk],
) -> AskResponse:
    """
    Generate answer from retrieved chunks.

    Flow:
    1. Guard: if no chunks, return not_enough_evidence immediately
    2. Format chunks for Claude
    3. Call Claude with answer_from_chunks prompt
    4. Validate: every chunk_id in response exists in input
    5. Build SourceCard objects with proper formatting
    6. Return AskResponse

    Args:
        question: User question
        retrieved_chunks: List of RetrievedChunk from retrieval service

    Returns:
        AskResponse with answer and sources

    Raises:
        AnswerServiceError: If answer generation fails
    """
    try:
        # Step 1: Guard against empty chunks
        if not retrieved_chunks:
            return AskResponse(
                answer="",
                sources=[],
                suggested_questions=[],
                confidence="low",
                not_enough_evidence=True,
            )

        # Step 2: Format chunks for Claude
        formatted_chunks = []
        chunk_map = {}  # chunk_id -> RetrievedChunk for validation

        for chunk in retrieved_chunks:
            chunk_dict = {
                "chunk_id": str(chunk.chunk_id),
                "content_type": chunk.content_type,
                "video_title": chunk.video_title,
                "summary": chunk.summary or "",
                "topic_tags": chunk.topic_tags or [],
                "contextual_text": chunk.contextual_text,
            }

            # Add content-type-specific fields
            if chunk.content_type == 'webinar':
                chunk_dict["time_range"] = format_time_range(chunk.start_time_seconds, chunk.end_time_seconds)
                chunk_dict["speakers"] = chunk.speaker_names or []
            else:  # article
                chunk_dict["section_heading"] = chunk.section_heading or "N/A"

            formatted_chunks.append(chunk_dict)
            chunk_map[chunk.chunk_id] = chunk

        # Step 3: Call Claude
        print(f"[Answer] Calling Claude with {len(formatted_chunks)} chunks...")
        claude_response = await claude_service.answer_from_chunks(
            user_question=question,
            retrieved_chunks=formatted_chunks,
        )

        answer = claude_response["answer"]
        # The prompt returns sources as objects with a chunk_id field; handle both
        raw_sources = claude_response["sources"]
        source_chunk_ids = []
        for s in raw_sources:
            cid = s["chunk_id"] if isinstance(s, dict) else s
            source_chunk_ids.append(UUID(cid))
        suggested_questions = claude_response["suggested_questions"]
        confidence = claude_response["confidence"]
        not_enough_evidence = claude_response.get("not_enough_evidence", False)

        print(f"[Answer] Claude response: {len(answer)} chars, {len(source_chunk_ids)} sources")

        # Step 4: Validate chunk_ids
        invalid_chunk_ids = [cid for cid in source_chunk_ids if cid not in chunk_map]
        if invalid_chunk_ids:
            print(f"[Answer] Warning: Claude referenced invalid chunk IDs: {invalid_chunk_ids}")
            # Filter out invalid IDs
            source_chunk_ids = [cid for cid in source_chunk_ids if cid in chunk_map]

        # Step 5: Build SourceCard objects
        sources = []
        for chunk_id in source_chunk_ids:
            chunk = chunk_map[chunk_id]

            # Build source URL based on content type
            if chunk.content_type == 'webinar':
                if chunk.video_url and chunk.video_url.startswith('https://'):
                    source_url = chunk.video_url
                else:
                    source_url = f"{settings.VIDEO_BASE_URL}/{chunk.video_id}"
                display_time = format_time_range(chunk.start_time_seconds, chunk.end_time_seconds)
            else:
                # For articles: use direct article URL (no timestamp)
                source_url = chunk.source_url or f"Article: {chunk.video_title}"
                display_time = None  # No timestamps for articles

            source_card = SourceCard(
                chunk_id=chunk.chunk_id,
                video_id=chunk.video_id,
                content_type=chunk.content_type,
                title=chunk.video_title,
                source_url=source_url,
                start_time_seconds=chunk.start_time_seconds if chunk.content_type == 'webinar' else None,
                end_time_seconds=chunk.end_time_seconds if chunk.content_type == 'webinar' else None,
                display_time=display_time,
                speaker_names=chunk.speaker_names or [],
                section_heading=chunk.section_heading,
                excerpt=chunk.contextual_text,
            )
            sources.append(source_card)

        # Step 6: Return response
        return AskResponse(
            answer=answer,
            sources=sources,
            suggested_questions=suggested_questions[:3],  # Limit to 3
            confidence=confidence,
            not_enough_evidence=not_enough_evidence,
        )

    except Exception as e:
        raise AnswerServiceError(f"Answer generation failed: {e}") from e


async def generate_answer_stream(
    question: str,
    retrieved_chunks: list[RetrievedChunk],
):
    """
    Stream answer generation, yielding token deltas then a final AskResponse.

    Yields:
        {"type": "token", "text": "..."} for each text delta from Claude
        {"type": "final", "result": AskResponse} once generation is complete

    Raises:
        AnswerServiceError: If generation fails
    """
    try:
        # Guard: no chunks
        if not retrieved_chunks:
            yield {
                "type": "final",
                "result": AskResponse(
                    answer="",
                    sources=[],
                    suggested_questions=[],
                    confidence="low",
                    not_enough_evidence=True,
                ),
            }
            return

        # Format chunks for Claude (identical to generate_answer)
        formatted_chunks = []
        chunk_map = {}

        for chunk in retrieved_chunks:
            chunk_dict = {
                "chunk_id": str(chunk.chunk_id),
                "content_type": chunk.content_type,
                "video_title": chunk.video_title,
                "summary": chunk.summary or "",
                "topic_tags": chunk.topic_tags or [],
                "contextual_text": chunk.contextual_text,
            }
            if chunk.content_type == 'webinar':
                chunk_dict["time_range"] = format_time_range(chunk.start_time_seconds, chunk.end_time_seconds)
                chunk_dict["speakers"] = chunk.speaker_names or []
            else:
                chunk_dict["section_heading"] = chunk.section_heading or "N/A"

            formatted_chunks.append(chunk_dict)
            chunk_map[chunk.chunk_id] = chunk

        # Stream tokens from Claude
        print(f"[Answer] Streaming Claude response with {len(formatted_chunks)} chunks...")
        parsed = None
        async for event in claude_service.stream_answer_from_chunks(
            user_question=question,
            retrieved_chunks=formatted_chunks,
        ):
            if event["type"] == "delta":
                yield {"type": "token", "text": event["text"]}
            elif event["type"] == "done":
                parsed = event["parsed"]

        if parsed is None:
            raise AnswerServiceError("Claude stream ended without a parsed result")

        answer = parsed["answer"]
        raw_sources = parsed["sources"]
        source_chunk_ids = []
        for s in raw_sources:
            cid = s["chunk_id"] if isinstance(s, dict) else s
            source_chunk_ids.append(UUID(cid))
        suggested_questions = parsed["suggested_questions"]
        confidence = parsed["confidence"]
        not_enough_evidence = parsed.get("not_enough_evidence", False)

        print(f"[Answer] Stream complete: {len(answer)} chars, {len(source_chunk_ids)} sources")

        # Validate chunk_ids
        invalid_chunk_ids = [cid for cid in source_chunk_ids if cid not in chunk_map]
        if invalid_chunk_ids:
            print(f"[Answer] Warning: Claude referenced invalid chunk IDs: {invalid_chunk_ids}")
            source_chunk_ids = [cid for cid in source_chunk_ids if cid in chunk_map]

        # Build SourceCard objects (identical to generate_answer)
        sources = []
        for chunk_id in source_chunk_ids:
            chunk = chunk_map[chunk_id]
            if chunk.content_type == 'webinar':
                if chunk.video_url and chunk.video_url.startswith('https://'):
                    source_url = chunk.video_url
                else:
                    source_url = f"{settings.VIDEO_BASE_URL}/{chunk.video_id}"
                display_time = format_time_range(chunk.start_time_seconds, chunk.end_time_seconds)
            else:
                source_url = chunk.source_url or f"Article: {chunk.video_title}"
                display_time = None

            sources.append(SourceCard(
                chunk_id=chunk.chunk_id,
                video_id=chunk.video_id,
                content_type=chunk.content_type,
                title=chunk.video_title,
                source_url=source_url,
                start_time_seconds=chunk.start_time_seconds if chunk.content_type == 'webinar' else None,
                end_time_seconds=chunk.end_time_seconds if chunk.content_type == 'webinar' else None,
                display_time=display_time,
                speaker_names=chunk.speaker_names or [],
                section_heading=chunk.section_heading,
                excerpt=chunk.contextual_text,
            ))

        yield {
            "type": "final",
            "result": AskResponse(
                answer=answer,
                sources=sources,
                suggested_questions=suggested_questions[:3],
                confidence=confidence,
                not_enough_evidence=not_enough_evidence,
            ),
        }

    except AnswerServiceError:
        raise
    except Exception as e:
        raise AnswerServiceError(f"Answer stream generation failed: {e}") from e
