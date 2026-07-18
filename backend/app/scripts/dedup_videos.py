"""
Remove duplicate video records from the database.

Groups videos by (title, webinar_date) and keeps the one with the most
chunks (likely already rechunked). Deletes the rest; cascade removes
their segments and chunks automatically.

Usage:
    python -m app.scripts.dedup_videos            # dry run (default)
    python -m app.scripts.dedup_videos --execute  # actually delete
"""
import argparse
import asyncio

from sqlalchemy import func, select

from app.db.database import AsyncSessionLocal
from app.db.models import Chunk, Video


async def dedup_videos(execute: bool = False):
    async with AsyncSessionLocal() as db:
        # Load all webinar videos with their chunk counts
        result = await db.execute(
            select(Video, func.count(Chunk.id).label("chunk_count"))
            .outerjoin(Chunk, Chunk.video_id == Video.id)
            .where(Video.content_type == "webinar")
            .group_by(Video.id)
            .order_by(Video.title, Video.webinar_date)
        )
        rows = result.all()

        # Group by (title, webinar_date)
        groups: dict[tuple, list] = {}
        for video, chunk_count in rows:
            key = (video.title, str(video.webinar_date))
            if key not in groups:
                groups[key] = []
            groups[key].append((video, chunk_count))

        dupes = {k: v for k, v in groups.items() if len(v) > 1}

        if not dupes:
            print("No duplicate videos found.")
            return

        print(f"Found {len(dupes)} duplicate group(s):\n")

        to_delete: list[Video] = []

        for (title, date), entries in dupes.items():
            # Sort: most chunks first (rechunked ones have more smaller chunks)
            entries.sort(key=lambda x: x[1], reverse=True)
            keeper, keeper_chunks = entries[0]
            deletions = entries[1:]

            print(f"  Title: {title}  |  Date: {date}")
            print(f"    KEEP:   {keeper.id}  ({keeper_chunks} chunks, status={keeper.status})")
            for vid, cnt in deletions:
                print(f"    DELETE: {vid.id}  ({cnt} chunks, status={vid.status})")
                to_delete.append(vid)
            print()

        print(f"{'Would delete' if not execute else 'Deleting'} {len(to_delete)} duplicate video record(s)")
        print("(Segments and chunks cascade-delete automatically)\n")

        if not execute:
            print("Run with --execute to apply.")
            return

        for vid in to_delete:
            await db.delete(vid)

        await db.commit()
        print(f"✓ Deleted {len(to_delete)} duplicate video records.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Remove duplicate video records")
    parser.add_argument("--execute", action="store_true", help="Actually delete (default is dry run)")
    args = parser.parse_args()
    asyncio.run(dedup_videos(execute=args.execute))
