"""
Ingestion service - orchestrates the webinar ingestion pipeline.

Phase 2: Steps 1-3 only (no Claude contextualization, no embeddings)
Phase 3: Steps 1-4 (adds Claude contextualization)
Phase 4: Steps 1-5 (adds embeddings)
"""
import json
from datetime import datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Chunk, TranscriptSegment, Video
from app.errors import IngestionError
from app.services.chunking_service import chunk_segments
from app.services import claude_service
from app.services import embedding_service


async def ingest_webinar(
    title: str,
    description: str | None,
    webinar_date: str | None,  # ISO format: "2026-04-12"
    speakers: list[str],
    video_url: str | None,
    transcript_path: str,
    db_session: AsyncSession,
) -> tuple[UUID, int]:
    """
    Ingest a webinar into the database.

    Phase 4: Steps 1-5
    - Step 1: Insert video record
    - Step 2: Insert transcript segments
    - Step 3: Chunk segments and insert chunks
    - Step 4: Claude contextualization (enrich with summary, topic_tags, questions_answered)
    - Step 5: Generate embeddings and store vectors

    Args:
        title: Video title
        description: Video description
        webinar_date: Date of webinar (ISO format or None)
        speakers: List of speaker names
        video_url: URL to video file
        transcript_path: Path to transcript JSON file
        db_session: Database session

    Returns:
        Tuple of (video_id, chunk_count)

    Raises:
        IngestionError: If ingestion fails
    """
    try:
        # Step 1: Insert video record
        print(f"\n[Step 1] Creating video record: {title}")

        # Parse webinar_date if provided
        parsed_date = None
        if webinar_date:
            try:
                parsed_date = datetime.fromisoformat(webinar_date).date()
            except ValueError:
                print(f"Warning: Invalid date format '{webinar_date}', setting to None")

        video = Video(
            title=title,
            description=description,
            webinar_date=parsed_date,
            speakers=speakers,
            video_url=video_url,
            status="processing",  # Will update to 'embedded' after step 5
        )
        db_session.add(video)
        await db_session.flush()  # Get video.id without committing

        video_id = video.id
        print(f"✓ Video created: {video_id}")

        # Step 2: Load and insert transcript segments
        print(f"\n[Step 2] Loading transcript from: {transcript_path}")

        transcript_file = Path(transcript_path)
        if not transcript_file.exists():
            raise IngestionError(f"Transcript file not found: {transcript_path}")

        with open(transcript_file) as f:
            transcript_data = json.load(f)

        if not isinstance(transcript_data, list):
            raise IngestionError("Transcript must be a JSON array")

        print(f"✓ Loaded {len(transcript_data)} segments")

        # Insert all segments
        segments = []
        for seg_data in transcript_data:
            segment = TranscriptSegment(
                video_id=video_id,
                start_time_seconds=seg_data["start_time_seconds"],
                end_time_seconds=seg_data["end_time_seconds"],
                speaker=seg_data.get("speaker"),
                text=seg_data["text"],
            )
            segments.append(segment)
            db_session.add(segment)

        await db_session.flush()
        print(f"✓ Inserted {len(segments)} transcript segments")

        # Step 3: Chunk the segments
        print(f"\n[Step 3] Chunking segments (target: 130 words ~1 min, overlap: 20)")

        chunk_dicts = chunk_segments(transcript_data, target_words=130, overlap_words=20)
        print(f"✓ Created {len(chunk_dicts)} chunks")

        # Insert chunks
        # Phase 4: contextual_text updated in step 4, embedding updated in step 5
        chunks_to_contextualize = []
        for chunk_data in chunk_dicts:
            chunk = Chunk(
                video_id=video_id,
                start_time_seconds=chunk_data["start_time_seconds"],
                end_time_seconds=chunk_data["end_time_seconds"],
                raw_text=chunk_data["raw_text"],
                contextual_text=chunk_data["raw_text"],  # Temporary, updated in step 4
                speaker_names=chunk_data["speaker_names"],
                chunk_index=chunk_data["chunk_index"],
                word_count=chunk_data["word_count"],
                # Enriched fields set in step 4
                summary=None,
                topic_tags=None,
                questions_answered=None,
                # Embedding set in step 5
                embedding=None,
            )
            db_session.add(chunk)
            chunks_to_contextualize.append(chunk)

        await db_session.flush()
        print(f"✓ Inserted {len(chunk_dicts)} chunks")

        # Step 4: Claude Contextualization (Phase 3)
        print(f"\n[Step 4] Contextualizing chunks with Claude")

        def format_time(seconds: float) -> str:
            """Format seconds as HH:MM:SS."""
            total = int(seconds)
            h = total // 3600
            m = (total % 3600) // 60
            s = total % 60
            return f"{h:02d}:{m:02d}:{s:02d}"

        for i, chunk in enumerate(chunks_to_contextualize, 1):
            print(f"  Contextualizing chunk {i}/{len(chunks_to_contextualize)}...", end=" ")

            # Call Claude to enrich the chunk
            try:
                result = await claude_service.contextualize_chunk(
                    video_title=title,
                    webinar_date=webinar_date or "Unknown",
                    speaker_names=chunk.speaker_names or [],
                    start_time=format_time(chunk.start_time_seconds),
                    end_time=format_time(chunk.end_time_seconds),
                    raw_chunk_text=chunk.raw_text,
                )

                # Update chunk with Claude's enrichments
                chunk.contextual_text = result["contextual_text"]
                chunk.summary = result["summary"]
                chunk.topic_tags = result["topic_tags"]
                chunk.questions_answered = result["questions_this_answers"]

                print("✓")

            except Exception as e:
                print(f"✗ Failed: {e}")
                raise

        await db_session.flush()
        print(f"✓ Contextualized {len(chunks_to_contextualize)} chunks")

        # Step 5: Generate embeddings (Phase 4)
        print(f"\n[Step 5] Generating embeddings")

        for i, chunk in enumerate(chunks_to_contextualize, 1):
            print(f"  Embedding chunk {i}/{len(chunks_to_contextualize)}...", end=" ")

            # Build embedding input string per spec:
            # {video_title} | {webinar_date} | {speaker_names} | {summary} | {topic_tags} | {contextual_text}
            speaker_str = ", ".join(chunk.speaker_names) if chunk.speaker_names else "Unknown"
            tags_str = ", ".join(chunk.topic_tags) if chunk.topic_tags else ""

            embedding_input = (
                f"{title} | "
                f"Date: {webinar_date or 'Unknown'} | "
                f"Speakers: {speaker_str} | "
                f"Summary: {chunk.summary or ''} | "
                f"Topics: {tags_str} | "
                f"{chunk.contextual_text} | "
                f"Content type: webinar"
            )

            try:
                embedding_vector = await embedding_service.embed_text(embedding_input)
                chunk.embedding = embedding_vector
                print("✓")

            except Exception as e:
                print(f"✗ Failed: {e}")
                raise

        await db_session.flush()
        print(f"✓ Generated embeddings for {len(chunks_to_contextualize)} chunks")

        # Update video status to 'embedded'
        video.status = "embedded"
        await db_session.flush()

        # Commit the transaction
        await db_session.commit()

        print(f"\n✓ Ingestion complete!")
        print(f"  Video ID: {video_id}")
        print(f"  Segments: {len(segments)}")
        print(f"  Chunks: {len(chunk_dicts)}")

        return (video_id, len(chunk_dicts))

    except Exception as e:
        await db_session.rollback()
        raise IngestionError(f"Ingestion failed: {e}") from e
