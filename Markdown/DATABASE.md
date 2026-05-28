# DATABASE.md — Webinar Library Answer Engine

## Relationship to README.md

This document extends the README's data model with deeper database guidance: index strategy, retrieval query patterns, the processing status lifecycle, timestamp conventions, data integrity rules, and optional enhancement tables. The README is the primary build spec and the source of truth for all naming, migration approach, service file names, and architecture decisions. Where this document adds depth, it does so within the README's constraints. Where the two conflict, the README wins.

---

## Core Schema (Required)

All migrations live in `backend/app/db/migrations/`. Raw SQL files only — no Alembic. Run in order.

### `001_create_extensions.sql`

```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
```

> On AWS RDS PostgreSQL 15.2+, both extensions are available. Verify with `SHOW rds.extensions;` before running.

---

### `002_create_videos.sql`

```sql
CREATE TABLE videos (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title            TEXT NOT NULL,
    description      TEXT,
    webinar_date     DATE,
    speakers         TEXT[],
    video_url        TEXT,
    duration_seconds INTEGER,
    status           TEXT NOT NULL DEFAULT 'pending',
    created_at       TIMESTAMP DEFAULT NOW(),
    updated_at       TIMESTAMP DEFAULT NOW()
);
```

**Additions beyond README base:** `status` (processing lifecycle), `updated_at`.

