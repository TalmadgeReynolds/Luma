"""
Hot folder watcher — drop a webinar file or subfolder here to trigger automatic ingestion.

Usage (from backend/):
    python -m app.scripts.watch_hot_folder

Drop zone: <project_root>/hot_folder/

Accepted inputs:
  - A single transcript file (*.vtt, *.transcript, *.txt) dropped directly in hot_folder/
  - A subfolder containing a transcript file plus optional metadata.json

Optional metadata.json keys: title, description, date, speakers, video_url

On success the file/folder is moved to hot_folder/processed/.
On failure  the file/folder is moved to hot_folder/failed/ with an error.txt.
"""

import asyncio
import json
import os
import re
import shutil
import sys
import time
import urllib.parse
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
# hot_folder/ lives at the project root (one level above backend/)
PROJECT_ROOT = Path(__file__).resolve().parents[3]  # …/Luma
HOT_FOLDER   = PROJECT_ROOT / "hot_folder"
PROCESSED    = HOT_FOLDER / "processed"
FAILED       = HOT_FOLDER / "failed"

# Videos are served by FastAPI from backend/videos/
VIDEOS_DIR   = PROJECT_ROOT / "backend" / "videos"

_VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm", ".avi", ".mkv"}
_TRANSCRIPT_EXTENSIONS = {".vtt", ".transcript", ".txt"}

_S3_BASE = "https://luma-webinars-730335545672-us-east-1-an.s3.us-east-1.amazonaws.com"
_GMT_DATE_RE = re.compile(r"GMT(\d{8})")


def _build_s3_url(filename: str) -> str | None:
    """Derive the S3 URL from a GMT-prefixed recording filename."""
    m = _GMT_DATE_RE.search(filename)
    if not m:
        return None
    date = m.group(1)
    key = f"Luma Webinars/{date} Luma Webinar/{filename}"
    return f"{_S3_BASE}/{urllib.parse.quote(key, safe='/')}"

# --------------------------------------------------------------------------- #
# VTT → JSON conversion
# --------------------------------------------------------------------------- #
_TIMESTAMP_RE = re.compile(
    r"(\d{2}):(\d{2}):(\d{2})[.,](\d{3})\s*-->\s*"
    r"(\d{2}):(\d{2}):(\d{2})[.,](\d{3})"
)
_SIMPLE_TS_RE = re.compile(r"^(\d+):(\d{2})$")


def _ts_to_seconds(h: str, m: str, s: str, ms: str) -> float:
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0


def _parse_simple_transcript(text: str) -> list[dict]:
    """
    Fallback parser for simple M:SS / text alternating format (no WEBVTT header).
    Timestamps like '0:01', '1:07' alternate with lines of transcript text.
    '>>' prefixes are stripped (indicate speaker turns with no named speaker).
    """
    lines = text.splitlines()
    timestamps: list[float] = []
    texts: list[str] = []
    current_ts: float | None = None
    current_lines: list[str] = []

    for line in lines:
        line = line.strip()
        if not line:
            continue
        m = _SIMPLE_TS_RE.match(line)
        if m:
            if current_ts is not None and current_lines:
                timestamps.append(current_ts)
                texts.append(" ".join(current_lines))
            current_ts = int(m.group(1)) * 60 + int(m.group(2))
            current_lines = []
        else:
            cleaned = re.sub(r"^>>\s*", "", line)
            if cleaned:
                current_lines.append(cleaned)

    if current_ts is not None and current_lines:
        timestamps.append(current_ts)
        texts.append(" ".join(current_lines))

    segments = []
    for i, (ts, txt) in enumerate(zip(timestamps, texts)):
        end_ts = timestamps[i + 1] if i + 1 < len(timestamps) else ts + 5.0
        segments.append({
            "start_time_seconds": float(ts),
            "end_time_seconds": float(end_ts),
            "speaker": None,
            "text": txt,
        })
    return segments


