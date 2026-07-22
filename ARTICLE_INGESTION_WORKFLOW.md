# Article Ingestion Workflow

This document walks through the complete process for ingesting Luma Learning Center articles into the knowledge base.

## Quick Reference

```bash
# 1. (One-time) Export articles from the Learning Center
cd scripts/luma_learning_center_plain_text_exporter
pip install -r requirements.txt
python export_luma_learning_center_articles.py

# 2. Run the batch ingestion from the backend directory
cd ../../backend
python -m app.scripts.ingest_articles_batch \
    --manifest ../scripts/luma_learning_center_plain_text_exporter/luma_learning_center_plain_text_articles/manifest.csv \
    --continue-on-error

# 3. Verify in database
docker compose exec db psql -U postgres webinar_mvp \
  -c "SELECT title, source_url FROM videos WHERE content_type='article' ORDER BY created_at DESC LIMIT 5;"
```

---

## Detailed Steps

### Step 1: Export Articles (if not already done)

The export script scrapes the Luma Learning Center and saves each article as a plain-text file along with a `manifest.csv`.

```bash
cd scripts/luma_learning_center_plain_text_exporter
pip install -r requirements.txt
python export_luma_learning_center_articles.py
```

After a successful run the folder `luma_learning_center_plain_text_articles/` will contain:

```
luma_learning_center_plain_text_articles/
  01_the-luma-agent.txt
  02_just-ask-the-agent.txt
  ...
  manifest.csv          ← index, title, url, filename, word_count, status
```

Rows in `manifest.csv` with `status=ok` have a corresponding `.txt` file. Rows with `status=error: …` indicate that the scrape failed for that URL and will be automatically skipped during ingestion.

**If the page renders client-side content** (and fewer articles are found than expected), add the `--browser` flag:

```bash
python -m playwright install chromium
python export_luma_learning_center_articles.py --browser
```

The 28 articles already scraped in `luma_learning_center_plain_text_articles/` are committed and ready to use — you can skip this step and go straight to Step 2.

---

### Step 2: Start the App Stack

The ingestion script connects to the database, so Postgres must be running:

```bash
# From the project root:
./run --no-backend --no-frontend --no-watch
```

Or start only the database container directly:

```bash
docker compose up -d db
```

---

### Step 3: Run Batch Ingestion

From the `backend/` directory:

```bash
cd backend
python -m app.scripts.ingest_articles_batch \
    --manifest ../scripts/luma_learning_center_plain_text_exporter/luma_learning_center_plain_text_articles/manifest.csv \
    --continue-on-error
```

#### What the script does

1. Reads every row in `manifest.csv`.
2. **Skips** rows whose `status` column is not `ok` (e.g. scrape errors).
3. **Skips** articles already present in the database (idempotent by default; controlled by `--skip-existing`).
4. For each remaining article: parses the text → chunks → Claude contextualization → embeddings → stored in Postgres.

#### Expected output

```
Found 28 articles in manifest

[1/28] Processing: The Luma Agent
  ✓ Success: 4 chunks created

[2/28] Processing: Just Ask The Agent
  ✓ Success: 6 chunks created

...

================================================================================
BATCH INGESTION SUMMARY
================================================================================
Total articles: 28
  ✓ Successful: 28
  ⊙ Skipped: 0
  ✗ Failed: 0
Total chunks created: 147
================================================================================
```

If `--continue-on-error` is omitted the script stops on the first error.

#### CLI flags

| Flag | Default | Description |
|------|---------|-------------|
| `--manifest PATH` | *(required)* | Path to `manifest.csv` |
| `--continue-on-error` | off | Keep going after an article fails |
| `--skip-existing` | on | Skip URLs already in the database |
| `--log-file PATH` | *(none)* | Append a timestamped log to this file |

---

### Step 4: Verify in Database

```bash
docker compose exec db psql -U postgres webinar_mvp \
  -c "SELECT title, source_url, status FROM videos WHERE content_type='article' ORDER BY created_at DESC LIMIT 10;"
```

All rows should show `status = embedded`.

To check chunk counts:

```bash
docker compose exec db psql -U postgres webinar_mvp -c "
SELECT v.title, COUNT(c.id) AS chunks
FROM videos v
JOIN chunks c ON c.video_id = v.id
WHERE v.content_type = 'article'
GROUP BY v.title
ORDER BY v.title;
"
```

---

### Step 5: Test in the App

1. Start the full stack:
   ```bash
   ./run
   ```
2. Open the app at http://localhost:5173.
3. Ask a question that should be answered by a Learning Center article, e.g.:
   ```
   How do I maintain character consistency across multiple images?
   ```
4. The answer should cite a Learning Center article and include a link back to the source URL.

---

## Ingesting a Single Article

To ingest one article by its manifest index:

```bash
cd backend
python -m app.scripts.ingest_article --article-id 1
```

To ingest a custom article file:

```bash
cd backend
python -m app.scripts.ingest_article \
    --title "My Custom Article" \
    --url "https://lumalabs.ai/learning-center/articles/my-article" \
    --date "2026-03-09" \
    --file /path/to/article.txt
```

---

## Re-running After a Partial Failure

The ingestion is idempotent. Re-run the same command — articles already stored in the database are automatically skipped:

```bash
cd backend
python -m app.scripts.ingest_articles_batch \
    --manifest ../scripts/luma_learning_center_plain_text_exporter/luma_learning_center_plain_text_articles/manifest.csv \
    --continue-on-error
```

---

## Troubleshooting

| Issue | Cause | Fix |
|-------|-------|-----|
| `Manifest not found` | Wrong path to `manifest.csv` | Use the absolute path or the relative path shown above |
| `Article file not found` | Export was not run, or ran from wrong directory | Run `export_luma_learning_center_articles.py` first |
| `status=error: …` rows skipped | Scrape failed for those URLs | Re-run the export script; those rows will be retried |
| Connection refused on DB | Postgres not running | Run `docker compose up -d db` |
| Claude / embedding API errors | Missing API keys | Check `backend/.env` against `backend/.env.example` |
| Article already ingested | `--skip-existing` is on | Normal behavior; pass `--skip-existing false` to force re-ingest |
