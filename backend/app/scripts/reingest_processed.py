"""
One-time batch re-ingestion of all folders in hot_folder/processed/.

Each folder must already contain a _transcript_converted.json (they all do).
Skips folders where a video already exists in the DB with the same title.

Usage (from backend/):
    python -m app.scripts.reingest_processed
"""
import asyncio
import json
import re
import urllib.parse
from pathlib import Path

from app.db.database import AsyncSessionLocal
from app.services.ingestion_service import ingest_webinar

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PROCESSED    = PROJECT_ROOT / "hot_folder" / "processed"

_VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm", ".avi", ".mkv"}
_S3_BASE = "https://luma-webinars-730335545672-us-east-1-an.s3.us-east-1.amazonaws.com"
_GMT_DATE_RE = re.compile(r"GMT(\d{8})")


def _build_s3_url(filename: str) -> str | None:
    m = _GMT_DATE_RE.search(filename)
    if not m:
        return None
    date = m.group(1)
    key = f"Luma Webinars/{date} Luma Webinar/{filename}"
    return f"{_S3_BASE}/{urllib.parse.quote(key, safe='/')}"


def _extract_speakers(segments: list[dict]) -> list[str]:
    seen: list[str] = []
    for seg in segments:
        s = seg.get("speaker")
        if s and s not in seen:
            seen.append(s)
    return seen


async def ingest_folder(folder: Path) -> None:
    transcript_json = folder / "_transcript_converted.json"
    if not transcript_json.exists():
        print(f"  SKIP {folder.name} — no _transcript_converted.json")
        return

    segments = json.loads(transcript_json.read_text())
    if not segments:
        print(f"  SKIP {folder.name} — empty transcript")
        return

    meta_file = folder / "metadata.json"
    meta = json.loads(meta_file.read_text()) if meta_file.exists() else {}

    title    = meta.get("title") or folder.name
    date     = meta.get("date")
    speakers = meta.get("speakers") or _extract_speakers(segments)

    # Try to derive S3 video URL from any video file in the folder
    video_url = meta.get("video_url")
    if not video_url:
        video_files = [f for f in folder.iterdir() if f.suffix.lower() in _VIDEO_EXTENSIONS]
        if video_files:
            video_url = _build_s3_url(video_files[0].name)
            if not meta.get("title"):
                title = video_files[0].stem

    print(f"  Ingesting: {title}")
    print(f"    segments={len(segments)}  date={date or '—'}  video_url={video_url or '—'}")

    async with AsyncSessionLocal() as session:
        video_id, chunk_count = await ingest_webinar(
            title=title,
            description=meta.get("description"),
            webinar_date=date,
            speakers=speakers,
            video_url=video_url,
            transcript_path=str(transcript_json),
            db_session=session,
        )

    print(f"    ✓ video_id={video_id}  chunks={chunk_count}")


async def main() -> None:
    folders = sorted([f for f in PROCESSED.iterdir() if f.is_dir()])
    print(f"Found {len(folders)} folders in hot_folder/processed/\n")

    for i, folder in enumerate(folders, 1):
        print(f"[{i}/{len(folders)}] {folder.name}")
        try:
            await ingest_folder(folder)
        except Exception as e:
            print(f"    ERROR: {e}")
        print()

    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