def vtt_to_segments(vtt_path: Path) -> list[dict]:
    """
    Parse a VTT or simple transcript file into the ingestion JSON format.

    Supports:
      1. Standard Zoom-style WebVTT (HH:MM:SS.mmm --> HH:MM:SS.mmm cues)
      2. Simple M:SS / text alternating format (no WEBVTT header)

    Returns list of dicts with keys:
        start_time_seconds, end_time_seconds, speaker, text
    """
    text = vtt_path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()

    segments: list[dict] = []
    i = 0
    while i < len(lines):
        m = _TIMESTAMP_RE.match(lines[i].strip())
        if m:
            start = _ts_to_seconds(m.group(1), m.group(2), m.group(3), m.group(4))
            end   = _ts_to_seconds(m.group(5), m.group(6), m.group(7), m.group(8))
            i += 1
            # Collect all text lines until blank line
            cue_lines = []
            while i < len(lines) and lines[i].strip():
                cue_lines.append(lines[i].strip())
                i += 1
            full_text = " ".join(cue_lines)
            if not full_text:
                continue

            # Try to split "Speaker Name: text"
            if ": " in full_text:
                speaker, _, body = full_text.partition(": ")
            else:
                speaker = None
                body = full_text

            segments.append({
                "start_time_seconds": start,
                "end_time_seconds": end,
                "speaker": speaker,
                "text": body,
            })
        else:
            i += 1

    if not segments:
        segments = _parse_simple_transcript(text)

    return segments


# --------------------------------------------------------------------------- #
# Ingestion trigger
# --------------------------------------------------------------------------- #
def _resolve_video_url_for_transcription(folder: Path, meta: dict) -> str | None:
    """Return an HTTPS URL suitable for cloud transcription, or None if unavailable."""
    # 1. Explicit URL in metadata.json
    if meta.get("video_url"):
        return meta["video_url"]
    # 2. Video file in folder whose filename can be mapped to an S3 URL
    video_files = [f for f in folder.iterdir() if f.suffix.lower() in _VIDEO_EXTENSIONS]
    for vf in video_files:
        url = _build_s3_url(vf.name)
        if url:
            return url
    return None


