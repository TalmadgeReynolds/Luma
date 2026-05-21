"""
Hot folder watcher — drop a webinar subfolder here to trigger automatic ingestion.

Usage (from backend/):
    python -m app.scripts.watch_hot_folder

Drop zone: <project_root>/hot_folder/
Each subfolder must contain:
  - *.transcript.vtt  (required — Zoom-style VTT with "Speaker: text" cues)
  - metadata.json     (optional — title, description, date, speakers, video_url)

On success the subfolder is moved to hot_folder/processed/.
On failure  the subfolder is moved to hot_folder/failed/ with an error.txt.
"""

import asyncio
import json
import os
import re
import shutil
import sys
import time
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

# --------------------------------------------------------------------------- #
# VTT → JSON conversion
# --------------------------------------------------------------------------- #
_TIMESTAMP_RE = re.compile(
    r"(\d{2}):(\d{2}):(\d{2})[.,](\d{3})\s*-->\s*"
    r"(\d{2}):(\d{2}):(\d{2})[.,](\d{3})"
)


def _ts_to_seconds(h: str, m: str, s: str, ms: str) -> float:
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0


def vtt_to_segments(vtt_path: Path) -> list[dict]:
    """
    Parse a Zoom-style VTT file into the ingestion JSON format.

    Expected cue format (speaker label on same line as text):
        Speaker Name: cue text here

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

    return segments


# --------------------------------------------------------------------------- #
# Ingestion trigger
# --------------------------------------------------------------------------- #
async def _run_ingestion(folder: Path) -> None:
    """Convert VTT and call ingest_webinar for the given subfolder."""
    # Import here to avoid loading DB config at module import time
    from app.db.database import AsyncSessionLocal
    from app.services.ingestion_service import ingest_webinar

    # Locate VTT file
    vtt_files = sorted(folder.glob("*.vtt"))
    if not vtt_files:
        raise FileNotFoundError(f"No .vtt file found in {folder}")

    # Prefer *.transcript.vtt if multiple exist
    transcript_vtt = next(
        (f for f in vtt_files if "transcript" in f.name.lower()), vtt_files[0]
    )

    # Convert VTT → segments list
    print(f"  Converting {transcript_vtt.name} …")
    segments = vtt_to_segments(transcript_vtt)
    if not segments:
        raise ValueError(f"VTT file produced 0 segments: {transcript_vtt}")

    # Write temp JSON (ingestion_service reads from file path)
    tmp_json = folder / "_transcript_converted.json"
    tmp_json.write_text(json.dumps(segments, indent=2, ensure_ascii=False))

    # Load optional metadata.json
    meta_file = folder / "metadata.json"
    if meta_file.exists():
        meta = json.loads(meta_file.read_text())
    else:
        meta = {}

    title       = meta.get("title") or folder.name
    description = meta.get("description")
    date        = meta.get("date")
    speakers    = meta.get("speakers") or _extract_speakers(segments)

    # Copy any video file to backend/videos/ and set video_url
    video_url = meta.get("video_url")
    if not video_url:
        video_files = [f for f in folder.iterdir() if f.suffix.lower() in _VIDEO_EXTENSIONS]
        if video_files:
            VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
            src = video_files[0]
            dest = VIDEOS_DIR / src.name
            if not dest.exists():
                shutil.copy2(str(src), str(dest))
                print(f"  Copied video: {src.name} → backend/videos/")
            video_url = f"/videos/{src.name}"
            print(f"  video_url   : {video_url}")

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
# Folder processing (async — runs inside the single persistent event loop)
# --------------------------------------------------------------------------- #
async def process_folder(folder: Path) -> None:
    """Run ingestion for the given subfolder and move it on completion."""
    print(f"\n{'='*60}")
    print(f"[HOT FOLDER] Processing: {folder.name}")
    print(f"{'='*60}")

    try:
        await _run_ingestion(folder)

        if not folder.exists():
            print(f"  ✓ Ingestion succeeded; folder already removed (likely moved by another process)\n")
            return

        dest = PROCESSED / folder.name
        if dest.exists():
            dest = PROCESSED / f"{folder.name}_{int(time.time())}"
        shutil.move(str(folder), dest)
        print(f"  → Moved to processed/{dest.name}\n")

    except Exception as exc:
        print(f"  ✗ Error: {exc}\n")

        if not folder.exists():
            print(f"  (folder already gone; skipping move to failed/)\n")
            return

        dest = FAILED / folder.name
        if dest.exists():
            dest = FAILED / f"{folder.name}_{int(time.time())}"
        try:
            shutil.move(str(folder), dest)
        except FileNotFoundError:
            print(f"  (folder disappeared before it could be moved to failed/)\n")
            return
        (dest / "error.txt").write_text(str(exc))
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
        if p.parent == HOT_FOLDER and p.is_dir():
            subfolder = str(p)
        elif p.parent.parent == HOT_FOLDER and p.parent.name not in ("processed", "failed"):
            subfolder = str(p.parent)
        else:
            return

        if subfolder in (str(PROCESSED), str(FAILED)):
            return

        eligible_at = time.time() + _SETTLE_SECONDS
        if self._pending.get(subfolder, 0) < eligible_at:
            self._pending[subfolder] = eligible_at
            print(f"  [queued] {Path(subfolder).name} (processing in {_SETTLE_SECONDS}s …)")

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
    """Consume folders from the queue and ingest them sequentially."""
    while True:
        folder: Path = await queue.get()
        if folder.exists() and folder.is_dir():
            await process_folder(folder)
        queue.task_done()


async def _main_async() -> None:
    PROCESSED.mkdir(parents=True, exist_ok=True)
    FAILED.mkdir(parents=True, exist_ok=True)

    print(f"[HOT FOLDER] Watching: {HOT_FOLDER}")
    print(f"  Drop a webinar subfolder with a .vtt transcript inside.")
    print(f"  Optional metadata.json: title, description, date, speakers, video_url")
    print(f"  Press Ctrl+C to stop.\n")

    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_running_loop()

    # Start the background worker
    worker_task = asyncio.create_task(_worker(queue))

    # Enqueue any pre-existing subfolders immediately
    for child in sorted(HOT_FOLDER.iterdir()):
        if child.is_dir() and child.name not in ("processed", "failed") and not child.name.startswith("."):
            print(f"[HOT FOLDER] Found existing folder on startup: {child.name}")
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
                folder = Path(folder_str)
                if folder.exists() and folder.is_dir():
                    await queue.put(folder)
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
