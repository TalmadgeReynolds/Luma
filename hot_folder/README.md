# Hot Folder — Ingestion Drop Zone

Drop a webinar subfolder here to trigger automatic ingestion.

## Folder Structure

```
hot_folder/
  my-webinar-2026-05-21/
    recording.transcript.vtt   ← required (Zoom transcript VTT)
    metadata.json              ← optional (see below)
```

## metadata.json (optional)

```json
{
  "title": "My Webinar Title",
  "description": "Optional description",
  "date": "2026-05-21",
  "speakers": ["Alice", "Bob"],
  "video_url": "/videos/my-webinar.mp4"
}
```

If `metadata.json` is omitted, the folder name is used as the title.

## Processed / Failed

- On success: folder moves to `processed/`
- On failure: folder moves to `failed/` with an `error.txt`