async def _run_ingestion(folder_or_file: Path) -> None:
    """Convert VTT and call ingest_webinar. Accepts a folder or a bare transcript file."""
    # Import here to avoid loading DB config at module import time
    from app.db.database import AsyncSessionLocal
    from app.services.ingestion_service import ingest_webinar

    # segments is populated either by parsing a transcript file or by the transcription service
    segments: list[dict] | None = None

    if folder_or_file.is_file():
        # Bare file dropped directly — use it as the transcript, no metadata
        transcript_vtt: Path | None = folder_or_file
        meta: dict = {}
        video_search_dir: Path | None = None
        tmp_json = folder_or_file.parent / f"_{folder_or_file.stem}_converted.json"
    else:
        folder = folder_or_file
        meta_file = folder / "metadata.json"
        meta = json.loads(meta_file.read_text()) if meta_file.exists() else {}
        video_search_dir = folder
        tmp_json = folder / "_transcript_converted.json"

        # Locate transcript file — supports *.vtt, *.transcript, and *.txt
        transcript_files = (
            sorted(folder.glob("*.vtt")) +
            sorted(folder.glob("*.transcript")) +
            sorted(folder.glob("*.transcript.txt")) +
            sorted(folder.glob("*.txt"))
        )
        # Exclude error.txt written by the watcher itself
        transcript_files = [f for f in transcript_files if f.name != "error.txt"]

        if not transcript_files:
            # No transcript found — attempt auto-transcription via the configured provider
            video_url_for_tx = _resolve_video_url_for_transcription(folder, meta)
            if video_url_for_tx is None:
                raise FileNotFoundError(
                    f"No transcript file found in {folder} "
                    "(expected *.vtt, *.transcript, or *.txt). "
                    "To enable auto-transcription, set video_url in metadata.json "
                    "and configure TRANSCRIPTION_PROVIDER in your .env."
                )
            print(f"  No transcript found — requesting auto-transcription…")
            from app.services import transcription_service
            segments = await transcription_service.transcribe_video(video_url_for_tx)
            if not segments:
                raise ValueError(f"Auto-transcription returned 0 segments for {folder.name}")
            transcript_vtt = None
        else:
            # Prefer files with 'transcript' in the name if multiple exist
            transcript_vtt = next(
                (f for f in transcript_files if "transcript" in f.name.lower()), transcript_files[0]
            )

    # Parse transcript file if segments not already obtained from transcription service
    if segments is None:
        print(f"  Converting {transcript_vtt.name} …")
        segments = vtt_to_segments(transcript_vtt)
        if not segments:
            raise ValueError(f"Transcript file produced 0 segments: {transcript_vtt}")

    tmp_json.write_text(json.dumps(segments, indent=2, ensure_ascii=False))

    # transcript_vtt may be None when segments came from the transcription service
    title_fallback = transcript_vtt.stem if transcript_vtt else folder_or_file.name
    title       = meta.get("title") or title_fallback
    description = meta.get("description")
    date        = meta.get("date")
    speakers    = meta.get("speakers") or _extract_speakers(segments)

    # Copy any video file to backend/videos/ and set video_url
    video_url = meta.get("video_url")
    if not video_url and video_search_dir:
        video_files = [f for f in video_search_dir.iterdir() if f.suffix.lower() in _VIDEO_EXTENSIONS]
        if video_files:
            video_file = video_files[0]
            video_url = _build_s3_url(video_file.name)
            if video_url:
                print(f"  video_url (S3): {video_url}")
            else:
                print(f"  Warning: could not derive S3 URL from {video_file.name}")
            # Extract date from GMT filename when metadata.json didn't provide one
            if not date:
                m = _GMT_DATE_RE.search(video_file.name)
                if m:
                    d = m.group(1)  # YYYYMMDD
                    date = f"{d[:4]}-{d[4:6]}-{d[6:]}"  # → YYYY-MM-DD
            # Use mp4 stem as title if no explicit title was set
            if not meta.get("title"):
                title = video_file.stem

    print(f"  Title   : {title}")
    print(f"  Speakers: {speakers}")
    print(f"  Date    : {date or '(not set)'}")
    print(f"  Segments: {len(segments)}")

    async with AsyncSessionLocal() as session:
        video_id, chunk_count = await ingest_webinar(
            title=title,
            description=description,
            webinar_date=date,
            speakers=speakers,
            video_url=video_url,
            transcript_path=str(tmp_json),
            db_session=session,
        )

    print(f"  ✓ video_id={video_id}  chunks={chunk_count}")


def _extract_speakers(segments: list[dict]) -> list[str]:
    """Collect unique non-None speaker names from segments."""
    seen: list[str] = []
    for seg in segments:
        s = seg.get("speaker")
        if s and s not in seen:
            seen.append(s)
    return seen


# --------------------------------------------------------------------------- #
# Item processing (async — runs inside the single persistent event loop)
# --------------------------------------------------------------------------- #
async def process_item(item: Path) -> None:
    """Run ingestion for a transcript file or subfolder and move it on completion."""
    print(f"\n{'='*60}")
    print(f"[HOT FOLDER] Processing: {item.name}")
    print(f"{'='*60}")

    try:
        await _run_ingestion(item)

        if not item.exists():
            print(f"  ✓ Ingestion succeeded; item already removed\n")
            return

        dest = PROCESSED / item.name
        if dest.exists():
            dest = PROCESSED / f"{item.name}_{int(time.time())}"
        shutil.move(str(item), dest)
        print(f"  → Moved to processed/{dest.name}\n")

    except Exception as exc:
        print(f"  ✗ Error: {exc}\n")

        if not item.exists():
            print(f"  (item already gone; skipping move to failed/)\n")
            return

        dest = FAILED / item.name
        if dest.exists():
            dest = FAILED / f"{item.name}_{int(time.time())}"
        try:
            shutil.move(str(item), dest)
        except FileNotFoundError:
            print(f"  (item disappeared before it could be moved to failed/)\n")
            return
        # Write error alongside the item
        err_file = dest.parent / f"{dest.name}.error.txt" if dest.is_file() else dest / "error.txt"
        err_file.write_text(str(exc))
        print(f"  → Moved to failed/{dest.name}\n")


