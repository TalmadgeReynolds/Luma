# End-to-End Webinar Ingestion Workflow

This document walks through the complete process: from uploading a video to S3 to verifying it's searchable in the knowledge base.

## Quick Reference

```bash
# 1. Upload video to S3 (via AWS Console or CLI)
# 2. Generate S3 URL
python scripts/s3_url_builder.py 20260521 GMT20260521-170000_Recording_2560x1440.mp4

# 3. Create hot folder with transcript + metadata
mkdir -p hot_folder/20260521
cp my-transcript.txt hot_folder/20260521/
# Create metadata.json with video_url from step 2

# 4. Run watcher to ingest
cd backend
python -m app.scripts.watch_hot_folder

# 5. Verify in database
docker compose exec db psql -U postgres webinar_mvp \
  -c "SELECT title, video_url FROM videos WHERE content_type='webinar' ORDER BY created_at DESC LIMIT 1;"

# 6. Test in app
# Ask a question that would pull from this webinar
# Verify source card shows inline video player with correct timestamps
```

---

## Detailed Steps

### Pre-Ingestion: Upload Video to S3

1. **Via AWS Console:**
   - Open S3 bucket: `luma-webinars-730335545672-us-east-1-an`
   - Navigate to or create: `Luma Webinars/20260521 Luma Webinar/`
   - Upload: `GMT20260521-170000_Recording_2560x1440.mp4`

2. **Via AWS CLI:**
   ```bash
   aws s3 cp GMT20260521-170000_Recording_2560x1440.mp4 \
     s3://luma-webinars-730335545672-us-east-1-an/Luma\ Webinars/20260521\ Luma\ Webinar/
   ```

3. **Verify upload:**
   - In AWS Console: file appears in the folder
   - File size matches local file
   - Make note of exact filename (case-sensitive)

### Step 1: Generate S3 URL

Use the helper script to create a properly formatted CDN URL:

```bash
python scripts/s3_url_builder.py 20260521 GMT20260521-170000_Recording_2560x1440.mp4
```

Output:
```
https://luma-webinars-730335545672-us-east-1-an.s3.us-east-1.amazonaws.com/Luma%20Webinars/20260521%20Luma%20Webinar/GMT20260521-170000_Recording_2560x1440.mp4
```

**Copy this URL** — you'll paste it into metadata.json.

### Step 2: Prepare Transcript File

Ensure your transcript is in one of the supported formats:

- **Plain text (.txt):** timestamps in M:SS format, one per line
  ```
  0:15
  Let's start with the basics.
  1:23
  Here's how you do it:
  ```

- **WebVTT (.vtt):** standard WebVTT format with `-->` separators
  ```
  00:15.000 --> 00:30.000
  Speaker: Let's start with the basics.
  ```

- **Simple transcript (.transcript):** plain text with speaker markers (`>>`)

Save as: `hot_folder/20260521/<filename>.txt` (any name with "transcript" in it, or just `.txt`)

### Step 3: Create Hot Folder

```bash
mkdir -p hot_folder/20260521
cp your-transcript.txt hot_folder/20260521/
```

Folder name must be YYYYMMDD (e.g., `20260521` for May 21, 2026).

### Step 4: Create metadata.json

Create `hot_folder/20260521/metadata.json`:

```json
{
  "title": "Character Consistency Deep Dive",
  "description": "Best practices for maintaining character appearance in AI-generated video",
  "date": "2026-05-21",
  "speakers": ["Alice Chen", "Bob Martinez"],
  "video_url": "https://luma-webinars-730335545672-us-east-1-an.s3.us-east-1.amazonaws.com/Luma%20Webinars/20260521%20Luma%20Webinar/GMT20260521-170000_Recording_2560x1440.mp4"
}
```

**Important:**
- `video_url` must be the full HTTPS URL (from Step 1)
- JSON must be valid (use `python -m json.tool metadata.json` to check)
- All fields except `video_url` are optional

### Step 5: Run Hot Folder Watcher

From the `backend/` directory:

```bash
cd /workspaces/Luma/backend
python -m app.scripts.watch_hot_folder
```

The watcher will monitor `hot_folder/` and process your folder. Expected output:

```
[HOT FOLDER] Watching: /workspaces/Luma/hot_folder
  Drop a webinar subfolder with a .vtt transcript inside.
  Press Ctrl+C to stop.

  [queued] 20260521 (processing in 3s …)

============================================================
[HOT FOLDER] Processing: 20260521
============================================================
✓ Loaded prompt: contextualize_chunk
✓ Initialized OpenAI client (model: text-embedding-3-small)
  Converting your-transcript.txt …
  ✓ Title   : Character Consistency Deep Dive
  ✓ Speakers: Alice Chen, Bob Martinez
  ✓ Date    : 2026-05-21
  ✓ Segments: 157
  ✓ Chunks  : 42
  ✓ Embeddings generated
  ✓ video_id=<UUID>  chunks=42
  → Moved to processed/20260521
```

**Key indicators of success:**
- ✓ Title, speakers, segments visible
- ✓ Chunks generated (should be > 0)
- ✓ Embeddings generated (calls Claude + embedding model)
- ✓ Folder moved to `processed/`

**If it fails:**
- Check `failed/20260521/error.txt` for details
- Fix the issue and move the folder back to `hot_folder/`
- Rerun watcher

### Step 6: Verify in Database

Query the database to confirm video_url was stored:

```bash
docker compose exec db psql -U postgres webinar_mvp -c \
  "SELECT id, title, video_url FROM videos WHERE content_type='webinar' ORDER BY created_at DESC LIMIT 1;"
```

Expected output:
```
                  id                  |           title            |                                               video_url                                                |
--------------------------------------+----------------------------+-----------------------------------------------------------------------------------------------------------
 f1234567-89ab-cdef-0123-456789abcdef | Character Consistency Deep | https://luma-webinars-730335545672-us-east-1-an.s3.us-east-1.amazonaws.com/Luma%20Webinars/...
```

**Check:**
- ✓ `title` matches what you set in metadata.json
- ✓ `video_url` starts with `https://`
- ✓ URL contains your S3 bucket name and folder structure

### Step 7: Test Inline Video Player in App

1. Make sure backend and frontend are running:
   ```bash
   # In project root:
   ./run
   ```

2. Open the app: http://localhost:5173

3. Ask a question that would pull from your webinar:
   ```
   "What are the best practices for character consistency?"
   ```

4. Check the source card:
   - ✓ Title of webinar appears
   - ✓ Timestamp shows (e.g., `00:15–00:45`)
   - ✓ **Inline `<video>` player appears** (not just a link)
   - ✓ Click play — video starts at the correct timestamp
   - ✓ Relevant excerpt of transcript visible

5. If video doesn't load:
   - Open browser DevTools → Network tab
   - Check video request: should show 200 (success)
   - If 403 (Forbidden): S3 bucket permissions or CORS misconfigured
   - If 404: URL in database is incorrect

### Step 8: Verify Full Search Flow

Once verified, test end-to-end:

```bash
# 1. Ask a question about the webinar topic
Question: "How do I maintain character consistency?"

# 2. Check answer includes content from your webinar
Answer: Should cite specific practices from your video

# 3. Check sources list
Sources: Should include your webinar with inline video player

# 4. Play the video
Video: Should auto-seek to relevant timestamp
```

---

## Troubleshooting

| Issue | Cause | Fix |
|-------|-------|-----|
| Watcher can't find transcript | Filename doesn't match pattern | Name file with "transcript" in it or use `.txt` |
| "0 segments" error | Transcript format not recognized | Check format: M:SS timestamps or proper WebVTT |
| metadata.json not read | JSON syntax error | Validate: `python -m json.tool metadata.json` |
| video_url not in DB | metadata.json missing `video_url` | Add full HTTPS URL to metadata.json |
| Video doesn't play | URL incorrect or S3 CORS misconfigured | Test URL directly in browser; check S3 CORS |
| Chunks generated but video_url null | Old ingestion code before S3 support | Re-ingest with updated code |

---

## File Locations After Success

```
hot_folder/
  processed/20260521/
    your-transcript.txt                  ← original file
    metadata.json                        ← original metadata
    _transcript_converted.json           ← segments used for ingestion
    
Database (videos table):
  id: <UUID>
  title: Character Consistency Deep Dive
  video_url: https://...mp4               ← stored for retrieval
  status: embedded                        ← ready for search
  chunk_count: 42
```

The transcript, metadata, and converted JSON are kept in `processed/` for your reference.

---

## Next Steps

- **Batch process:** Drop multiple dated folders; watcher processes sequentially
- **Monitor searches:** Ask questions and verify new webinar appears in results
- **Build taxonomy:** Use consistent naming and speaker lists for better search
- **Update article ingestion:** Similar process for written content in learning center
