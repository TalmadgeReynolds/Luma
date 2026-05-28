# Webinar Ingestion Guide: Transcript + S3 Video

This guide walks you through ingesting a webinar transcript and linking it to a video in S3.

## Prerequisites

Before starting, ensure:
1. **Video uploaded to S3** at the correct path
2. **Transcript file ready** (`.txt`, `.vtt`, or `.transcript` format)
3. **Metadata prepared** with S3 video URL

## S3 Bucket Structure

Videos must follow this folder structure in your S3 bucket:

```
s3://luma-webinars-730335545672-us-east-1-an/
├── Luma Webinars/
│   ├── 20260210 Luma Webinar/
│   │   └── GMT20260210_Recording_1920x1080.mp4
│   ├── 20260316 Luma Webinar/
│   │   └── GMT20260316-170029_Recording_2288x1290.mp4
│   └── 20260415 Luma Webinar/
│       └── GMT20260415-165945_Recording_3008x1692.mp4
```

**Key points:**
- Folder format: `{YYYYMMDD} Luma Webinar` (e.g., `20260210 Luma Webinar`)
- Use the date from your webinar for the folder name
- Video filename should match the GMT prefix (e.g., `GMT20260210_...`)

## CDN URL Format

Your video CDN URL will be:

```
https://luma-webinars-730335545672-us-east-1-an.s3.us-east-1.amazonaws.com/Luma%20Webinars/{YYYYMMDD}%20Luma%20Webinar/{filename}.mp4
```

**Example:**
```
https://luma-webinars-730335545672-us-east-1-an.s3.us-east-1.amazonaws.com/Luma%20Webinars/20260210%20Luma%20Webinar/GMT20260210_Recording_1920x1080.mp4
```

Note the `%20` encoding for spaces — this is handled automatically.

## Step-by-Step Ingestion

### Step 1: Create Hot Folder Subfolder

Create a subfolder in `hot_folder/` named with the date (YYYYMMDD):

```bash
mkdir -p hot_folder/20260521
```

### Step 2: Add Transcript File

Copy your transcript file into the folder. Supported formats:
- `.txt` — Plain text with timestamps (M:SS format)
- `.vtt` — WebVTT format (HH:MM:SS.mmm --> HH:MM:SS.mmm)
- `.transcript` — Simple alternating timestamp/text format

```bash
cp my-webinar.transcript.txt hot_folder/20260521/
```

The watcher looks for any file matching `*transcript*` first, then any `.txt` or `.vtt` file.

### Step 3: Create metadata.json

Create a `metadata.json` file in the same folder with webinar details **including the S3 video URL**:

```json
{
  "title": "Character Consistency Deep Dive",
  "description": "Best practices for maintaining consistent character appearance in AI-generated video",
  "date": "2026-05-21",
  "speakers": ["Alice Chen", "Bob Martinez"],
  "video_url": "https://luma-webinars-730335545672-us-east-1-an.s3.us-east-1.amazonaws.com/Luma%20Webinars/20260521%20Luma%20Webinar/GMT20260521-170000_Recording_2560x1440.mp4"
}
```

**Fields:**
- `title` — (optional) Webinar title. Defaults to folder name if omitted.
- `description` — (optional) Brief description
- `date` — (optional) ISO format date (YYYY-MM-DD)
- `speakers` — (optional) List of speaker names. Auto-extracted from transcript if omitted.
- `video_url` — **(required for S3)** Full HTTPS URL to video in S3

### Step 4: Generate S3 URL (Helper Script)

To avoid manual URL construction and encoding errors, use the helper script:

```bash
python scripts/s3_url_builder.py 20260521 GMT20260521-170000_Recording_2560x1440.mp4
```

Output:
```
https://luma-webinars-730335545672-us-east-1-an.s3.us-east-1.amazonaws.com/Luma%20Webinars/20260521%20Luma%20Webinar/GMT20260521-170000_Recording_2560x1440.mp4
```

