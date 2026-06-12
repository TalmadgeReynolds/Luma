"""
Transcription service — send a video/audio URL to a cloud transcription provider.

Supported providers (set via TRANSCRIPTION_PROVIDER in .env):
  assemblyai  — AssemblyAI async API (recommended; no file-size limit, handles long videos)
  deepgram    — Deepgram Nova-2 (URL-based, supports long files)
  whisper     — OpenAI Whisper API (25 MB file-size limit; use for short clips only)
  json        — (default) no-op; transcription disabled

Returns segments compatible with the ingestion pipeline:
  [{"start_time_seconds": float, "end_time_seconds": float,
    "speaker": str | None, "text": str}]
"""

import asyncio
import io
from urllib.parse import urlparse

import httpx


async def transcribe_video(video_url: str) -> list[dict]:
    """
    Transcribe a video/audio file from a URL using the configured provider.

    Raises:
        ValueError: If provider is misconfigured, API key is missing, or transcription fails.
    """
    # Import here to avoid loading DB config at module import time
    from app.config import get_settings
    settings = get_settings()
    provider = settings.TRANSCRIPTION_PROVIDER.lower()

    if provider == "assemblyai":
        return await _transcribe_assemblyai(video_url, settings)
    if provider == "deepgram":
        return await _transcribe_deepgram(video_url, settings)
    if provider == "whisper":
        return await _transcribe_whisper(video_url, settings)
    if provider == "json":
        raise ValueError(
            "TRANSCRIPTION_PROVIDER is set to 'json' (disabled). "
            "Set it to 'assemblyai', 'deepgram', or 'whisper' to enable auto-transcription."
        )
    raise ValueError(
        f"Unknown TRANSCRIPTION_PROVIDER '{provider}'. "
        "Expected: 'assemblyai', 'deepgram', or 'whisper'."
    )


# --------------------------------------------------------------------------- #
# AssemblyAI
# --------------------------------------------------------------------------- #

async def _transcribe_assemblyai(video_url: str, settings) -> list[dict]:
    """
    Submit a transcription job to AssemblyAI and poll until complete.
    Supports any video length; speaker diarization is enabled automatically.
    """
    api_key = getattr(settings, "ASSEMBLYAI_API_KEY", None)
    if not api_key:
        raise ValueError(
            "ASSEMBLYAI_API_KEY is required when TRANSCRIPTION_PROVIDER='assemblyai'. "
            "Add it to your .env file."
        )

    headers = {"authorization": api_key, "content-type": "application/json"}

    async with httpx.AsyncClient(timeout=60) as client:
        print(f"  [transcription] Submitting to AssemblyAI: {video_url[:80]}…")
        resp = await client.post(
            "https://api.assemblyai.com/v2/transcript",
            json={"audio_url": video_url, "speaker_labels": True},
            headers=headers,
        )
        resp.raise_for_status()
        job_id = resp.json()["id"]
        print(f"  [transcription] Job submitted (id={job_id}) — polling for completion…")

    poll_url = f"https://api.assemblyai.com/v2/transcript/{job_id}"
    async with httpx.AsyncClient(timeout=30) as poll_client:
        while True:
            await asyncio.sleep(10)
            result = (await poll_client.get(poll_url, headers=headers)).json()
            status = result["status"]
            if status == "completed":
                break
            if status == "error":
                raise ValueError(f"AssemblyAI transcription failed: {result.get('error')}")
            print(f"  [transcription] Status: {status}…")

    # Prefer speaker-diarised utterances when available
    utterances = result.get("utterances") or []
    if utterances:
        return [
            {
                "start_time_seconds": u["start"] / 1000.0,
                "end_time_seconds": u["end"] / 1000.0,
                "speaker": f"Speaker {u['speaker']}",
                "text": u["text"],
            }
            for u in utterances
        ]

    # Fallback: group raw word timestamps into 30-second segments
    words = result.get("words") or []
    if not words:
        raise ValueError("AssemblyAI returned an empty transcript")
    return _group_words_to_segments(words, chunk_duration=30.0)


# --------------------------------------------------------------------------- #
# Deepgram
# --------------------------------------------------------------------------- #