**`status` values** — see [Processing Lifecycle](#processing-lifecycle).

> `video_url` stores a local path (`/videos/char-consistency.mp4`) for MVP. In Phase 2, this becomes a derived value from the `video_assets` table and the S3 presigned URL flow. See [Optional Enhancements: S3 Architecture](#s3-architecture).

---

### `003_create_transcript_segments.sql`

```sql
CREATE TABLE transcript_segments (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    video_id            UUID REFERENCES videos(id) ON DELETE CASCADE,
    start_time_seconds  FLOAT NOT NULL,
    end_time_seconds    FLOAT NOT NULL,
    speaker             TEXT,
    text                TEXT NOT NULL,
    created_at          TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_transcript_segments_video_id
    ON transcript_segments(video_id);

CREATE INDEX idx_transcript_segments_time
    ON transcript_segments(video_id, start_time_seconds, end_time_seconds);
```

---

### `004_create_chunks.sql`

```sql
-- EMBEDDING_DIMENSION must be substituted at migration time from env var.
-- The ingestion script reads EMBEDDING_DIMENSION and runs this DDL directly.
CREATE TABLE chunks (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    video_id            UUID REFERENCES videos(id) ON DELETE CASCADE,
    start_time_seconds  FLOAT NOT NULL,
    end_time_seconds    FLOAT NOT NULL,
    raw_text            TEXT NOT NULL,
    contextual_text     TEXT NOT NULL,
    summary             TEXT,
    topic_tags          TEXT[],
    questions_answered  TEXT[],
    speaker_names       TEXT[],
    embedding           VECTOR(1024),   -- replace with EMBEDDING_DIMENSION value
    chunk_index         INTEGER,        -- addition: position within video for ordering
    word_count          INTEGER,        -- addition: enables chunk size monitoring
    created_at          TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_chunks_video_id
    ON chunks(video_id);

CREATE INDEX idx_chunks_time
    ON chunks(video_id, start_time_seconds, end_time_seconds);

CREATE INDEX idx_chunks_topic_tags
    ON chunks USING GIN(topic_tags);

CREATE INDEX idx_chunks_embedding_hnsw
    ON chunks USING hnsw (embedding vector_cosine_ops);
```

**`embedding` column** stores the vector directly on `chunks`. `EMBEDDING_DIMENSION` must match the model (see Environment Variables). A separate `chunk_embeddings` table — where each row carries `provider`, `model_name`, and the vector — is a valid future migration if the team needs to store multiple embedding versions or swap providers without re-chunking; for MVP, the column-on-chunks approach is simpler.

**Additions beyond README base:** `chunk_index`, `word_count`.

---

### `005_create_queries.sql`

```sql
CREATE TABLE queries (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_question       TEXT NOT NULL,
    rewritten_question  TEXT,
    search_terms        TEXT[],
    created_at          TIMESTAMP DEFAULT NOW()
);
```

---

### `006_create_retrieval_logs.sql`

```sql
CREATE TABLE retrieval_logs (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    query_id          UUID REFERENCES queries(id) ON DELETE CASCADE,
    chunk_id          UUID REFERENCES chunks(id) ON DELETE CASCADE,
    retrieval_method  TEXT,    -- "vector" | "keyword" | "merged"
    retrieval_score   FLOAT,
    rank              INTEGER,
    created_at        TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_retrieval_logs_query_id
    ON retrieval_logs(query_id);

CREATE INDEX idx_retrieval_logs_chunk_id
    ON retrieval_logs(chunk_id);
```

---

### `007_create_answers.sql`

```sql
CREATE TABLE answers (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    query_id            UUID REFERENCES queries(id) ON DELETE CASCADE,
    answer_text         TEXT NOT NULL,
    source_chunk_ids    UUID[],
    suggested_questions TEXT[],
    confidence          TEXT,     -- "high" | "medium" | "low"
    not_enough_evidence BOOLEAN DEFAULT FALSE,
    created_at          TIMESTAMP DEFAULT NOW()
);
```

---

## Indexes

### Vector index

Use HNSW for the embedding column. HNSW builds an in-memory navigable graph; it does not require a training pass (unlike IVFFlat) and delivers better recall at lower dataset sizes. IVFFlat is a reasonable alternative at very large scale (millions of chunks) where its lower memory footprint matters more.

```sql
-- Already included in 004_create_chunks.sql.
-- Repeated here for reference.
CREATE INDEX idx_chunks_embedding_hnsw
    ON chunks USING hnsw (embedding vector_cosine_ops);
```

IVFFlat alternative (large-scale only):

```sql
CREATE INDEX idx_chunks_embedding_ivfflat
    ON chunks USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);
```

### Full-text search index

Migration `009_create_chunk_search.sql` (see [Optional Enhancements](#optional-enhancements)) adds a dedicated `chunk_search` table with a GIN-indexed `tsvector` column. For the MVP core, the README's inline `to_tsvector` approach in keyword search queries is sufficient. The materialized `chunk_search` table is the upgrade path for performance once the dataset grows.

### B-tree indexes

Already defined in the migration files above:
- `transcript_segments(video_id)`
- `transcript_segments(video_id, start_time_seconds, end_time_seconds)`
- `chunks(video_id)`
- `chunks(video_id, start_time_seconds, end_time_seconds)`
- `retrieval_logs(query_id)`
- `retrieval_logs(chunk_id)`

### GIN index for arrays

Already defined in `004_create_chunks.sql`:
- `chunks(topic_tags)` — enables fast containment queries against tag arrays

---

## Retrieval Queries

These queries use the README's table structure. Bind parameters use SQLAlchemy-style `:name` notation; swap to `$1`/`$2` for asyncpg direct queries.

### Vector search

```sql
SELECT
    c.id,
    c.video_id,
    c.start_time_seconds,
    c.end_time_seconds,
    c.raw_text,
    c.contextual_text,
    c.summary,
    c.topic_tags,
    c.speaker_names,
    1 - (c.embedding <=> :query_embedding) AS score
FROM chunks c
ORDER BY c.embedding <=> :query_embedding
LIMIT :top_k;
```

### Keyword search (inline tsvector — MVP default)

```sql
SELECT
    c.id,
    c.video_id,
    c.start_time_seconds,
    c.end_time_seconds,
    c.raw_text,
    c.contextual_text,
    c.summary,
    c.topic_tags,
    c.speaker_names,
    ts_rank(
        to_tsvector('english', c.raw_text || ' ' || coalesce(c.summary, '')),
        plainto_tsquery('english', :query)
    ) AS score
FROM chunks c
WHERE to_tsvector('english', c.raw_text || ' ' || coalesce(c.summary, ''))
      @@ plainto_tsquery('english', :query)
ORDER BY score DESC
LIMIT :top_k;
```

If `009_create_chunk_search.sql` has been applied, use this higher-performance variant instead:

```sql
SELECT
    c.id,
    c.video_id,
    c.start_time_seconds,
    c.end_time_seconds,
    c.raw_text,
    c.contextual_text,
    c.summary,
    c.topic_tags,
    c.speaker_names,
    ts_rank(cs.search_vector, plainto_tsquery('english', :query)) AS score
FROM chunk_search cs
JOIN chunks c ON c.id = cs.chunk_id
WHERE cs.search_vector @@ plainto_tsquery('english', :query)
ORDER BY score DESC
LIMIT :top_k;
```

### Hybrid merge pattern

`retrieval_service.py` implements this in Python:

```
1. Run vector search → up to top_k * 2 results.
2. Run keyword search → up to top_k * 2 results.
3. Union both result sets.
4. Deduplicate by chunk_id, keeping the higher score for any duplicate.
5. Sort descending by score.
6. Return top_k chunks.
7. Log all returned chunks to retrieval_logs with method = "vector", "keyword", or "merged".
```

---

## Processing Lifecycle

`videos.status` tracks where each webinar is in the ingestion pipeline.

```
pending → uploaded → transcribed → chunked → contextualized → embedded → ready
                                                                        ↘
                                                                        failed
```

Update after each pipeline stage:

```sql
UPDATE videos
SET status = 'transcribed', updated_at = NOW()
WHERE id = :video_id;
```

Any unrecoverable error at any stage → set `status = 'failed'`. Only videos with `status = 'ready'` should be served to the retrieval pipeline.

**Status definitions:**

| Status | Meaning |
|---|---|
| `pending` | Record created, no media yet |
| `uploaded` | Video file registered (local path or S3 asset recorded) |
| `transcribed` | `transcript_segments` rows exist |
| `chunked` | `chunks` rows exist (raw_text populated) |
| `contextualized` | `chunks.contextual_text`, `summary`, `topic_tags`, `questions_answered` populated |
| `embedded` | `chunks.embedding` populated for all chunks |
| `ready` | Chunk search index populated (if using `chunk_search`); video available to query |
| `failed` | Pipeline error; check application logs |

---

## Timestamp Conventions

Store all timestamps as seconds (FLOAT). Display as timecode in the frontend.

```
842.5 → stored as 842.5
842.5 → displayed as 00:14:02
```

Seconds are sortable, comparable, queryable, and map directly to HTML `<video>` seek operations and URL `?t=` parameters. Do not store timecodes as strings. Do not parse timecode strings in SQL.

---

## Data Integrity Rules

### `videos`

Each row must have: `title`, `status`.
`video_url` is nullable in the README schema but should be populated before `status` reaches `uploaded`.

### `transcript_segments`

Each row must have: `video_id`, `start_time_seconds`, `end_time_seconds`, `text`.
`end_time_seconds` must be greater than `start_time_seconds`.

### `chunks`

Each row must have: `video_id`, `start_time_seconds`, `end_time_seconds`, `raw_text`.
`chunk_index` must be set at creation time.
`contextual_text`, `summary`, `topic_tags`, `questions_answered` must be populated before `videos.status` advances to `contextualized`.
`embedding` must be non-null before `videos.status` advances to `embedded`.

### `retrieval_logs`

Each row must have: `query_id`, `chunk_id`, `retrieval_method`.
Log before returning chunks to the answer service — not after.

### `answers`

Each row must have: `query_id`, `answer_text`.
`source_chunk_ids` should be populated for all answers where `not_enough_evidence = false`.
`confidence` must be `'high'`, `'medium'`, or `'low'`.

---

## Optional Enhancements

Migrations 008–010 are not required for the core answer loop. Add them once the core is working.

---

### `008_create_video_assets.sql` — S3 asset tracking

Tracks each S3 media object associated with a video. One webinar may have an original video, a proxy video, an audio extraction, a transcript JSON export, captions, and a thumbnail. This table stores them all without requiring schema changes per asset type.

```sql
CREATE TABLE video_assets (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    video_id       UUID NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    asset_type     TEXT NOT NULL,
    s3_bucket      TEXT NOT NULL,
    s3_key         TEXT NOT NULL,
    s3_region      TEXT,
    s3_version_id  TEXT,
    etag           TEXT,
    content_type   TEXT,
    file_size_bytes BIGINT,
    created_at     TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_video_assets_video_id
    ON video_assets(video_id);

CREATE INDEX idx_video_assets_type
    ON video_assets(video_id, asset_type);
```

**`asset_type` values:**

```
original_video
proxy_video
audio_wav
transcript_json
captions_vtt
thumbnail
clip_export
```

Each `video_assets` row must have: `video_id`, `asset_type`, `s3_bucket`, `s3_key`.

---

### `009_create_chunk_search.sql` — materialized tsvector

Stores a precomputed full-text search vector per chunk. Faster than inline `to_tsvector` at query time once the chunk table is large. Populated from `raw_text`, `contextual_text`, `summary`, `topic_tags`, and the parent video `title`.

```sql
CREATE TABLE chunk_search (
    chunk_id      UUID PRIMARY KEY REFERENCES chunks(id) ON DELETE CASCADE,
    search_vector TSVECTOR
);

CREATE INDEX idx_chunk_search_vector
    ON chunk_search USING GIN(search_vector);
```

Populate or refresh after ingestion:

```sql
INSERT INTO chunk_search (chunk_id, search_vector)
SELECT
    c.id,
    to_tsvector(
        'english',
        coalesce(v.title, '') || ' ' ||
        coalesce(c.summary, '') || ' ' ||
        coalesce(c.contextual_text, '') || ' ' ||
        coalesce(c.raw_text, '') || ' ' ||
        coalesce(array_to_string(c.topic_tags, ' '), '')
    )
FROM chunks c
JOIN videos v ON v.id = c.video_id
ON CONFLICT (chunk_id)
DO UPDATE SET search_vector = EXCLUDED.search_vector;
```

Run this after each ingestion batch. Once this migration is applied, switch `retrieval_service.py` to the `chunk_search`-backed keyword query in the [Retrieval Queries](#retrieval-queries) section above.

---

### `010_create_feedback.sql` — user feedback

Stores per-answer user feedback. Useful for identifying bad retrieval results and calibrating the eval set.

```sql
CREATE TABLE feedback (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    answer_id     UUID REFERENCES answers(id) ON DELETE CASCADE,
    query_id      UUID REFERENCES queries(id) ON DELETE CASCADE,
    rating        TEXT,
    feedback_text TEXT,
    created_at    TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_feedback_answer_id
    ON feedback(answer_id);
```

**`rating` values:**

```
thumbs_up
thumbs_down
wrong_source
answer_too_vague
missing_context
```

---

## S3 Architecture

**This is Phase 2.** The MVP starts with local video paths (`video_url` on the `videos` table, served by FastAPI). Move to S3 when the team is ready to stop shipping video files alongside the application.

### Bucket strategy

One private bucket for the MVP:

```
company-webinar-library-mvp
```

Keep S3 Block Public Access enabled. Use S3 default server-side encryption. Do not generate public URLs. The frontend never talks to S3 directly.

### Object key strategy

```
raw/{video_id}/source.mp4
proxy/{video_id}/720p.mp4
audio/{video_id}/audio.wav
transcripts/{video_id}/transcript.json
captions/{video_id}/captions.vtt
thumbnails/{video_id}/thumbnail.jpg
clips/{video_id}/{clip_id}.mp4
```

Store the bucket name and key in `video_assets`. Do not construct full S3 URIs in the database — compute them in the service layer.

### Presigned URL flow

The frontend never holds a permanent video URL in S3 mode. When a user clicks a source card:

```
User clicks source card
    ↓
React calls GET /videos/{video_id}/playback-url?start_time=842
    ↓
FastAPI queries video_assets for video_id, prefers asset_type = 'proxy_video', falls back to 'original_video'
    ↓
FastAPI generates a presigned S3 URL (TTL = PRESIGNED_URL_EXPIRATION_SECONDS)
    ↓
FastAPI returns { video_id, start_time_seconds, asset_type, playback_url }
    ↓
React opens video player at timestamp
```

Response shape:

```json
{
  "video_id": "uuid",
  "start_time_seconds": 842,
  "asset_type": "proxy_video",
  "playback_url": "https://s3.amazonaws.com/..."
}
```

Always prefer `proxy_video` for playback. Fall back to `original_video`. Do not stream uncompressed originals if a proxy exists.

### S3 migration path for `video_url`

Once `video_assets` is populated, `videos.video_url` can be deprecated. The `GET /videos` endpoint should derive the playback URL from `video_assets` + presigned URL generation rather than returning a raw path. During transition, keep `video_url` populated as a fallback.

### Optional services (add when S3 is live)

The README defines the core service files. These two are additions for S3 mode:

| File | Responsibility |
|---|---|
| `s3_service.py` | Generate presigned playback URLs, check object existence, retrieve best asset by type (proxy → original fallback) |
| `playback_service.py` | Serve the `GET /videos/{video_id}/playback-url` endpoint logic; wraps `s3_service.py` |

The React frontend must never hold AWS credentials. All S3 access routes through the FastAPI backend.

---

## Environment Variables

### Core (all required)

```env
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/webinar_mvp

ANTHROPIC_API_KEY=your_anthropic_key_here
CLAUDE_MODEL=claude-sonnet-4-20250514

EMBEDDING_PROVIDER=voyage          # "voyage" | "openai"
EMBEDDING_MODEL=voyage-3-large     # voyage-3-large | text-embedding-3-small
EMBEDDING_DIMENSION=1024           # 1024 for voyage-3-large | 1536 for text-embedding-3-small

VOYAGE_API_KEY=your_voyage_key_here
OPENAI_API_KEY=your_openai_key_here   # required if EMBEDDING_PROVIDER=openai

TRANSCRIPTION_PROVIDER=whisper     # whisper | deepgram | assemblyai | json
VIDEO_BASE_URL=http://localhost:8000/videos
```

`EMBEDDING_DIMENSION` must match the model. The migration for `chunks` reads this value at table creation time.

### S3 / AWS (required only for Phase 2 S3 migration)

```env
AWS_REGION=us-east-1
S3_VIDEO_BUCKET=company-webinar-library-mvp
PRESIGNED_URL_EXPIRATION_SECONDS=900
```

Add these when deploying `008_create_video_assets.sql` and enabling the S3 playback flow. They are not referenced by any core MVP service.

---

## Local Development

Use the `docker-compose.yml` in the project root (defined in the README):

```yaml
version: "3.9"
services:
  db:
    image: pgvector/pgvector:pg15
    environment:
      POSTGRES_DB: webinar_mvp
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
volumes:
  pgdata:
```

```bash
docker-compose up -d
python -m app.scripts.run_migrations
psql $DATABASE_URL -c "\dt"   # → all tables listed
```

For RDS: swap `DATABASE_URL` to the RDS endpoint. Put RDS in a private VPC subnet. Allow inbound traffic only from the backend security group. Store credentials in environment variables or AWS Secrets Manager — not in source code.

---

## Migration Order

### Core (required)

| File | Table | Notes |
|---|---|---|
| `001_create_extensions.sql` | — | `vector`, `uuid-ossp` |
| `002_create_videos.sql` | `videos` | Includes `status`, `updated_at` |
| `003_create_transcript_segments.sql` | `transcript_segments` | |
| `004_create_chunks.sql` | `chunks` | Includes `chunk_index`, `word_count`, HNSW index |
| `005_create_queries.sql` | `queries` | |
| `006_create_retrieval_logs.sql` | `retrieval_logs` | |
| `007_create_answers.sql` | `answers` | |

### Optional enhancements (add after core answer loop is working)

| File | Table | Notes |
|---|---|---|
| `008_create_video_assets.sql` | `video_assets` | Required for S3 Phase 2 |
| `009_create_chunk_search.sql` | `chunk_search` | Upgrade keyword search performance |
| `010_create_feedback.sql` | `feedback` | User feedback collection |

Run migrations via:

```bash
python -m app.scripts.run_migrations
```

The script in `backend/app/scripts/run_migrations.py` executes `.sql` files from `backend/app/db/migrations/` in lexicographic order.
