# Hot Folder — Ingestion Drop Zone

Drop a webinar subfolder here to trigger automatic ingestion.

**→ See [INGESTION_GUIDE.md](./INGESTION_GUIDE.md) for step-by-step instructions with S3 video URLs.**

## Folder Structure

```
hot_folder/
  20260521/                                    ← folder named YYYYMMDD
    webinar-transcript.txt                    ← required (*.txt, *.vtt, or *.transcript)
    metadata.json                             ← optional (see below)
```

## Supported Transcript Formats

- `.txt` — Plain text with M:SS timestamps (e.g., `0:15`, `1:23`)
- `.vtt` — WebVTT format (HH:MM:SS.mmm --> HH:MM:SS.mmm)
- `.transcript` — Alternating timestamp/text lines

Any file with `transcript` in the name is preferred. See [INGESTION_GUIDE.md](./INGESTION_GUIDE.md) for format examples.

## metadata.json

All fields are optional except `video_url` (if you want S3 videos):

```json
{
  "title": "Character Consistency Deep Dive",
  "description": "Best practices for AI video generation",
  "date": "2026-05-21",
  "speakers": ["Alice Chen", "Bob Martinez"],
  "video_url": "https://luma-webinars-730335545672-us-east-1-an.s3.us-east-1.amazonaws.com/Luma%20Webinars/20260521%20Luma%20Webinar/GMT20260521-170000_Recording_2560x1440.mp4"
}
```

**Fields:**
- `title` — defaults to folder name if omitted
- `description` — optional
- `date` — optional (ISO format: YYYY-MM-DD)
- `speakers` — optional; auto-extracted from transcript if omitted
- `video_url` — (**for S3**) full HTTPS URL to video. If omitted, watcher looks for local video files.

**S3 URL Format:**
```
https://luma-webinars-730335545672-us-east-1-an.s3.us-east-1.amazonaws.com/Luma%20Webinars/{YYYYMMDD}%20Luma%20Webinar/{filename}.mp4
```

Use the helper script to generate: `python scripts/s3_url_builder.py 20260521 GMT20260521-170000_Recording_2560x1440.mp4`

## Processing

- **On success:** folder moves to `processed/` — original files kept for reference
- **On failure:** folder moves to `failed/` with an `error.txt` explaining what went wrong

## Examples

See `metadata.example.json` for a fully annotated template.