async def _transcribe_deepgram(video_url: str, settings) -> list[dict]:
    """
    Transcribe via Deepgram Nova-2.  Sends the URL directly; handles long files.
    """
    api_key = getattr(settings, "DEEPGRAM_API_KEY", None)
    if not api_key:
        raise ValueError(
            "DEEPGRAM_API_KEY is required when TRANSCRIPTION_PROVIDER='deepgram'. "
            "Add it to your .env file."
        )

    headers = {"Authorization": f"Token {api_key}", "Content-Type": "application/json"}
    params = {
        "model": "nova-2",
        "smart_format": "true",
        "utterances": "true",
        "diarize": "true",
        "punctuate": "true",
    }

    print(f"  [transcription] Submitting to Deepgram: {video_url[:80]}…")
    # Deepgram synchronous endpoint — may take several minutes for long audio
    async with httpx.AsyncClient(timeout=1800) as client:
        resp = await client.post(
            "https://api.deepgram.com/v1/listen",
            json={"url": video_url},
            headers=headers,
            params=params,
        )
        resp.raise_for_status()
        data = resp.json()

    utterances = data.get("results", {}).get("utterances") or []
    if utterances:
        return [
            {
                "start_time_seconds": u["start"],
                "end_time_seconds": u["end"],
                "speaker": f"Speaker {u['speaker']}",
                "text": u["transcript"],
            }
            for u in utterances
        ]

    # Fallback: word-level timestamps
    words = (
        data.get("results", {})
        .get("channels", [{}])[0]
        .get("alternatives", [{}])[0]
        .get("words", [])
    )
    if not words:
        raise ValueError("Deepgram returned an empty transcript")
    return _group_words_to_segments(
        [{"start": w["start"] * 1000, "end": w["end"] * 1000, "text": w["word"]} for w in words],
        chunk_duration=30.0,
    )


# --------------------------------------------------------------------------- #
# OpenAI Whisper
# --------------------------------------------------------------------------- #

async def _transcribe_whisper(video_url: str, settings) -> list[dict]:
    """
    Transcribe via OpenAI Whisper API.

    WARNING: Whisper has a 25 MB per-request file-size limit.
    For long videos use TRANSCRIPTION_PROVIDER='assemblyai' or 'deepgram' instead.
    """
    import openai

    api_key = getattr(settings, "OPENAI_API_KEY", None)
    if not api_key:
        raise ValueError(
            "OPENAI_API_KEY is required when TRANSCRIPTION_PROVIDER='whisper'. "
            "Add it to your .env file."
        )

    print(f"  [transcription] Downloading audio for Whisper: {video_url[:80]}…")
    async with httpx.AsyncClient(timeout=300) as client:
        resp = await client.get(video_url)
        resp.raise_for_status()
        data = resp.content

    size_mb = len(data) / (1024 * 1024)
    if size_mb > 25:
        raise ValueError(
            f"Video is {size_mb:.1f} MB — exceeds Whisper's 25 MB per-request limit. "
            "Use TRANSCRIPTION_PROVIDER='assemblyai' or 'deepgram' for long videos."
        )

    print(f"  [transcription] Sending {size_mb:.1f} MB to Whisper…")
    filename = urlparse(video_url).path.split("/")[-1] or "audio.mp4"

    oai = openai.AsyncOpenAI(api_key=api_key)
    result = await oai.audio.transcriptions.create(
        model="whisper-1",
        file=(filename, io.BytesIO(data)),
        response_format="verbose_json",
        timestamp_granularities=["segment"],
    )

    raw_segments = getattr(result, "segments", None) or []
    if not raw_segments:
        raise ValueError("Whisper returned no transcription segments")

    return [
        {
            "start_time_seconds": float(s["start"]),
            "end_time_seconds": float(s["end"]),
            "speaker": None,
            "text": s["text"].strip(),
        }
        for s in raw_segments
    ]


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _group_words_to_segments(
    words: list[dict],  # each: {"start": ms_float, "end": ms_float, "text": str}
    chunk_duration: float = 30.0,
) -> list[dict]:
    """Group word-level timestamps into fixed-duration segments."""
    if not words:
        return []

    chunk_ms = chunk_duration * 1000
    segments: list[dict] = []
    chunk_start = words[0]["start"]
    chunk_words: list[str] = []

    for w in words:
        chunk_words.append(w["text"])
        if w["end"] - chunk_start >= chunk_ms:
            segments.append({
                "start_time_seconds": chunk_start / 1000.0,
                "end_time_seconds": w["end"] / 1000.0,
                "speaker": None,
                "text": " ".join(chunk_words).strip(),
            })
            chunk_start = w["end"]
            chunk_words = []

    if chunk_words:
        segments.append({
            "start_time_seconds": chunk_start / 1000.0,
            "end_time_seconds": words[-1]["end"] / 1000.0,
            "speaker": None,
            "text": " ".join(chunk_words).strip(),
        })

    return segments
