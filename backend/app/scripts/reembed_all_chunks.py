"""
Re-embed all chunks with updated embedding format.

This script regenerates embeddings for all existing chunks using the new
neutralized embedding format (content_type moved to end).

Usage:
    python -m app.scripts.reembed_all_chunks [--dry-run] [--batch-size 100]

Options:
    --dry-run: Show what would be done without making changes
    --batch-size: Number of chunks to process per commit (default: 100)
"""
import argparse
import asyncio
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.db.database import AsyncSessionLocal
from app.db.models import Chunk, Video
from app.services import embedding_service


async def reembed_all_chunks(dry_run: bool = False, batch_size: int = 100):
    """
    Re-embed all chunks with the new embedding format.

    Args:
        dry_run: If True, show what would be done without making changes
        batch_size: Number of chunks to commit at once
    """
    start_time = datetime.now()

    print("=" * 80)
    print("RE-EMBEDDING ALL CHUNKS")
    print("=" * 80)
    print(f"Dry run: {dry_run}")
    print(f"Batch size: {batch_size}")
    print(f"Started at: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    async with AsyncSessionLocal() as db:
        # Fetch all chunks with their video metadata
        print("Fetching chunks from database...")

        result = await db.execute(
            select(Chunk)
            .options(joinedload(Chunk.video))
            .order_by(Chunk.id)
        )
        chunks = result.scalars().all()

        total_chunks = len(chunks)
        print(f"Found {total_chunks} chunks to re-embed\n")

        if total_chunks == 0:
            print("No chunks to process. Exiting.")
            return

        # Process chunks
        processed = 0
        errors = 0
        error_log = []

        for i, chunk in enumerate(chunks, 1):
            try:
                video = chunk.video

                # Build new embedding input based on content type
                if video.content_type == 'webinar':
                    # Webinar format
                    speaker_str = ", ".join(chunk.speaker_names) if chunk.speaker_names else "Unknown"
                    tags_str = ", ".join(chunk.topic_tags) if chunk.topic_tags else ""

                    embedding_input = (
                        f"{video.title} | "
                        f"Date: {video.webinar_date or 'Unknown'} | "
                        f"Speakers: {speaker_str} | "
                        f"Summary: {chunk.summary or ''} | "
                        f"Topics: {tags_str} | "
                        f"{chunk.contextual_text} | "
                        f"Content type: webinar"
                    )
                else:  # article
                    # Article format
                    section = chunk.section_heading or ""
                    tags_str = ", ".join(chunk.topic_tags) if chunk.topic_tags else ""

                    embedding_input = (
                        f"{video.title} | "
                        f"Date: {video.webinar_date or 'Unknown'} | "
                        f"Section: {section} | "
                        f"Summary: {chunk.summary or ''} | "
                        f"Topics: {tags_str} | "
                        f"{chunk.contextual_text} | "
                        f"Content type: article"
                    )

                # Show progress
                progress_percent = (i / total_chunks) * 100
                content_type_label = video.content_type.upper()
                print(f"[{i}/{total_chunks}] ({progress_percent:.1f}%) Re-embedding {content_type_label} chunk {chunk.id}...", end=" ")

                if not dry_run:
                    # Generate new embedding
                    embedding_vector = await embedding_service.embed_text(embedding_input)

                    # Update chunk
                    chunk.embedding = embedding_vector

                    # Commit in batches
                    if i % batch_size == 0:
                        await db.commit()
                        print(f"✓ (batch committed)")
                    else:
                        print("✓")
                else:
                    print("✓ (dry run)")

                processed += 1

            except Exception as e:
                errors += 1
                error_msg = f"Chunk {chunk.id}: {str(e)}"
                error_log.append(error_msg)
                print(f"✗ ERROR: {str(e)}")
                continue

        # Final commit for remaining chunks
        if not dry_run and processed % batch_size != 0:
            await db.commit()
            print("\n✓ Final batch committed")

        # Print summary
        end_time = datetime.now()
        duration = end_time - start_time

        print()
        print("=" * 80)
        print("SUMMARY")
        print("=" * 80)
        print(f"Total chunks: {total_chunks}")
        print(f"Successfully processed: {processed}")
        print(f"Errors: {errors}")
        print(f"Duration: {duration}")
        print(f"Avg time per chunk: {duration.total_seconds() / total_chunks:.2f}s")

        if errors > 0:
            print(f"\nERROR LOG ({errors} errors):")
            for error_msg in error_log:
                print(f"  - {error_msg}")

        if dry_run:
            print("\nDRY RUN COMPLETE - No changes were made to the database.")
        else:
            print(f"\n✓✓✓ Re-embedding complete! All {processed} chunks updated.")


def main():
    parser = argparse.ArgumentParser(
        description="Re-embed all chunks with updated embedding format"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Number of chunks to commit per batch (default: 100)"
    )

    args = parser.parse_args()

    asyncio.run(reembed_all_chunks(
        dry_run=args.dry_run,
        batch_size=args.batch_size
    ))


if __name__ == "__main__":
    main()
