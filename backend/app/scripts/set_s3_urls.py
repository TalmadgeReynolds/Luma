"""
Interactive script to map S3/CDN video URLs to existing webinar records.

For each webinar without an https:// video_url, suggests a match based on
the GMT date prefix (GMT{YYYYMMDD}) and lets you confirm or provide the key.

Usage:
    CDN_BASE_URL=https://your-cdn.example.com python -m app.scripts.set_s3_urls
"""
import asyncio
import os
import re
import sys
from datetime import date

from sqlalchemy import text

from app.db.database import engine


CDN_BASE_URL = os.environ.get("CDN_BASE_URL", "").rstrip("/")


def gmt_prefix_from_date(d: date) -> str:
    return f"GMT{d.strftime('%Y%m%d')}"


def s3_folder_from_date(d: date) -> str:
    """Build the folder path: 'Luma Webinars/YYYYMMDD Luma Webinar/'"""
    return f"Luma Webinars/{d.strftime('%Y%m%d')} Luma Webinar"


def suggest_key(s3_keys: list[str], webinar_date: date | None) -> str | None:
    if not webinar_date:
        return None
    prefix = gmt_prefix_from_date(webinar_date)
    matches = [k for k in s3_keys if os.path.basename(k).startswith(prefix)]
    return matches[0] if len(matches) == 1 else None


def build_cdn_url(cdn_base: str, filename: str, webinar_date: date | None) -> str:
    """Assemble full CDN URL including the nested folder path."""
    import urllib.parse
    if webinar_date:
        folder = s3_folder_from_date(webinar_date)
        key = f"{folder}/{filename}"
    else:
        key = filename
    # URL-encode spaces and special chars in the path
    encoded = urllib.parse.quote(key, safe="/")
    return f"{cdn_base}/{encoded}"


async def main():
    if not CDN_BASE_URL:
        print("Error: CDN_BASE_URL environment variable is required.")
        print("  Example: CDN_BASE_URL=https://your-cdn.example.com python -m app.scripts.set_s3_urls")
        sys.exit(1)

    if len(sys.argv) < 2:
        print("Usage: python -m app.scripts.set_s3_urls GMT*.mp4 [GMT*.mp4 ...]")
        print("Example:")
        print('  python -m app.scripts.set_s3_urls "GMT20260310-165940_Recording.cutfile.20260311021342393_2288x1290.mp4" "GMT20260316-170029_Recording_2288x1290.mp4"')
        sys.exit(1)

    s3_keys = [os.path.basename(arg) for arg in sys.argv[1:]]
    print(f"Loaded {len(s3_keys)} filenames.\n")

    async with engine.connect() as conn:
        rows = await conn.execute(text("""
            SELECT id, title, webinar_date, video_url
            FROM videos
            WHERE content_type = 'webinar'
            ORDER BY webinar_date DESC
        """))
        videos = rows.fetchall()

    updates: list[tuple[str, str]] = []  # (video_id, cdn_url)

    for video in videos:
        vid_id = str(video.id)
        title = video.title
        webinar_date = video.webinar_date
        current_url = video.video_url or ""

        if current_url.startswith("https://"):
            print(f"[skip] {title} — already has CDN URL")
            continue

        date_str = webinar_date.strftime("%Y-%m-%d") if webinar_date else "unknown date"
        suggestion = suggest_key(s3_keys, webinar_date)

        print(f"\n{'─'*60}")
        print(f"Title : {title}")
        print(f"Date  : {date_str}")
        if suggestion:
            print(f"Suggested key: {suggestion}")
            answer = input("Press Enter to accept, or type a different key (or 's' to skip): ").strip()
            if answer.lower() == "s":
                print("  → skipped")
                continue
            s3_key = answer if answer else suggestion
        else:
            print(f"No auto-match found for GMT prefix {gmt_prefix_from_date(webinar_date) if webinar_date else 'N/A'}")
            s3_key = input("Enter S3 key (or press Enter to skip): ").strip()
            if not s3_key:
                print("  → skipped")
                continue

        cdn_url = build_cdn_url(CDN_BASE_URL, s3_key, webinar_date)
        print(f"  → will set: {cdn_url}")
        updates.append((vid_id, cdn_url))

    if not updates:
        print("\nNo updates to apply.")
        return

    print(f"\n{'='*60}")
    print(f"About to update {len(updates)} video record(s). Confirm? [y/N]: ", end="")
    confirm = input().strip().lower()
    if confirm != "y":
        print("Aborted.")
        return

    async with engine.begin() as conn:
        for vid_id, cdn_url in updates:
            await conn.execute(
                text("UPDATE videos SET video_url = :url WHERE id = :id"),
                {"url": cdn_url, "id": vid_id},
            )

    print(f"\nDone. Updated {len(updates)} video(s).")


if __name__ == "__main__":
    asyncio.run(main())