Copy and paste this into your `metadata.json`.

### Step 5: Run the Hot Folder Watcher

From the `backend/` directory:

```bash
cd backend
python -m app.scripts.watch_hot_folder
```

The watcher will:
1. Detect your `20260521/` folder
2. Parse the transcript file
3. Read `metadata.json`
4. Ingest the webinar and store the video_url in the database
5. Move the folder to `processed/` on success or `failed/` on error

Watch for this output:
```
[HOT FOLDER] Processing: 20260521
  Converting GMT20260521-170000_Recording_2560x1440.txt …
  ✓ Title   : Character Consistency Deep Dive
  ✓ Speakers: Alice Chen, Bob Martinez
  ✓ Segments: 157
  ✓ video_id=<UUID>  chunks=42
  → Moved to processed/20260521
```

### Step 6: Verify in Database

Query the database to confirm the video_url was stored:

```bash
docker compose exec db psql -U postgres webinar_mvp -c \
  "SELECT title, video_url FROM videos WHERE title = 'Character Consistency Deep Dive';"
```

Expected output:
```
 title                      | video_url
----------------------------+--------
 Character Consistency Deep |https://luma-webinars-...
```

### Step 7: Verify in App

1. Start the app (if not already running)
2. Ask a question that would pull from this webinar
3. Check that the source card displays with an inline video player
4. Click play — video should start at the relevant timestamp

## Troubleshooting

### Watcher Says "No transcript file found"

**Cause:** Filename doesn't match the pattern.

**Solution:** Transcript must be named with `transcript` in the name, or be a `.txt` file.

Examples that work:
- `GMT20260521_Recording.transcript.txt` ✓
- `webinar-transcript.txt` ✓
- `transcript.vtt` ✓
- `my-webinar.transcript` ✓

Examples that don't:
- `recording.txt` ✗
- `speakers.vtt` ✗

### Watcher Says "VTT file produced 0 segments"

**Cause:** Transcript format not recognized.

**Solution:** Ensure your file follows one of these formats:
- **Plain text** (M:SS format): timestamps like `0:15` or `1:23` on separate lines
- **WebVTT**: lines with `HH:MM:SS.mmm --> HH:MM:SS.mmm` headers
- **Simple transcript**: alternating timestamps and text lines

### Video URL Not Stored in Database

**Cause:** `metadata.json` is invalid JSON or missing `video_url` field.

**Solution:**
1. Validate JSON: `python -m json.tool hot_folder/20260521/metadata.json`
2. Ensure `video_url` field is present and is a valid HTTPS URL
3. Check for typos in field names (case-sensitive: `video_url`, not `videoUrl`)

### Video Player Doesn't Load in App

**Cause:** S3 bucket CORS not configured or URL is incorrect.

**Solution:**
1. Test video URL directly in browser: paste the URL and verify it plays
2. Check S3 bucket CORS settings: should allow GET requests from your frontend origin
3. Verify URL format: should start with `https://` and include full path with folder

## What Happens to Your Data

| File | Location | Status |
|------|----------|--------|
| Transcript | `processed/{YYYYMMDD}/` | Moved after success |
| metadata.json | `processed/{YYYYMMDD}/` | Moved after success |
| Converted JSON | `processed/{YYYYMMDD}/_transcript_converted.json` | Reference for chunks |
| On error | `failed/{YYYYMMDD}/` + `error.txt` | Review error.txt for details |

After successful ingestion, the watcher keeps the original files in `processed/` for your records. You can review metadata, transcripts, and error logs there.

## Tips

- **Batch ingestion:** Drop multiple dated folders at once; watcher processes sequentially
- **Dry run:** Check the watcher output before moving files manually
- **Video resolution:** Include resolution in filename (e.g., `2560x1440`) for clarity
- **Speaker names:** Let watcher auto-extract from `>>` cues if not in metadata
