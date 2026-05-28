[README.md](https://github.com/user-attachments/files/28358194/README.md)
# Webinar Library Answer Engine MVP

---

## Agent Preamble

**You are a coding agent. This file is your build specification.** Read it completely before writing any code.

**What this project is:** A retrieval-augmented answer engine over a private library of timestamped webinar transcripts. Users ask plain-English questions; the system retrieves relevant transcript chunks, sends them to Claude, and returns a grounded answer with source cards that deep-link to exact video timestamps.

**Your role:** Implement the full stack — database schema, ingestion pipeline, retrieval service, answer generation, FastAPI API, and React frontend — exactly as specified here. Do not fill gaps with assumptions; every ambiguity is resolved in this document.

**How to approach the build:** Follow the Implementation Sequence (final section) phase by phase. Complete and verify each phase before advancing. Do not skip ahead.

**What "done" looks like:**
- `POST /ask` returns a grounded answer with timestamped source cards for any question that has supporting evidence in the database.
- The ingestion script can process a fixture transcript end-to-end (segment → chunk → contextualize → embed → store).
- The React UI renders an answer, source cards, and suggested follow-up questions.
- The retrieval evaluation script reports ≥ 80% correct-source-in-top-5 against the fixture eval set.

---

## Constraints & Non-Negotiables

**Hard stops — do not build these:**
- User accounts, authentication, or permissions
- Admin CMS or media asset manager
- Video editing, highlight reels, or clip export
- Speaker diarization beyond simple speaker labels
- Multi-agent orchestration or LangChain abstractions
- Fine-tuning
- Visual frame analysis
- Complex dashboards

**Hard rules — always enforce:**
- Every answer must be grounded in retrieved chunks. No answers from model general knowledge.
- Every answer with supporting evidence must include timestamped source citations.
- When evidence is insufficient, respond with the `not_enough_evidence` flag and the fallback message — do not hallucinate.
- Do not invent product features, company policy, or terminology not present in transcripts.
- Keep code modular: one service per file, thin route handlers, logic in services.
- Log all retrieval results (query, chunks returned, scores) for debugging.
- Optimize retrieval quality before UI polish.

---

## Architecture Overview

```
Video file / transcript JSON
        ↓
[Ingestion Pipeline]
  load segments → chunk → Claude contextualize → embed → pgvector store
        ↓
[Query Pipeline]
  user question → Claude rewrite → embed → vector search + keyword search
        ↓
[Answer Pipeline]
  top-k chunks → Claude answer synthesis → structured JSON response
        ↓
[API]  POST /ask  →  React frontend
```

One Postgres database with pgvector extension serves both the chunk store and all logging tables. Claude handles contextualization, query rewriting, optional reranking, and answer synthesis. The embedding provider is swappable via env var.

---

## Stack & Environment

| Layer | Choice |
|---|---|
| Frontend | React + Vite + TypeScript |
| Backend | FastAPI (Python 3.11+) |
| Database | PostgreSQL 15+ with pgvector extension |
| LLM | Claude (`claude-sonnet-4-20250514` default) |
| Embeddings | Voyage AI (`voyage-3-large`, 1024-dim) or OpenAI (`text-embedding-3-small`, 1536-dim) |
| Transcription | Whisper / Deepgram / AssemblyAI / pre-existing JSON — ingestion script accepts any that conforms to the transcript schema |
| Local dev infra | `docker-compose.yml` for Postgres + pgvector |

### `backend/.env.example`

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

> `EMBEDDING_DIMENSION` **must match** the model: `voyage-3-large` → `1024`, `text-embedding-3-small` → `1536`. The migrations read this value at table creation time.

### `docker-compose.yml` (project root)

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

---

## Data Model

All migrations live in `backend/app/db/migrations/`. Use raw SQL files for MVP simplicity — no Alembic. Run them in order: `001_create_extension.sql`, `002_create_videos.sql`, etc.

```sql
-- 001_create_extension.sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
```

```sql
-- 002_create_videos.sql
CREATE TABLE videos (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title           TEXT NOT NULL,
    description     TEXT,
    webinar_date    DATE,
    speakers        TEXT[],
    video_url       TEXT,
    duration_seconds INTEGER,
    created_at      TIMESTAMP DEFAULT NOW()
);
```

```sql
-- 003_create_transcript_segments.sql
CREATE TABLE transcript_segments (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    video_id            UUID REFERENCES videos(id) ON DELETE CASCADE,
    start_time_seconds  FLOAT NOT NULL,
    end_time_seconds    FLOAT NOT NULL,
    speaker             TEXT,
    text                TEXT NOT NULL,
    created_at          TIMESTAMP DEFAULT NOW()
);
```

```sql
-- 004_create_chunks.sql
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
    created_at          TIMESTAMP DEFAULT NOW()
);
CREATE INDEX chunks_embedding_idx ON chunks USING ivfflat (embedding vector_cosine_ops);
CREATE INDEX chunks_raw_text_idx  ON chunks USING gin(to_tsvector('english', raw_text));
```

```sql
-- 005_create_queries.sql
CREATE TABLE queries (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_question       TEXT NOT NULL,
    rewritten_question  TEXT,
    search_terms        TEXT[],
    created_at          TIMESTAMP DEFAULT NOW()
);
```

```sql
-- 006_create_retrieval_logs.sql
CREATE TABLE retrieval_logs (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    query_id          UUID REFERENCES queries(id) ON DELETE CASCADE,
    chunk_id          UUID REFERENCES chunks(id) ON DELETE CASCADE,
    retrieval_method  TEXT,   -- "vector" | "keyword" | "merged"
    retrieval_score   FLOAT,
    rank              INTEGER,
    created_at        TIMESTAMP DEFAULT NOW()
);
```

```sql
-- 007_create_answers.sql
CREATE TABLE answers (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    query_id          UUID REFERENCES queries(id) ON DELETE CASCADE,
    answer_text       TEXT NOT NULL,
    source_chunk_ids  UUID[],
    suggested_questions TEXT[],
    confidence        TEXT,   -- "high" | "medium" | "low"
    not_enough_evidence BOOLEAN DEFAULT FALSE,
    created_at        TIMESTAMP DEFAULT NOW()
);
```

---

## Claude Prompts

All prompts are stored as `.txt` files in `backend/app/prompts/`. Services load them at startup. Template variables use `{{variable_name}}` syntax.

### `prompts/contextualize_chunk.txt`

```
You are preparing webinar transcript chunks for semantic search indexing.

Rules:
- Do not invent facts not present in the transcript or metadata.
- Do not rewrite the transcript text.
- Resolve vague pronouns and references ("this", "it", "the thing we showed") using surrounding context where possible.
- Add a short contextual header explaining what this chunk covers.

Video metadata:
Title: {{video_title}}
Date: {{webinar_date}}
Speakers: {{speaker_names}}
Time range: {{start_time}} – {{end_time}}

Transcript chunk:
{{raw_chunk_text}}

Return valid JSON only, no prose outside the JSON block:
{
  "contextual_text": "<header paragraph + transcript excerpt>",
  "summary": "<one sentence>",
  "topic_tags": ["<tag>", "..."],
  "questions_this_answers": ["<question>", "..."]
}
```

### `prompts/rewrite_query.txt`

```
You are optimizing a search query against a private company webinar transcript library.

Rewrite the user's question into a retrieval query that improves recall.
Include: exact product terms (if implied), synonyms, likely feature names, technical and plain-English phrasings.
Do not answer the question. Do not invent company policy.

User question:
{{user_question}}

Return valid JSON only:
{
  "rewritten_query": "<expanded query string>",
  "search_terms": ["<term>", "..."],
  "possible_topics": ["<topic>", "..."]
}
```

### `prompts/rerank_chunks.txt`

```
You are selecting the most useful transcript excerpts to answer a user question.

User question:
{{user_question}}

Candidate excerpts (JSON array):
{{candidate_chunks}}

Rank excerpts by usefulness. Prefer excerpts that:
- directly answer the question
- contain concrete steps, definitions, examples, or warnings
- are specific rather than vague
- do not contain only greetings, intros, or unrelated chatter

Return valid JSON only:
{
  "ranked_chunk_ids": ["<id>", "..."],
  "reasoning_summary": "<one sentence>"
}
```

### `prompts/answer_from_chunks.txt`

```
You are answering questions using a private library of company webinar transcripts.

Rules:
- Use ONLY the provided transcript excerpts. Do not use outside knowledge.
- Cite every major claim with the webinar title and timestamp.
- If excerpts do not contain sufficient evidence, set not_enough_evidence to true and answer with the fallback message.
- For "how do I" questions, structure the answer as numbered steps.
- If excerpts conflict or express uncertainty, acknowledge it.
- Keep answers practical and direct.

User question:
{{user_question}}

Retrieved transcript excerpts:
{{retrieved_chunks}}

Return valid JSON only:
{
  "answer": "<answer text, or 'I could not find enough evidence in the webinar library to answer that confidently.' if evidence is missing>",
  "sources": [
    {
      "chunk_id": "<uuid>",
      "video_title": "<title>",
      "start_time_seconds": 0,
      "end_time_seconds": 0,
      "display_time": "HH:MM:SS–HH:MM:SS",
      "speaker_names": ["<name>"],
      "snippet": "<verbatim excerpt, ≤ 2 sentences>",
      "supporting_claim": "<what claim this supports>"
    }
  ],
  "suggested_questions": ["<question>", "<question>", "<question>"],
  "confidence": "high | medium | low",
  "not_enough_evidence": false
}
```

---

## Ingestion Pipeline

**Transcript input schema** — the ingestion script accepts a JSON file conforming to:

```json
[
  {
    "start_time_seconds": 842.2,
    "end_time_seconds":   856.8,
    "speaker": "Speaker 1",
    "text": "The safest way to keep the character consistent is..."
  }
]
```

If speaker names are unavailable, use `"Speaker 1"`, `"Speaker 2"`, or `"Unknown"`.

### Step 1 — Insert video record

Insert into `videos`. Return `video_id`.

### Step 2 — Insert transcript segments

Bulk-insert all transcript JSON items into `transcript_segments` for `video_id`.

### Step 3 — Chunk segments

Sliding-window chunking over ordered segments:
- **Target:** 600 words per chunk, 120-word overlap (acceptable range: 500–700 words, 100–150 overlap)
- Preserve `start_time_seconds` from first segment in window, `end_time_seconds` from last
- Preserve all unique `speaker` values in window as `speaker_names`
- Concatenate segment texts as `raw_text`

### Step 4 — Claude contextualization

For each chunk, call Claude with `prompts/contextualize_chunk.txt`. Store response fields:
- `contextual_text` → `chunks.contextual_text`
- `summary` → `chunks.summary`
- `topic_tags` → `chunks.topic_tags`
- `questions_this_answers` → `chunks.questions_answered`

### Step 5 — Embed

Embed `contextual_text` (not `raw_text`) via `embedding_service`. Store vector in `chunks.embedding`.

The embedding input string is:
```
{video_title} | {webinar_date} | {speaker_names joined} | {summary} | {topic_tags joined} | {contextual_text}
```

### Step 6 — Persist

Insert complete chunk row. Log completion count.

### Ingestion CLI

```bash
python -m app.scripts.ingest_webinar \
  --title "Character Consistency Deep Dive" \
  --date "2026-04-12" \
  --speakers "Alice,Bob" \
  --video-url "/videos/char-consistency.mp4" \
  --transcript "/transcripts/char-consistency.json"

# Fixture run (uses bundled test transcript):
python -m app.scripts.ingest_webinar --fixture
```

**Verification:** After `--fixture`, query the database:
```sql
SELECT COUNT(*) FROM videos;           -- expect 1
SELECT COUNT(*) FROM transcript_segments; -- expect N (fixture-dependent)
SELECT COUNT(*) FROM chunks;           -- expect ~N/10 (varies by transcript length)
SELECT COUNT(*) FROM chunks WHERE embedding IS NOT NULL; -- must equal chunks count
```

---

## Retrieval Pipeline

### Service interface

```python
# backend/app/services/retrieval_service.py

from dataclasses import dataclass
from uuid import UUID

@dataclass
class RetrievedChunk:
    chunk_id:           UUID
    video_id:           UUID
    video_title:        str
    start_time_seconds: float
    end_time_seconds:   float
    raw_text:           str
    contextual_text:    str
    summary:            str
    topic_tags:         list[str]
    speaker_names:      list[str]
    retrieval_score:    float
    retrieval_method:   str   # "vector" | "keyword" | "merged"

async def retrieve_chunks(
    question: str,
    top_k: int = 8,
    query_id: UUID | None = None,
) -> list[RetrievedChunk]:
    """
    1. Rewrite question via Claude (rewrite_query prompt).
    2. Embed rewritten_query via embedding_service.
    3. Vector search: cosine similarity against chunks.embedding, limit top_k * 2.
    4. Keyword search: full-text search on raw_text + summary + topic_tags, limit top_k * 2.
    5. Merge: union results, deduplicate by chunk_id, sort by max(vector_score, keyword_score).
    6. Persist retrieval_logs for all returned chunks.
    7. Return top_k.
    """
    ...
```

**Vector search SQL:**
```sql
SELECT id, video_id, raw_text, contextual_text, summary, topic_tags, speaker_names,
       start_time_seconds, end_time_seconds,
       1 - (embedding <=> $1::vector) AS score
FROM chunks
ORDER BY embedding <=> $1::vector
LIMIT $2;
```

**Keyword search SQL:**
```sql
SELECT id, video_id, raw_text, contextual_text, summary, topic_tags, speaker_names,
       start_time_seconds, end_time_seconds,
       ts_rank(to_tsvector('english', raw_text || ' ' || summary), plainto_tsquery('english', $1)) AS score
FROM chunks
WHERE to_tsvector('english', raw_text || ' ' || summary) @@ plainto_tsquery('english', $1)
ORDER BY score DESC
LIMIT $2;
```

**Verification:**
```bash
python -m app.scripts.test_retrieval --question "How do we explain character consistency?"
# Expect: top-5 results include the fixture video, output shows scores and timestamps
```

---

## Answer Generation

### Service interface

```python
# backend/app/services/answer_service.py

from app.services.retrieval_service import RetrievedChunk
from uuid import UUID

@dataclass
class SourceCard:
    chunk_id:           UUID
    video_id:           UUID
    video_title:        str
    start_time_seconds: float
    end_time_seconds:   float
    display_time:       str   # "HH:MM:SS–HH:MM:SS"
    speaker_names:      list[str]
    snippet:            str
    supporting_claim:   str
    video_url:          str   # f"{video_url}?t={int(start_time_seconds)}"

@dataclass
class AnswerResponse:
    answer:               str
    sources:              list[SourceCard]
    suggested_questions:  list[str]
    confidence:           str   # "high" | "medium" | "low"
    not_enough_evidence:  bool

async def answer_question(
    question: str,
    chunks: list[RetrievedChunk],
    query_id: UUID,
) -> AnswerResponse:
    """
    1. If chunks is empty, return not_enough_evidence response immediately.
    2. Format chunks into the retrieved_chunks string for the prompt.
    3. Call Claude with answer_from_chunks prompt.
    4. Parse JSON response; validate against AnswerResponse shape.
    5. Resolve video_url for each source card from videos table.
    6. Persist to answers table.
    7. Return AnswerResponse.
    """
    ...
```

**Chunk formatting for prompt** — each chunk rendered as:
```
[Chunk ID: {chunk_id}]
Video: {video_title} | Date: {webinar_date} | Time: {display_time} | Speakers: {speaker_names}
Summary: {summary}
Tags: {topic_tags joined with ", "}
Transcript:
{contextual_text}
---
```

**Verification:**
```bash
# With fixture data loaded:
curl -s -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "How do we explain character consistency?"}' | python -m json.tool
# Expect: answer field non-empty, sources array non-empty with start_time_seconds values
```

---

## API Endpoints

All endpoints prefixed with `/api/v1` is optional for MVP; flat paths are acceptable. Add CORS middleware allowing all origins for local dev:

```python
# backend/app/main.py
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
```

### `POST /ask`

**Request:**
```json
{
  "question": "How do we explain character consistency in Agents?",
  "top_k": 8
}
```

`top_k` default: `8`, acceptable range: `4–20`.

**Response:**
```json
{
  "answer": "The webinars describe character consistency as a reference-first workflow...",
  "sources": [
    {
      "chunk_id": "uuid",
      "video_id": "uuid",
      "video_title": "Character Consistency Deep Dive",
      "start_time_seconds": 842,
      "end_time_seconds": 1030,
      "display_time": "00:14:02–00:17:10",
      "speaker_names": ["Alice"],
      "snippet": "The safest way to keep a character consistent is to begin with a locked reference image...",
      "supporting_claim": "Explains locked references and identity drift.",
      "video_url": "http://localhost:8000/videos/char-consistency.mp4?t=842"
    }
  ],
  "suggested_questions": [
    "What causes character drift?",
    "How should I prepare reference images?",
    "What should users avoid when prompting character consistency?"
  ],
  "confidence": "high",
  "not_enough_evidence": false
}
```

### `GET /videos`

**Response:** Array of:
```json
{
  "id": "uuid",
  "title": "Character Consistency Deep Dive",
  "webinar_date": "2026-04-12",
  "speakers": ["Alice", "Bob"],
  "duration_seconds": 3600,
  "video_url": "http://localhost:8000/videos/char-consistency.mp4"
}
```

### `GET /videos/{video_id}/chunks`

**Response:** Array of:
```json
{
  "id": "uuid",
  "start_time_seconds": 842,
  "end_time_seconds": 1030,
  "summary": "Explains how reference images reduce identity drift.",
  "topic_tags": ["character consistency", "reference images", "identity drift"],
  "speaker_names": ["Alice"]
}
```

### `GET /health`

**Response:** `{"status": "ok"}`

### `POST /ingest/video` *(optional MVP endpoint — CLI script is primary)*

**Request:**
```json
{
  "title": "Character Consistency Deep Dive",
  "description": "Internal webinar on maintaining identity across AI-generated shots.",
  "webinar_date": "2026-04-12",
  "speakers": ["Alice", "Bob"],
  "video_url": "/videos/char-consistency.mp4",
  "transcript_path": "/transcripts/char-consistency.json"
}
```

**Response:** `{"video_id": "uuid", "chunks_created": 42}`

---

## Frontend

### `types/api.ts` — single source of truth for all API types

```typescript
export interface AskRequest {
  question: string;
  top_k?: number;
}

export interface SourceCard {
  chunk_id:           string;
  video_id:           string;
  video_title:        string;
  start_time_seconds: number;
  end_time_seconds:   number;
  display_time:       string;
  speaker_names:      string[];
  snippet:            string;
  supporting_claim:   string;
  video_url:          string;
}

export interface AskResponse {
  answer:              string;
  sources:             SourceCard[];
  suggested_questions: string[];
  confidence:          "high" | "medium" | "low";
  not_enough_evidence: boolean;
}

export interface VideoSummary {
  id:               string;
  title:            string;
  webinar_date:     string;
  speakers:         string[];
  duration_seconds: number;
  video_url:        string;
}
```

### Components

```typescript
// AskBox.tsx
interface AskBoxProps {
  onSubmit: (question: string) => void;
  loading:  boolean;
}
// Renders: text input + submit button. Disables both while loading.

// AnswerPanel.tsx
interface AnswerPanelProps {
  answer:             string;
  confidence:         "high" | "medium" | "low";
  notEnoughEvidence:  boolean;
}
// Renders: answer text. If notEnoughEvidence, show fallback message.
// Show confidence badge.

// SourceCard.tsx
interface SourceCardProps {
  source: SourceCard;
}
// Renders: video title, display_time, speaker_names, snippet, "Open Clip" button.
// "Open Clip" href = source.video_url (includes ?t= param).

// SuggestedQuestions.tsx
interface SuggestedQuestionsProps {
  questions:       string[];
  onQuestionClick: (question: string) => void;
}
// Renders: clickable question chips. onClick → populates AskBox and submits.
```

### UI behavior

1. User submits question → disable input, show spinner.
2. Call `POST /ask`.
3. On success: render AnswerPanel, SourceCard list, SuggestedQuestions.
4. On `not_enough_evidence: true`: render fallback message; still render any partial source cards.
5. On network error: render error message, re-enable input.
6. Clicking a suggested question pre-fills the input and immediately submits.

### Video jump link

```typescript
// Already embedded in video_url from API. No client-side construction needed.
// Direct use: <a href={source.video_url}>Open Clip</a>
```

---

## Project Structure

```
webinar-answer-engine/
├── docker-compose.yml          # Postgres + pgvector for local dev
├── README.md                   # This file
│
├── backend/
│   ├── requirements.txt        # Python dependencies
│   ├── .env.example            # All required env vars with defaults
│   └── app/
│       ├── __init__.py
│       ├── main.py             # FastAPI app, middleware, router registration
│       ├── config.py           # Pydantic Settings; reads .env
│       │
│       ├── db/
│       │   ├── __init__.py
│       │   ├── database.py     # Async SQLAlchemy engine + session factory
│       │   ├── models.py       # SQLAlchemy ORM models (mirrors SQL schema)
│       │   ├── schemas.py      # Pydantic request/response schemas
│       │   └── migrations/     # Raw SQL files: 001_*.sql … 007_*.sql
│       │
│       ├── api/
│       │   ├── __init__.py
│       │   ├── routes_ask.py       # POST /ask
│       │   ├── routes_videos.py    # GET /videos, GET /videos/{id}/chunks
│       │   └── routes_ingest.py    # POST /ingest/video, GET /health
│       │
│       ├── services/
│       │   ├── __init__.py
│       │   ├── claude_service.py       # All Anthropic API calls; loads prompts
│       │   ├── embedding_service.py    # Voyage / OpenAI embedding; provider switch
│       │   ├── chunking_service.py     # Sliding-window chunker
│       │   ├── retrieval_service.py    # Query rewrite → embed → vector+keyword search
│       │   ├── answer_service.py       # Chunk formatting → Claude → AnswerResponse
│       │   └── ingestion_service.py    # Orchestrates steps 1–6 of ingestion pipeline
│       │
│       ├── prompts/
│       │   ├── contextualize_chunk.txt
│       │   ├── rewrite_query.txt
│       │   ├── rerank_chunks.txt
│       │   └── answer_from_chunks.txt
│       │
│       └── scripts/
│           ├── __init__.py
│           ├── ingest_webinar.py   # CLI: --title --date --video-url --transcript --fixture
│           ├── run_migrations.py   # Executes migration SQL files in order
│           └── test_retrieval.py   # Eval script; reports top-5 hit rate
│
├── backend/fixtures/
│   ├── sample_transcript.json  # Short fixture transcript (~50 segments) for testing
│   └── eval_questions.json     # Evaluation question set
│
└── frontend/
    ├── index.html
    ├── package.json            # React, Vite, TypeScript
    ├── vite.config.ts          # Proxy /ask → http://localhost:8000
    └── src/
        ├── main.tsx
        ├── App.tsx             # Single-page layout; holds question/answer state
        ├── api/
        │   └── client.ts       # fetch wrapper for POST /ask, GET /videos
        ├── components/
        │   ├── AskBox.tsx
        │   ├── AnswerPanel.tsx
        │   ├── SourceCard.tsx
        │   └── SuggestedQuestions.tsx
        └── types/
            └── api.ts          # All TypeScript types (see Frontend section)
```

Every Python directory that is a package must contain an `__init__.py`. Create them as empty files.

---

## Implementation Sequence

### Phase 1 — Infrastructure

**Build:**
- `docker-compose.yml`
- `backend/app/config.py` (Pydantic Settings, reads `.env`)
- `backend/app/db/database.py` (async SQLAlchemy engine)
- `backend/app/db/migrations/*.sql` (all 7 migration files)
- `backend/app/scripts/run_migrations.py`
- `backend/app/main.py` (bare FastAPI app with `/health`)

**Verify:**
```bash
docker-compose up -d
python -m app.scripts.run_migrations
curl http://localhost:8000/health   # → {"status": "ok"}
psql $DATABASE_URL -c "\dt"         # → all 7 tables listed
```

---

### Phase 2 — Ingestion (no Claude, no embeddings)

**Build:**
- `backend/app/db/models.py` (ORM models)
- `backend/app/services/chunking_service.py`
- `backend/app/services/ingestion_service.py` (steps 1–3 only: video → segments → chunks, no contextualization, no embedding)
- `backend/app/scripts/ingest_webinar.py` with `--fixture` flag
- `backend/fixtures/sample_transcript.json` (~50 segments)

**Verify:**
```bash
python -m app.scripts.ingest_webinar --fixture
psql $DATABASE_URL -c "SELECT COUNT(*) FROM videos;"              # 1
psql $DATABASE_URL -c "SELECT COUNT(*) FROM transcript_segments;" # ≥ 50
psql $DATABASE_URL -c "SELECT COUNT(*) FROM chunks;"              # ≥ 5
```

---

### Phase 3 — Claude Contextualization

**Build:**
- `backend/app/services/claude_service.py` with:
  - `contextualize_chunk(video_metadata, raw_text) -> dict`
  - `rewrite_query(question) -> dict`
  - `answer_from_chunks(question, formatted_chunks) -> dict`
  - `rerank_chunks(question, candidate_chunks) -> dict` *(optional, implement last)*
- `backend/app/prompts/*.txt` (all 4 prompt files)
- Update `ingestion_service.py` to call `contextualize_chunk` (step 4)

**Verify:**
```bash
python -m app.scripts.ingest_webinar --fixture
psql $DATABASE_URL -c "SELECT contextual_text IS NOT NULL, COUNT(*) FROM chunks GROUP BY 1;"
# → true | N   (all chunks have contextual_text)
```

---

### Phase 4 — Embeddings

**Build:**
- `backend/app/services/embedding_service.py`
  - `embed_text(text: str) -> list[float]`
  - Provider selected by `EMBEDDING_PROVIDER` env var
- Update `ingestion_service.py` to call `embed_text` and store `embedding` (step 5)

**Verify:**
```bash
python -m app.scripts.ingest_webinar --fixture
psql $DATABASE_URL -c "SELECT COUNT(*) FROM chunks WHERE embedding IS NOT NULL;"
# → equals total chunk count
```

---

### Phase 5 — Retrieval

**Build:**
- `backend/app/services/retrieval_service.py` (`retrieve_chunks` function as specified)
- `backend/app/scripts/test_retrieval.py`
- `backend/fixtures/eval_questions.json`

**Verify:**
```bash
python -m app.scripts.test_retrieval
# → prints per-question results + overall hit rate
# Target: ≥ 80% correct-source-in-top-5 (relax to ≥ 60% if fixture set < 5 questions)
```

---

### Phase 6 — Answer Generation & API

**Build:**
- `backend/app/services/answer_service.py` (`answer_question` function as specified)
- `backend/app/db/schemas.py` (Pydantic request/response models)
- `backend/app/api/routes_ask.py`
- `backend/app/api/routes_videos.py`
- `backend/app/api/routes_ingest.py`
- Register all routers in `main.py`; add CORS middleware

**Verify:**
```bash
curl -s -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"How do we explain character consistency?"}' | python -m json.tool
# → answer non-empty, sources array non-empty, suggested_questions has 3 items

curl http://localhost:8000/videos | python -m json.tool
# → array with 1 fixture video
```

---

### Phase 7 — Frontend

**Build:**
- `frontend/` scaffold: Vite + React + TypeScript
- `frontend/src/types/api.ts` (copy from spec above)
- `frontend/src/api/client.ts`
- All 4 components
- `frontend/src/App.tsx`
- Vite proxy: `/ask` → `http://localhost:8000`

**Verify:**
```bash
cd frontend && npm run dev
# Open http://localhost:5173
# Submit "How do we explain character consistency?"
# → Answer renders, at least 1 source card visible with "Open Clip" link
# → Clicking a suggested question submits it
```

---

## Evaluation

### `backend/fixtures/eval_questions.json`

```json
[
  {
    "question": "How do we explain character consistency?",
    "expected_video_title": "Character Consistency Deep Dive",
    "expected_terms": ["reference image", "identity drift", "locked reference"]
  },
  {
    "question": "What should users do before generating a full campaign?",
    "expected_video_title": "Workflow Planning Webinar",
    "expected_terms": ["pre-flight", "asset pack", "test pass"]
  },
  {
    "question": "Why does a character's face change between shots?",
    "expected_video_title": "Character Consistency Deep Dive",
    "expected_terms": ["identity drift", "vague description", "reference"]
  }
]
```

### `backend/app/scripts/test_retrieval.py` output format

```
Question: How do we explain character consistency?
  Top 5 videos: Character Consistency Deep Dive (×3), Workflow Planning Webinar (×2)
  Expected video in top 5: ✓
  Expected terms in top chunk: ✓ reference image, ✗ identity drift

Overall: 2/3 questions with correct source in top 5 (67%)
```

**MVP target:** correct source in top 5 for ≥ 80% of eval questions. If fixture has fewer than 5 questions, require 100%.

### Retrieval quality signals to log (for future tuning)

The `retrieval_logs` table captures method (`vector` / `keyword` / `merged`) and score per chunk per query. This data enables offline analysis of which retrieval method performs better without any additional instrumentation.
