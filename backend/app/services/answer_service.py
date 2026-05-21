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
                "video_title": chunk.video_title,
                "time_range": format_time_range(chunk.start_time_seconds, chunk.end_time_seconds),
                "speakers": chunk.speaker_names or [],
                "summary": chunk.summary or "",
                "topic_tags": chunk.topic_tags or [],
                "contextual_text": chunk.contextual_text,
            }
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

            # Build video URL with timestamp
            video_url = chunk.video_title  # Placeholder - actual URL should come from video record
            if settings.VIDEO_BASE_URL:
                video_url = f"{settings.VIDEO_BASE_URL}/{chunk.video_id}"
            video_url_with_timestamp = f"{video_url}?t={int(chunk.start_time_seconds)}"

            source_card = SourceCard(
                chunk_id=chunk.chunk_id,
                video_id=chunk.video_id,
                video_title=chunk.video_title,
                video_url=video_url_with_timestamp,
                start_time_seconds=chunk.start_time_seconds,
                end_time_seconds=chunk.end_time_seconds,
                display_time=format_time_range(chunk.start_time_seconds, chunk.end_time_seconds),
                excerpt=chunk.summary or chunk.contextual_text[:200],
                speaker_names=chunk.speaker_names or [],
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
