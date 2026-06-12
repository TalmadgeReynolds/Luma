"""
Diagnose chunk quality for the June 3, 2026 webinar vs. the next most-recent webinar.
Checks whether contextual_text was populated during ingest.

Usage (from backend/):
    python -m app.scripts.diagnose_chunk_quality
"""

import asyncio

from sqlalchemy import text

from app.db.database import AsyncSessionLocal

TARGET_VIDEO_ID = "52cf13bf-e759-43ba-b249-f4f0f64de451"


async def main() -> None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            text("""
                SELECT chunk_index, word_count,
                       left(raw_text, 100) as raw_preview,
                       left(contextual_text, 250) as ctx_preview,
                       left(summary, 120) as summary_preview
                FROM chunks
                WHERE video_id = :vid
                ORDER BY chunk_index
                LIMIT 6
            """),
            {"vid": TARGET_VIDEO_ID},
        )
        rows = result.fetchall()

        print(f"\n=== June 3, 2026 webinar chunks ({len(rows)} of 18 shown) ===")
        for r in rows:
            raw = repr(r.raw_preview) if r.raw_preview else "(EMPTY)"
            ctx = repr(r.ctx_preview) if r.ctx_preview else "(EMPTY)"
            summ = repr(r.summary_preview) if r.summary_preview else "(EMPTY)"
            print(f"\n  [chunk {r.chunk_index}, {r.word_count} words]")
            print(f"  raw:  {raw}")
            print(f"  ctx:  {ctx}")
            print(f"  summ: {summ}")

        result2 = await db.execute(
            text("""
                SELECT c.chunk_index, c.word_count,
                       left(c.contextual_text, 250) as ctx_preview,
                       v.webinar_date, v.title
                FROM chunks c
                JOIN videos v ON c.video_id = v.id
                WHERE v.content_type = 'webinar'
                  AND v.id != :vid
                  AND v.status = 'embedded'
                ORDER BY v.webinar_date DESC, c.chunk_index
                LIMIT 3
            """),
            {"vid": TARGET_VIDEO_ID},
        )
        rows2 = result2.fetchall()

        print(f"\n=== Comparison: next most-recent webinar ===")
        for r in rows2:
            ctx = repr(r.ctx_preview) if r.ctx_preview else "(EMPTY)"
            title = r.title[:60] if r.title else "?"
            print(f"\n  [{r.webinar_date} - {title} - chunk {r.chunk_index}, {r.word_count} words]")
            print(f"  ctx: {ctx}")


if __name__ == "__main__":
    asyncio.run(main())
