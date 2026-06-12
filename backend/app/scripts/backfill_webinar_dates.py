"""
One-shot backfill: set webinar_date on videos where it is NULL but the
video_url contains a GMT{YYYYMMDD} date stamp (standard Zoom recording format).

Usage (from backend/):
    python -m app.scripts.backfill_webinar_dates
"""

import asyncio
import re
from datetime import date

from sqlalchemy import select, update

from app.db.database import AsyncSessionLocal
from app.db.models import Video

_GMT_DATE_RE = re.compile(r"GMT(\d{8})")


async def backfill() -> None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Video).where(
                Video.webinar_date.is_(None),
                Video.video_url.isnot(None),
                Video.content_type == "webinar",
            )
        )
        videos = result.scalars().all()

        if not videos:
            print("No videos with null webinar_date found.")
            return

        updated = 0
        skipped = 0
        for video in videos:
            m = _GMT_DATE_RE.search(video.video_url)
            if not m:
                print(f"  SKIP  {video.id} — no GMT date in URL: {video.video_url}")
                skipped += 1
                continue
            d = m.group(1)  # YYYYMMDD
            parsed = date(int(d[:4]), int(d[4:6]), int(d[6:]))
            video.webinar_date = parsed
            print(f"  SET   {video.id} → {parsed}  ({video.title})")
            updated += 1

        await session.commit()
        print(f"\nDone — updated {updated}, skipped {skipped}.")


if __name__ == "__main__":
    asyncio.run(backfill())
