"""
Chunking service - implements sliding window chunking over transcript segments.

Target: 600 words per chunk, 120-word overlap
Acceptable range: 500-700 words, 100-150 overlap
"""
from app.errors import ChunkingError


def chunk_segments(
    segments: list[dict],
    target_words: int = 600,
    overlap_words: int = 120
) -> list[dict]:
    """
    Create overlapping chunks from transcript segments.

    Args:
        segments: List of segment dicts with keys:
            - start_time_seconds: float
            - end_time_seconds: float
            - speaker: str | None
            - text: str
        target_words: Target words per chunk (default 600)
        overlap_words: Overlap words between chunks (default 120)

    Returns:
        List of chunk dicts with keys:
            - start_time_seconds: float (from first segment)
            - end_time_seconds: float (from last segment)
            - raw_text: str (concatenated text)
            - speaker_names: list[str] (unique speakers)
            - word_count: int
            - chunk_index: int (position within video)

    Raises:
        ChunkingError: If segments are invalid or chunking fails
    """
    if not segments:
        raise ChunkingError("Cannot chunk empty segments list")

    # Sort segments by start time
    sorted_segments = sorted(segments, key=lambda s: s["start_time_seconds"])

    chunks = []
    chunk_index = 0
    current_position = 0

    while current_position < len(sorted_segments):
        # Start a new chunk
        chunk_segments = []
        chunk_word_count = 0

        # Add segments until we reach target word count
        segment_idx = current_position
        while segment_idx < len(sorted_segments):
            segment = sorted_segments[segment_idx]
            segment_words = len(segment["text"].split())

            # Add this segment to the chunk
            chunk_segments.append(segment)
            chunk_word_count += segment_words

            # Check if we've reached target
            if chunk_word_count >= target_words:
                break

            segment_idx += 1

        # If we didn't get any segments, something went wrong
        if not chunk_segments:
            break

        # Build the chunk
        chunk = {
            "start_time_seconds": chunk_segments[0]["start_time_seconds"],
            "end_time_seconds": chunk_segments[-1]["end_time_seconds"],
            "raw_text": " ".join(seg["text"] for seg in chunk_segments),
            "speaker_names": list(set(
                seg.get("speaker", "Unknown")
                for seg in chunk_segments
                if seg.get("speaker")
            )),
            "word_count": chunk_word_count,
            "chunk_index": chunk_index,
        }

        chunks.append(chunk)
        chunk_index += 1

        # Calculate next position with overlap
        # Work backwards from current position to find where overlap_words starts
        overlap_word_count = 0
        next_position = len(chunk_segments)

        for i in range(len(chunk_segments) - 1, -1, -1):
            segment_words = len(chunk_segments[i]["text"].split())
            overlap_word_count += segment_words

            if overlap_word_count >= overlap_words:
                # Start next chunk at this segment
                next_position = current_position + i
                break

        # Move to next chunk start position
        if next_position <= current_position:
            # Ensure we make progress (avoid infinite loop)
            next_position = current_position + max(1, len(chunk_segments) // 2)

        current_position = next_position

        # If we've processed all segments, stop
        if current_position >= len(sorted_segments):
            break

    if not chunks:
        raise ChunkingError("Chunking produced no results")

    return chunks
