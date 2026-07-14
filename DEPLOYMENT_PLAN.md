# Deployment Plan

## Overview

| Layer | Technology | Host |
|---|---|---|
| Frontend | React + Vite (static build) | Vercel |
| Backend API | FastAPI (Python) | Render |
| Database | PostgreSQL + pgvector | Render (managed) |
| Videos | Static files | AWS S3 (existing) |
| Embeddings | Voyage AI / OpenAI | External API |
| LLM | Anthropic Claude | External API |

---

## Architecture

```
User → Vercel (React SPA)
           ↓  API calls (HTTPS)
       Render (FastAPI)
           ↓
       Render Postgres (pgvector)
           ↓
       S3 (video files, existing)
```

---

## Phase 1 — Database (Render Postgres)

1. Create a **Render Postgres** instance (Standard plan includes pgvector support).
2. After provisioning, connect and enable the extension:
   ```sql
   CREATE EXTENSION IF NOT EXISTS vector;
   ```
3. Run all migrations from `backend/scripts/run_migrations.py` against the new database URL.
4. Note the `DATABASE_URL` (Internal URL for backend use within Render).

**Why Render Postgres:** pgvector is supported out of the box, no additional config needed.

---

## Phase 2 — Backend (Render Web Service)

### Deployment method: Docker or Python runtime

Render supports deploying directly from a GitHub repo. No Dockerfile is strictly required — Render can detect a Python app and use a build command.

**Recommended setup (no Dockerfile needed):**

- **Root directory:** `backend/`
- **Build command:** `pip install -r requirements.txt`
- **Start command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- **Plan:** Starter ($7/mo) or Standard for production

### Environment Variables to set in Render dashboard:

```
DATABASE_URL=<Render internal Postgres URL>
ANTHROPIC_API_KEY=<your key>
CLAUDE_MODEL=claude-sonnet-4-20250514
EMBEDDING_PROVIDER=voyage            # or openai
EMBEDDING_MODEL=voyage-3-large       # or text-embedding-3-small
EMBEDDING_DIMENSION=1024             # match model (1024 voyage, 1536 openai)
VOYAGE_API_KEY=<your key>            # if using Voyage
OPENAI_API_KEY=<your key>            # if using OpenAI
VIDEO_BASE_URL=https://<your-s3-bucket>.s3.amazonaws.com
API_KEY=<a strong random secret>     # for protected endpoints
```

Optional transcription keys if ingesting new webinars on the server:
```
TRANSCRIPTION_PROVIDER=deepgram      # or assemblyai / json
DEEPGRAM_API_KEY=<your key>
ASSEMBLYAI_API_KEY=<your key>
```

### CORS

Update `backend/app/main.py` to restrict `allow_origins` from `["*"]` to your Vercel domain before deploying:

```python
allow_origins=["https://your-app.vercel.app"],
```

---

## Phase 3 — Frontend (Vercel)

1. Import the repo into Vercel.
2. Set **Root Directory** to `frontend/`.
3. Vercel auto-detects Vite. Build settings:
   - **Build command:** `npm run build`
   - **Output directory:** `dist`

### Environment Variables:

```
VITE_API_BASE_URL=https://<your-render-backend>.onrender.com
```

4. Update `frontend/src/api/client.ts` to use `import.meta.env.VITE_API_BASE_URL` as the base URL rather than relying on the Vite dev proxy (which only works locally).

---

## Phase 4 — S3 Video Access

Your videos are already on S3. Ensure:

1. The S3 bucket (or a CloudFront distribution in front of it) allows public `GET` access for video URLs, **or** use pre-signed URLs if videos should be gated.
2. Set `VIDEO_BASE_URL` on Render to point to the S3 bucket or CloudFront URL.
3. The frontend `AnswerPanel` video links will resolve directly to S3 — no video traffic passes through Render.

---

## Phase 5 — Ingestion

The hot-folder watcher (`backend/scripts/watch_hot_folder.py`) is a long-running process — it is **not** suitable for Render's web service. Options:

- **Run ingestion locally** using your existing scripts and pointing them at the production `DATABASE_URL`.
- **Render Background Worker** (separate service, same repo, start command: `python -m app.scripts.watch_hot_folder`) if you want continuous ingestion in the cloud.
- For one-off batch ingestion, run `ingest_articles_batch.py` or `ingest_webinar.py` locally against the production database.

---

## Pre-Launch Checklist

- [ ] `allow_origins` in `main.py` updated to production Vercel URL
- [ ] `VITE_API_BASE_URL` set and `client.ts` reads from it
- [ ] All migrations applied to Render Postgres
- [ ] pgvector extension enabled on Render Postgres
- [ ] All required env vars set on Render
- [ ] S3 bucket CORS policy allows requests from Vercel domain
- [ ] `API_KEY` set and documented for any consumers
- [ ] Test `/health` endpoint on Render after deploy
- [ ] Test a full ask query end-to-end from Vercel → Render → Postgres → S3

---

## Estimated Monthly Cost

| Service | Plan | Cost |
|---|---|---|
| Render Web Service (backend) | Starter | ~$7/mo |
| Render Postgres | Starter (1 GB) | ~$7/mo |
| Vercel (frontend) | Hobby | Free |
| S3 (existing videos) | Pay-as-you-go | ~$1–5/mo |
| Voyage AI / Anthropic | API usage | Variable |

**Total fixed cost: ~$14–20/mo** before API usage.