# --------------------------------------------------------------------------- #
# Watchdog handler — puts folder paths onto an asyncio.Queue
# --------------------------------------------------------------------------- #
_SETTLE_SECONDS = 3   # wait for file writes to finish before processing


class HotFolderHandler(FileSystemEventHandler):
    """Watch for new/modified files in hot_folder subfolders."""

    def __init__(self, queue: asyncio.Queue, loop: asyncio.AbstractEventLoop):
        super().__init__()
        self._queue = queue
        self._loop = loop
        self._pending: dict[str, float] = {}  # folder_path → eligible-at timestamp

    def on_created(self, event):
        self._schedule(event.src_path)

    def on_modified(self, event):
        self._schedule(event.src_path)

    def _schedule(self, path: str):
        p = Path(path)
        # Bare transcript file dropped directly in hot_folder
        if (p.parent == HOT_FOLDER and p.is_file()
                and p.suffix.lower() in _TRANSCRIPT_EXTENSIONS
                and p.name != "error.txt"):
            key = str(p)
        # Subfolder dropped in hot_folder
        elif p.parent == HOT_FOLDER and p.is_dir():
            key = str(p)
        # File modified inside a subfolder (not processed/failed)
        elif p.parent.parent == HOT_FOLDER and p.parent.name not in ("processed", "failed"):
            key = str(p.parent)
        else:
            return

        if key in (str(PROCESSED), str(FAILED)):
            return

        eligible_at = time.time() + _SETTLE_SECONDS
        if self._pending.get(key, 0) < eligible_at:
            self._pending[key] = eligible_at
            print(f"  [queued] {Path(key).name} (processing in {_SETTLE_SECONDS}s …)")

    def drain_due(self) -> list[str]:
        """Return and remove folder paths whose settle time has passed."""
        now = time.time()
        due = [p for p, t in list(self._pending.items()) if t <= now]
        for p in due:
            del self._pending[p]
        return due


# --------------------------------------------------------------------------- #
# Main async loop — single event loop for all ingestion work
# --------------------------------------------------------------------------- #
async def _worker(queue: asyncio.Queue) -> None:
    """Consume files/folders from the queue and ingest them sequentially."""
    while True:
        item: Path = await queue.get()
        if item.exists():
            await process_item(item)
        queue.task_done()


async def _main_async() -> None:
    PROCESSED.mkdir(parents=True, exist_ok=True)
    FAILED.mkdir(parents=True, exist_ok=True)

    print(f"[HOT FOLDER] Watching: {HOT_FOLDER}")
    print(f"  Drop a transcript file (*.vtt, *.txt) or a subfolder with a transcript inside.")
    print(f"  Optional metadata.json (in subfolder): title, description, date, speakers, video_url")
    print(f"  Press Ctrl+C to stop.\n")

    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_running_loop()

    # Start the background worker
    worker_task = asyncio.create_task(_worker(queue))

    # Enqueue any pre-existing items (subfolders and loose transcript files)
    for child in sorted(HOT_FOLDER.iterdir()):
        if child.name in ("processed", "failed") or child.name.startswith("."):
            continue
        if child.is_dir():
            print(f"[HOT FOLDER] Found existing folder on startup: {child.name}")
            await queue.put(child)
        elif child.is_file() and child.suffix.lower() in _TRANSCRIPT_EXTENSIONS:
            print(f"[HOT FOLDER] Found existing file on startup: {child.name}")
            await queue.put(child)

    # Start watchdog observer
    handler = HotFolderHandler(queue, loop)
    observer = Observer()
    observer.schedule(handler, str(HOT_FOLDER), recursive=True)
    observer.start()

    try:
        while True:
            await asyncio.sleep(1)
            # Drain settled watchdog events into the queue
            for folder_str in handler.drain_due():
                item = Path(folder_str)
                if item.exists():
                    await queue.put(item)
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        observer.stop()
        observer.join()
        worker_task.cancel()
        print("\n[HOT FOLDER] Watcher stopped.")


def main() -> None:
    asyncio.run(_main_async())


if __name__ == "__main__":
    main()
