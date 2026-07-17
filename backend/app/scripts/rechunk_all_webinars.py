"""
Re-chunk all webinar videos with 1-minute clip targets.

Deletes existing chunks for every webinar, re-chunks transcript segments
at 130 words (~1 minute), re-contextualizes with Claude, and re-embeds.
Article content is left untouched.

Usage:
    python -m app.scripts.rechunk_all_webinars [--dry-run] [--video-id UUID]

Options:
    --dry-run   Show what would be done without writing to the database
    --video-id  Process a single video by ID (for testing)
"""
import argparse
import asyncio
from datetime import datetime

from sqlalchemy import delete, select

from app.db.database import AsyncSessionLocal
from app.db.models import Chunk, TranscriptSegment, Video
from app.services import claude_service, embedding_service
from app.services.chunking_service import chunk_segments

TARGET_WORDS = 130
OVERLAP_WORDS = 20


def format_time(seconds: float) -> str:
    total = int(seconds)
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


async def rechunk_video(video: Video, db, dry_run: bool) -> dict:
    """
    Re-chunk a single video. Returns a result dict with counts.
    """
    title = video.title
    webinar_date = str(video.webinar_date) if video.webinar_date else "Unknown"

    print(f"\n{'─' * 60}")
    print(f"Video: {title}")
    print(f"  ID:   {video.id}")
    print(f"  Date: {webinar_date}")

    # Load transcript segments
    seg_result = await db.execute(
        select(TranscriptSegment)
        .where(TranscriptSegment.video_id == video.id)
        .order_by(TranscriptSegment.start_time_seconds)
    )
    segments = seg_result.scalars().all()

    if not segments:
        print("  ⚠ No transcript segments found — skipping")
        return {"skipped": True}

    print(f"  Segments: {len(segments)}")

    seg_dicts = [
        {
            "start_time_seconds": s.start_time_seconds,
            "end_time_seconds": s.end_time_seconds,
            "speaker": s.speaker,
            "text": s.text,
        }
        for s in segments
    ]

    # Re-chunk at 1-minute target
    chunk_dicts = chunk_segments(seg_dicts, target_words=TARGET_WORDS, overlap_words=OVERLAP_WORDS)
    print(f"  New chunks: {len(chunk_dicts)} (was using 600-word target)")

    if dry_run:
        print("  [DRY RUN] Would delete old chunks and insert new ones")
        return {"dry_run": True, "new_chunk_count": len(chunk_dicts)}

    # Delete existing chunks
    await db.execute(delete(Chunk).where(Chunk.video_id == video.id))
    await db.flush()
    print("  ✓ Deleted old chunks")

    # Insert new chunks (contextual_text placeholder until step 2)
    new_chunks = []
    for chunk_data in chunk_dicts:
        chunk = Chunk(
            video_id=video.id,
            start_time_seconds=chunk_data["start_time_seconds"],
            end_time_seconds=chunk_data["end_time_seconds"],
            raw_text=chunk_data["raw_text"],
            contextual_text=chunk_data["raw_text"],  # Updated in contextualization step
            speaker_names=chunk_data["speaker_names"],
            chunk_index=chunk_data["chunk_index"],
            word_count=chunk_data["word_count"],
            summary=None,
            topic_tags=None,
            questions_answered=None,
            embedding=None,
        )
        db.add(chunk)
        new_chunks.append(chunk)

    await db.flush()
    print(f"  ✓ Inserted {len(new_chunks)} new chunks")

    # Contextualize each chunk with Claude
    print(f"  Contextualizing {len(new_chunks)} chunks...")
    for i, chunk in enumerate(new_chunks, 1):
        print(f"    [{i}/{len(new_chunks)}] {format_time(chunk.start_time_seconds)}–{format_time(chunk.end_time_seconds)}...", end=" ")
        try:
            result = await claude_service.contextualize_chunk(
                video_title=title,
                webinar_date=webinar_date,
                speaker_names=chunk.speaker_names or [],
                start_time=format_time(chunk.start_time_seconds),
                end_time=format_time(chunk.end_time_seconds),
                raw_chunk_text=chunk.raw_text,
            )
            chunk.contextual_text = result["contextual_text"]
            chunk.summary = result["summary"]
            chunk.topic_tags = result["topic_tags"]
            chunk.questions_answered = result["questions_this_answers"]
            print("✓")
        except Exception as e:
            print(f"✗ {e}")
            raise

    await db.flush()

    # Embed each chunk
    print(f"  Embedding {len(new_chunks)} chunks...")
    for i, chunk in enumerate(new_chunks, 1):
        print(f"    [{i}/{len(new_chunks)}]...", end=" ")
        try:
            speaker_str = ", ".join(chunk.speaker_names) if chunk.speaker_names else "Unknown"
            tags_str = ", ".join(chunk.topic_tags) if chunk.topic_tags else ""
            embedding_input = (
                f"{title} | "
                f"Date: {webinar_date} | "
                f"Speakers: {speaker_str} | "
                f"Summary: {chunk.summary or ''} | "
                f"Topics: {tags_str} | "
                f"{chunk.contextual_text} | "
                f"Content type: webinar"
            )
            chunk.embedding = await embedding_service.embed_text(embedding_input)
            print("✓")
        except Exception as e:
            print(f"✗ {e}")
            raise

    await db.flush()

    # Mark video as embedded
    video.status = "embedded"
    await db.commit()

    print(f"  ✓ Done — {len(new_chunks)} chunks committed")
    return {"new_chunk_count": len(new_chunks)}


async def rechunk_all_webinars(dry_run: bool = False, video_id: str | None = None):
    start_time = datetime.now()

    print("=" * 60)
    print("RE-CHUNK ALL WEBINARS — 1-MINUTE CLIPS")
    print("=" * 60)
    print(f"Target:   {TARGET_WORDS} words per chunk (~1 min at 130 wpm)")
    print(f"Overlap:  {OVERLAP_WORDS} words")
    print(f"Dry run:  {dry_run}")
    print(f"Started:  {start_time.strftime('%Y-%m-%d %H:%M:%S')}")

    async with AsyncSessionLocal() as db:
        query = select(Video).where(Video.content_type == "webinar")
        if video_id:
            from uuid import UUID
            query = query.where(Video.id == UUID(video_id))

        result = await db.execute(query)
        videos = result.scalars().all()

        print(f"\nFound {len(videos)} webinar(s) to process\n")

        if not videos:
            print("Nothing to do.")
            return

        total_new_chunks = 0
        skipped = 0
        errors = 0

        for video in videos:
            try:
                outcome = await rechunk_video(video, db, dry_run)
                if outcome.get("skipped"):
                    skipped += 1
                else:
                    total_new_chunks += outcome.get("new_chunk_count", 0)
            except Exception as e:
                errors += 1
                print(f"  ✗ ERROR processing {video.title}: {e}")
                await db.rollback()
                print("  Rolled back. Continuing with next video...")

    elapsed = datetime.now() - start_time
    print(f"\n{'=' * 60}")
    print("COMPLETE")
    print(f"  Videos processed: {len(videos) - skipped - errors}")
    print(f"  Skipped (no segments): {skipped}")
    print(f"  Errors: {errors}")
    print(f"  Total new chunks: {total_new_chunks}")
    print(f"  Elapsed: {elapsed}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Re-chunk all webinars at 1-minute clip target")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without writing")
    parser.add_argument("--video-id", type=str, default=None, help="Process only this video UUID")
    args = parser.parse_args()

    asyncio.run(rechunk_all_webinars(dry_run=args.dry_run, video_id=args.video_id))
