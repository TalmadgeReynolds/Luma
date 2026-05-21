# API_CONTRACT.md — Webinar Library Answer Engine

## Relationship to Other Documents

This document is the frontend-backend interface contract. A frontend developer reads this to build against the API; a backend developer implements against it. It does not repeat what other documents already define:

- **README.md** — source of truth for all architecture, naming, endpoints, schemas, service interfaces, project structure, and implementation sequence. README wins on all conflicts.
- **DATABASE.md** — schema definitions, indexes, processing lifecycle, S3 architecture, presigned URL flow, and S3 env vars.
- **RAG_PIPELINE.md** — retrieval science, confidence calibration rules, failure behavior patterns, `not_enough_evidence` rules, and the debug endpoint response shape.

Where this document adds fields not in the README, each addition is explicitly marked **Addition — not in README**.

---

## Endpoint Summary

| Method | Path | Priority | Description |
|---|---|---|---|
| `GET` | `/health` | MVP core | Backend liveness check |
| `POST` | `/ask` | MVP core | Submit question; receive grounded answer with source cards |
| `GET` | `/videos` | MVP core | List available webinars |
| `GET` | `/videos/{video_id}/chunks` | MVP core | List chunks for a webinar (dev/debug) |
| `POST` | `/feedback` | MVP core | Submit rating on an answer |
| `GET` | `/videos/{video_id}` | Optional enhancement | Single webinar detail view |
| `GET` | `/videos/{video_id}/playback-url` | Optional enhancement | S3 presigned playback URL — see DATABASE.md → S3 Architecture |
| `POST` | `/ingest/video` | Optional / CLI primary | API ingestion — CLI script is the primary path (see README → Ingestion CLI) |
| `GET` | `/debug/queries/{query_id}` | Dev only | RAG trace for a query — see RAG_PIPELINE.md → Debug Endpoint |

**Base URL (local dev):** `http://localhost:8000`

**Content-Type:** `application/json` for all request and response bodies.

---

## Standard Error Response

All error responses use this shape. This contract is not defined in any other document.

```json
{
  "error": {
    "code": "VIDEO_NOT_FOUND",
    "message": "No video was found for the provided video_id.",
    "details": {
      "video_id": "2bb9f7e1-3c8e-4ad5-9e45-925f9f64bb41"
    }
  }
}
```

### Error codes

| Code | When |
|---|---|
| `BAD_REQUEST` | Malformed request body |
| `VALIDATION_ERROR` | Pydantic validation failed |
| `VIDEO_NOT_FOUND` | `video_id` does not exist |
| `CHUNK_NOT_FOUND` | `chunk_id` does not exist |
| `QUERY_NOT_FOUND` | `query_id` does not exist |
| `ANSWER_NOT_FOUND` | `answer_id` does not exist |
| `NO_PLAYBACK_ASSET` | No playable S3 asset for this video |
| `S3_PRESIGN_FAILED` | S3 presigned URL generation failed |
| `INGESTION_FAILED` | Ingestion pipeline error |
| `TRANSCRIPT_INVALID` | Transcript JSON does not conform to schema |
| `RAG_RETRIEVAL_FAILED` | Vector or keyword search error |
| `CLAUDE_REQUEST_FAILED` | Anthropic API call failed |
| `EMBEDDING_REQUEST_FAILED` | Embedding provider call failed |
| `DATABASE_ERROR` | Postgres error |
| `INTERNAL_SERVER_ERROR` | Unhandled exception |

---

## Core Endpoints

### GET /health

Backend liveness check. Registered in `backend/app/main.py`.

**Response — 200 OK:**

```json
{
  "status": "ok"
}
```

> **Addition — not in README:** `service` and `version` fields are useful for diagnostics but not required by the README contract. Backends may include them:
> ```json
> { "status": "ok", "service": "webinar-answer-engine", "version": "0.1.0" }
> ```

---

### POST /ask

Main MVP endpoint. Accepts a user question; returns a grounded Claude answer with timestamped source cards. Implemented in `backend/app/api/routes_ask.py`.

**Request:**

```json
{
  "question": "How do we explain character consistency in Agents?",
  "top_k": 8
}
```

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `question` | `string` | Yes | — | Plain-English user question; min length 1 |
| `top_k` | `integer` | No | `8` | Range: 4–20. Number of chunks sent to answer synthesis. |
| `filters` | `object` | No | `null` | **Addition — not in README.** Accepted but ignored until implemented. See schema below. |

**Successful response — 200 OK:**

```json
{
  "answer": "The webinars describe character consistency as a reference-first workflow...",
  "sources": [
    {
      "chunk_id": "39e4dd75-b5a6-42cd-8c38-516b7f0c8f62",
      "video_id": "ccf5b43f-b4d5-4609-96e7-1d9a7e197948",
      "video_title": "Character Consistency Deep Dive",
      "start_time_seconds": 842.0,
      "end_time_seconds": 1030.0,
      "display_time": "00:14:02–00:17:10",
      "speaker_names": ["Alice"],
      "snippet": "The safest way to keep the character consistent is to start with a locked reference...",
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
  "not_enough_evidence": false,
  "query_id": "6f235d42-f6de-4f3f-9d1f-7e64a1f4a2e7",
  "answer_id": "d97527c6-4f75-4a92-bcf0-cc050ea8f054",
  "missing_evidence_note": ""
}
```

**Field notes:**

| Field | Source | Notes |
|---|---|---|
| `answer` | README | Answer text, or the canonical fallback when `not_enough_evidence` is true |
| `sources` | README | Array of source cards; may be empty when evidence is absent |
| `suggested_questions` | README | Three follow-up questions grounded in retrieved content |
| `confidence` | README | `"high"` \| `"medium"` \| `"low"` — see RAG_PIPELINE.md → Confidence Calibration |
| `not_enough_evidence` | README | `true` when retrieval cannot support a grounded answer — see RAG_PIPELINE.md → Failure Behavior |
| `video_url` | README | Full URL with `?t=` parameter. MVP: constructed from `VIDEO_BASE_URL` + path. S3 migration: call `/videos/{video_id}/playback-url` instead — see Source Card Click Behavior. |
| `query_id` | **Addition** | UUID of the persisted `queries` row. Use with `GET /debug/queries/{query_id}`. |
| `answer_id` | **Addition** | UUID of the persisted `answers` row. Use with `POST /feedback`. |
| `missing_evidence_note` | **Addition** | Human-readable note when `not_enough_evidence` is true. Empty string otherwise. |

**Insufficient evidence response — 200 OK:**

The endpoint always returns 200 when the pipeline ran successfully, even when evidence is absent.

```json
{
  "answer": "I could not find enough evidence in the webinar library to answer that confidently.",
  "sources": [],
  "suggested_questions": [],
  "confidence": "low",
  "not_enough_evidence": true,
  "query_id": "6f235d42-f6de-4f3f-9d1f-7e64a1f4a2e7",
  "answer_id": "d97527c6-4f75-4a92-bcf0-cc050ea8f054",
  "missing_evidence_note": "No relevant transcript chunks were retrieved for this question."
}
```

**Behavior rules:**

- `POST /ask` never returns an unsupported confident answer.
- When no chunks are retrieved, return `not_enough_evidence: true` without calling Claude for synthesis. See RAG_PIPELINE.md → Failure Behavior → No Results.
- The fallback answer string `"I could not find enough evidence in the webinar library to answer that confidently."` is canonical. Do not substitute other refusal phrasing.
- `snippet` in each source card must be verbatim from `raw_text`, ≤ 2 sentences. See RAG_PIPELINE.md → Source Snippet Rules.
- Every `chunk_id` in `sources` must exist in the chunks list that was sent to Claude. Discard any source referencing an unknown `chunk_id`.

---

### GET /videos

Returns available webinars. Implemented in `backend/app/api/routes_videos.py`.

**Query parameters** (all optional):

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `limit` | integer | 20 | Page size |
| `offset` | integer | 0 | Page offset |
| `status` | string | — | Filter by `videos.status` (see DATABASE.md → Processing Lifecycle) |

**Response — 200 OK:**

```json
{
  "items": [
    {
      "id": "ccf5b43f-b4d5-4609-96e7-1d9a7e197948",
      "title": "Character Consistency Deep Dive",
      "webinar_date": "2026-04-12",
      "speakers": ["Alice", "Bob"],
      "duration_seconds": 3600,
      "video_url": "http://localhost:8000/videos/char-consistency.mp4",
      "description": "Internal webinar on maintaining character identity across AI-generated shots.",
      "status": "ready",
      "created_at": "2026-05-21T12:30:00Z",
      "updated_at": "2026-05-21T12:30:00Z"
    }
  ],
  "limit": 20,
  "offset": 0,
  "total": 1
}
```

**Field notes:**

| Field | Source | Notes |
|---|---|---|
| `id` | README | UUID |
| `title` | README | |
| `webinar_date` | README | ISO 8601 date string |
| `speakers` | README | Array of speaker name strings |
| `duration_seconds` | README | Integer |
| `video_url` | README | Full URL. MVP: local path via `VIDEO_BASE_URL`. S3 migration: derive from `video_assets`. |
| `description` | **Addition** | From `videos.description`. Nullable. |
| `status` | **Addition** | From `videos.status` (see DATABASE.md). Useful for filtering ingestion-in-progress videos. |
| `created_at` | **Addition** | ISO 8601 datetime. |
| `updated_at` | **Addition** | ISO 8601 datetime (see DATABASE.md → `videos` table). |

> **README base contract:** The README defines a flat array response. Pagination (`items`, `limit`, `offset`, `total`) is an addition over the README's simpler shape. Backends that implement the README's flat array satisfy the MVP; pagination is the recommended production form.

---

### GET /videos/{video_id}/chunks

Returns the chunk index for a webinar. Primarily for development and debugging. Implemented in `backend/app/api/routes_videos.py`.

**Query parameters** (all optional):

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `limit` | integer | 20 | Page size |
| `offset` | integer | 0 | Page offset |
| `include_raw_text` | boolean | false | Include `raw_text` field on each chunk |
| `include_contextual_text` | boolean | false | Include `contextual_text` field on each chunk |

**Response — 200 OK:**

```json
{
  "video_id": "ccf5b43f-b4d5-4609-96e7-1d9a7e197948",
  "video_title": "Character Consistency Deep Dive",
  "items": [
    {
      "id": "39e4dd75-b5a6-42cd-8c38-516b7f0c8f62",
      "start_time_seconds": 842.0,
      "end_time_seconds": 1030.0,
      "display_time": "00:14:02–00:17:10",
      "summary": "Explains how reference images reduce identity drift.",
      "topic_tags": ["character consistency", "reference images", "identity drift"],
      "speaker_names": ["Alice"],
      "chunk_index": 14,
      "word_count": 642,
      "raw_text": null,
      "contextual_text": null
    }
  ],
  "limit": 20,
  "offset": 0,
  "total": 42
}
```

**Field notes:**

| Field | Source | Notes |
|---|---|---|
| `id`, `start_time_seconds`, `end_time_seconds`, `summary`, `topic_tags`, `speaker_names` | README | Core chunk fields |
| `display_time` | **Addition** | Formatted timecode range. See Time Formatting Utility. |
| `chunk_index` | **Addition** | Position within video. From `chunks.chunk_index` (see DATABASE.md). |
| `word_count` | **Addition** | From `chunks.word_count` (see DATABASE.md). |
| `raw_text` | **Addition** | Only present when `include_raw_text=true`. |
| `contextual_text` | **Addition** | Only present when `include_contextual_text=true`. |
| `video_id`, `video_title` | **Addition** | Envelope fields for context. |

**Error — 404:** `VIDEO_NOT_FOUND` if `video_id` does not exist.

---

### POST /feedback

Stores user rating on an answer. Required for retrieval quality debugging. Stores to the `feedback` table (see DATABASE.md → `010_create_feedback.sql`). Implement in `backend/app/api/routes_ask.py` or a separate `backend/app/api/routes_feedback.py`.

**Request:**

```json
{
  "query_id": "6f235d42-f6de-4f3f-9d1f-7e64a1f4a2e7",
  "answer_id": "d97527c6-4f75-4a92-bcf0-cc050ea8f054",
  "rating": "thumbs_up",
  "feedback_text": "This found the right webinar and timestamp."
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `query_id` | UUID string | Yes | Must reference an existing `queries` row |
| `answer_id` | UUID string | Yes | Must reference an existing `answers` row |
| `rating` | string | Yes | See rating values below |
| `feedback_text` | string | No | Free-text comment; nullable |

**Rating values:**

```
thumbs_up
thumbs_down
wrong_source
answer_too_vague
missing_context
hallucinated
timestamp_unhelpful
```

> `hallucinated` and `timestamp_unhelpful` are **Additions — not in README or DATABASE.md** relative to DATABASE.md's base rating list (`thumbs_up`, `thumbs_down`, `wrong_source`, `answer_too_vague`, `missing_context`).

**Response — 200 OK:**

```json
{
  "feedback_id": "f764a1fa-d2ff-4e6a-bf1d-d1b1a6c6d4d0",
  "status": "saved"
}
```

**Errors:** `QUERY_NOT_FOUND`, `ANSWER_NOT_FOUND`, `VALIDATION_ERROR`.

---

## Optional Enhancement Endpoints

### GET /videos/{video_id}

Single webinar detail view. Includes asset list when `video_assets` table is populated (see DATABASE.md → `008_create_video_assets.sql`).

**Response — 200 OK:**

```json
{
  "id": "ccf5b43f-b4d5-4609-96e7-1d9a7e197948",
  "title": "Character Consistency Deep Dive",
  "description": "Internal webinar on maintaining character identity across AI-generated shots.",
  "webinar_date": "2026-04-12",
  "speakers": ["Alice", "Bob"],
  "duration_seconds": 3600,
  "video_url": "http://localhost:8000/videos/char-consistency.mp4",
  "status": "ready",
  "assets": [
    {
      "id": "342a71a2-91e4-4d4a-9ff0-f1f028724cb5",
      "asset_type": "proxy_video",
      "s3_bucket": "company-webinar-library-mvp",
      "s3_key": "proxy/ccf5b43f-b4d5-4609-96e7-1d9a7e197948/720p.mp4",
      "content_type": "video/mp4",
      "file_size_bytes": 502349001
    }
  ],
  "created_at": "2026-05-21T12:30:00Z",
  "updated_at": "2026-05-21T12:30:00Z"
}
```

`assets` is an empty array until `008_create_video_assets.sql` is applied. The `asset_type` values are defined in DATABASE.md → S3 Architecture.

**Error — 404:** `VIDEO_NOT_FOUND`.

---

### GET /videos/{video_id}/playback-url

Generates a short-lived S3 presigned playback URL. **Phase 2 (S3 migration) only.** See DATABASE.md → S3 Architecture → Presigned URL Flow for the full flow description, asset preference logic (`proxy_video` → `original_video` fallback), and env vars.

**Query parameters:**

| Parameter | Type | Required | Notes |
|---|---|---|---|
| `start_time` | integer | No | Timestamp in seconds; passed through to `start_time_seconds` in response |
| `asset_type` | string | No | Override asset preference; default: `proxy_video` |

**Response — 200 OK:**

```json
{
  "video_id": "ccf5b43f-b4d5-4609-96e7-1d9a7e197948",
  "asset_type": "proxy_video",
  "start_time_seconds": 842.0,
  "expires_in_seconds": 900,
  "playback_url": "https://s3.amazonaws.com/..."
}
```

`expires_in_seconds` reflects `PRESIGNED_URL_EXPIRATION_SECONDS` (see DATABASE.md → Environment Variables).

**Error — 404:** `NO_PLAYBACK_ASSET` if no playable asset exists for this video.

```json
{
  "error": {
    "code": "NO_PLAYBACK_ASSET",
    "message": "No playable video asset was found for this webinar.",
    "details": { "video_id": "ccf5b43f-b4d5-4609-96e7-1d9a7e197948" }
  }
}
```

---

### POST /ingest/video

API-triggered ingestion. **The CLI script is the primary ingestion path for MVP** (see README → Ingestion CLI). This endpoint is the future contract for API-triggered ingestion.

Path uses README's naming: `POST /ingest/video`. Implemented in `backend/app/api/routes_ingest.py`.

**Request:**

```json
{
  "title": "Character Consistency Deep Dive",
  "description": "Internal webinar on maintaining character identity across AI-generated shots.",
  "webinar_date": "2026-04-12",
  "speakers": ["Alice", "Bob"],
  "video_url": "/videos/char-consistency.mp4",
  "transcript_path": "/transcripts/char-consistency.json"
}
```

Fields match the README's CLI arguments. `description` is an **Addition — not in README's CLI args** (it is in the `videos` table schema).

**Response — 200 OK:**

```json
{
  "video_id": "ccf5b43f-b4d5-4609-96e7-1d9a7e197948",
  "chunks_created": 42
}
```

This matches the README's defined response shape.

---

### GET /debug/queries/{query_id}

Development-only RAG trace endpoint. **Not in README** — defined in RAG_PIPELINE.md → Debug Endpoint. See that document for the full response shape, implementation notes, and the `DEBUG` env flag guard.

Guard:
```python
if not settings.DEBUG:
    raise HTTPException(status_code=404)
```

Add `DEBUG=true` to `backend/.env.example`. Do not expose in production.

Response shape and join logic are defined in RAG_PIPELINE.md → Debug Endpoint.

---

## Frontend TypeScript Types

File: `frontend/src/types/api.ts`

This is the single source of truth for all TypeScript types. Types below start from the README's definitions and extend with additions.

```typescript
// ─── Core types (from README) ────────────────────────────────────────────────

export interface AskRequest {
  question: string;
  top_k?: number;
  filters?: AskFilters; // Addition — not in README
}

export interface SourceCard {
  chunk_id:            string;
  video_id:            string;
  video_title:         string;
  start_time_seconds:  number;
  end_time_seconds:    number;
  display_time:        string;
  speaker_names:       string[];
  snippet:             string;
  supporting_claim:    string;
  video_url:           string; // Full URL with ?t= param. MVP: use directly. S3: call playback-url endpoint.
}

export interface AskResponse {
  answer:              string;
  sources:             SourceCard[];
  suggested_questions: string[];
  confidence:          "high" | "medium" | "low";
  not_enough_evidence: boolean;
  // Additions — not in README:
  query_id:            string;
  answer_id:           string;
  missing_evidence_note: string;
}

export interface VideoSummary {
  id:               string;
  title:            string;
  webinar_date:     string;
  speakers:         string[];
  duration_seconds: number;
  video_url:        string;
  // Additions — not in README:
  description?:     string | null;
  status?:          VideoStatus;
  created_at?:      string;
  updated_at?:      string;
}

// ─── Addition types (not in README) ──────────────────────────────────────────

/** Accepted by POST /ask but ignored until filter logic is implemented. */
export interface AskFilters {
  video_ids?:     string[];
  speaker_names?: string[];
  topic_tags?:    string[];
  date_from?:     string | null;
  date_to?:       string | null;
}

/** Processing lifecycle states — see DATABASE.md → Processing Lifecycle. */
export type VideoStatus =
  | "pending"
  | "uploaded"
  | "transcribed"
  | "chunked"
  | "contextualized"
  | "embedded"
  | "ready"
  | "failed";

/** Returned by GET /videos/{video_id} (optional enhancement endpoint). */
export interface VideoAsset {
  id:              string;
  asset_type:      string;
  s3_bucket:       string;
  s3_key:          string;
  content_type?:   string | null;
  file_size_bytes?: number | null;
}

/** Returned by GET /videos/{video_id} (optional enhancement endpoint). */
export interface VideoDetail extends VideoSummary {
  assets: VideoAsset[];
}

/** Returned by GET /videos (paginated). */
export interface PaginatedVideos {
  items:  VideoSummary[];
  limit:  number;
  offset: number;
  total:  number;
}

/** Returned by GET /videos/{video_id}/playback-url (optional S3 endpoint). */
export interface PlaybackUrlResponse {
  video_id:          string;
  asset_type:        "proxy_video" | "original_video";
  start_time_seconds: number;
  expires_in_seconds: number;
  playback_url:      string;
}

/** POST /feedback request body. */
export interface FeedbackRequest {
  query_id:      string;
  answer_id:     string;
  rating:
    | "thumbs_up"
    | "thumbs_down"
    | "wrong_source"
    | "answer_too_vague"
    | "missing_context"
    | "hallucinated"
    | "timestamp_unhelpful";
  feedback_text?: string;
}

/** POST /feedback response. */
export interface FeedbackResponse {
  feedback_id: string;
  status:      "saved";
}

/** Standard error envelope — all non-2xx responses. */
export interface ApiError {
  error: {
    code:     string;
    message:  string;
    details?: Record<string, unknown>;
  };
}
```

---

## Backend Pydantic Schemas

File: `backend/app/db/schemas.py`

This is the only schema file location (see README → Project Structure). Do not create a separate `backend/app/schemas/api.py`.

```python
from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


# ─── Ask ─────────────────────────────────────────────────────────────────────

class AskFilters(BaseModel):
    """Addition — not in README. Accepted but ignored until filter logic is implemented."""
    video_ids:     list[UUID] | None = None
    speaker_names: list[str]  | None = None
    topic_tags:    list[str]  | None = None
    date_from:     str        | None = None
    date_to:       str        | None = None


class AskRequest(BaseModel):
    question: str  = Field(..., min_length=1)
    top_k:    int  = Field(default=8, ge=4, le=20)
    filters:  AskFilters | None = None  # Addition — not in README


class SourceCardResponse(BaseModel):
    """Matches README's SourceCard dataclass. Field names are identical."""
    chunk_id:           UUID
    video_id:           UUID
    video_title:        str
    start_time_seconds: float
    end_time_seconds:   float
    display_time:       str          # "HH:MM:SS–HH:MM:SS"
    speaker_names:      list[str] = []
    snippet:            str
    supporting_claim:   str
    video_url:          str          # Full URL with ?t= param


class AskResponse(BaseModel):
    """README base fields + query_id, answer_id, missing_evidence_note additions."""
    answer:               str
    sources:              list[SourceCardResponse]
    suggested_questions:  list[str]
    confidence:           Literal["high", "medium", "low"]
    not_enough_evidence:  bool
    # Additions — not in README:
    query_id:             UUID
    answer_id:            UUID
    missing_evidence_note: str = ""


# ─── Videos ──────────────────────────────────────────────────────────────────

class VideoSummaryResponse(BaseModel):
    """Matches README's VideoSummary. Required fields from README; additions nullable."""
    id:               UUID
    title:            str
    webinar_date:     str        | None = None
    speakers:         list[str]         = []
    duration_seconds: int        | None = None
    video_url:        str        | None = None
    # Additions — not in README:
    description:      str        | None = None
    status:           str        | None = None  # see DATABASE.md → Processing Lifecycle
    created_at:       str        | None = None
    updated_at:       str        | None = None


class VideoAssetResponse(BaseModel):
    """Addition — not in README. Populated only after 008_create_video_assets.sql."""
    id:              UUID
    asset_type:      str
    s3_bucket:       str
    s3_key:          str
    content_type:    str | None = None
    file_size_bytes: int | None = None


class VideoDetailResponse(VideoSummaryResponse):
    """Returned by GET /videos/{video_id} (optional enhancement endpoint)."""
    assets: list[VideoAssetResponse] = []


class PaginatedVideosResponse(BaseModel):
    """Addition — README defines a flat array. Pagination is the recommended form."""
    items:  list[VideoSummaryResponse]
    limit:  int
    offset: int
    total:  int


# ─── Chunks ──────────────────────────────────────────────────────────────────

class ChunkResponse(BaseModel):
    """Matches README's GET /videos/{video_id}/chunks response fields."""
    id:                 UUID
    start_time_seconds: float
    end_time_seconds:   float
    summary:            str        | None = None
    topic_tags:         list[str]         = []
    speaker_names:      list[str]         = []
    # Additions — not in README:
    display_time:       str        | None = None
    chunk_index:        int        | None = None  # see DATABASE.md
    word_count:         int        | None = None  # see DATABASE.md
    raw_text:           str        | None = None  # only when include_raw_text=true
    contextual_text:    str        | None = None  # only when include_contextual_text=true


class VideoChunksResponse(BaseModel):
    """Addition — README returns a flat array; this wraps it with envelope + pagination."""
    video_id:    UUID
    video_title: str
    items:       list[ChunkResponse]
    limit:       int
    offset:      int
    total:       int


# ─── Playback ────────────────────────────────────────────────────────────────

class PlaybackUrlResponse(BaseModel):
    """Returned by GET /videos/{video_id}/playback-url (optional S3 endpoint)."""
    video_id:           UUID
    asset_type:         Literal["proxy_video", "original_video"]
    start_time_seconds: float
    expires_in_seconds: int
    playback_url:       str


# ─── Feedback ────────────────────────────────────────────────────────────────

class FeedbackRequest(BaseModel):
    """Stores to feedback table — see DATABASE.md → 010_create_feedback.sql."""
    query_id:      UUID
    answer_id:     UUID
    rating: Literal[
        "thumbs_up",
        "thumbs_down",
        "wrong_source",
        "answer_too_vague",
        "missing_context",
        "hallucinated",        # Addition — not in DATABASE.md base list
        "timestamp_unhelpful", # Addition — not in DATABASE.md base list
    ]
    feedback_text: str | None = None


class FeedbackResponse(BaseModel):
    feedback_id: UUID
    status:      Literal["saved"]


# ─── Ingest ──────────────────────────────────────────────────────────────────

class IngestVideoRequest(BaseModel):
    """Matches README's POST /ingest/video request shape."""
    title:           str
    description:     str        | None = None  # Addition — not in README CLI args
    webinar_date:    str        | None = None
    speakers:        list[str]         = []
    video_url:       str        | None = None
    transcript_path: str        | None = None


class IngestVideoResponse(BaseModel):
    """Matches README's POST /ingest/video response shape."""
    video_id:      UUID
    chunks_created: int


# ─── Errors ──────────────────────────────────────────────────────────────────

class ErrorDetail(BaseModel):
    code:    str
    message: str
    details: dict | None = None


class ErrorResponse(BaseModel):
    error: ErrorDetail
```

---

## Frontend API Client

File: `frontend/src/api/client.ts`

Not defined in any other document.

```typescript
import type {
  AskRequest,
  AskResponse,
  VideoSummary,
  PaginatedVideos,
  PlaybackUrlResponse,
  FeedbackRequest,
  FeedbackResponse,
  ApiError,
} from "../types/api";

/**
 * VITE_API_BASE_URL — Addition: set in frontend/.env.
 * See Environment Variables section below.
 * Falls back to localhost for local dev without Vite proxy.
 */
const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers ?? {}),
    },
    ...options,
  });

  if (!response.ok) {
    const body = await response.json().catch(() => null) as ApiError | null;
    throw new Error(
      body?.error?.message ?? `Request failed: ${response.status}`
    );
  }

  return response.json() as Promise<T>;
}

// ─── Core MVP functions ───────────────────────────────────────────────────────

export async function askLibrary(
  payload: AskRequest
): Promise<AskResponse> {
  return request<AskResponse>("/ask", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function getVideos(params?: {
  limit?: number;
  offset?: number;
  status?: string;
}): Promise<PaginatedVideos> {
  const query = new URLSearchParams();
  if (params?.limit  !== undefined) query.set("limit",  String(params.limit));
  if (params?.offset !== undefined) query.set("offset", String(params.offset));
  if (params?.status !== undefined) query.set("status", params.status);
  const qs = query.toString();
  return request<PaginatedVideos>(`/videos${qs ? `?${qs}` : ""}`);
}

export async function submitFeedback(
  payload: FeedbackRequest
): Promise<FeedbackResponse> {
  return request<FeedbackResponse>("/feedback", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

// ─── Optional enhancement functions ──────────────────────────────────────────

/**
 * S3 migration path. Call this instead of using video_url directly
 * once GET /videos/{video_id}/playback-url is implemented.
 * See Source Card Click Behavior section.
 */
export async function getPlaybackUrl(
  videoId: string,
  startTimeSeconds: number
): Promise<PlaybackUrlResponse> {
  return request<PlaybackUrlResponse>(
    `/videos/${videoId}/playback-url?start_time=${Math.floor(startTimeSeconds)}`
  );
}
```

**Frontend env var — Addition:**

```env
# frontend/.env
VITE_API_BASE_URL=http://localhost:8000
```

Set this when not using Vite's dev proxy. The Vite proxy config (see README → Frontend → `vite.config.ts`) proxies `/ask` → `http://localhost:8000` automatically in local dev; `VITE_API_BASE_URL` is used for deployed environments.

---

## Time Formatting Utility

Not defined in any other document. Place in `backend/app/services/answer_service.py` or a shared `backend/app/utils.py`.

```python
def format_seconds_as_timecode(seconds: float) -> str:
    """Convert float seconds to HH:MM:SS string. Used in display_time fields."""
    total = int(seconds)
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def format_time_range(start: float, end: float) -> str:
    """Format a chunk's time range as 'HH:MM:SS–HH:MM:SS'."""
    return f"{format_seconds_as_timecode(start)}–{format_seconds_as_timecode(end)}"
```

`display_time` is always `format_time_range(start_time_seconds, end_time_seconds)`. `start_time_seconds` and `end_time_seconds` are always stored as `FLOAT` (see DATABASE.md → Timestamp Conventions). Do not store or parse timecode strings in SQL.

---

## Source Card Click Behavior

The `SourceCard` type carries `video_url` — a full URL with a `?t=` parameter already embedded (e.g., `http://localhost:8000/videos/char-consistency.mp4?t=842`).

**MVP — use `video_url` directly:**

```typescript
// SourceCard.tsx — "Open Clip" button
<a href={source.video_url} target="_blank" rel="noopener noreferrer">
  Open Clip
</a>
```

No client-side URL construction is needed. The `?t=` parameter is constructed by the backend's `answer_service.py`:

```python
video_url = f"{base_video_url}?t={int(start_time_seconds)}"
```

**S3 migration path — call the playback-url endpoint:**

Once `GET /videos/{video_id}/playback-url` is implemented (Phase 2), replace the direct `video_url` link with a dynamic call:

```typescript
async function handleSourceCardClick(source: SourceCard): Promise<void> {
  // 1. Call the backend for a short-lived presigned URL.
  const { playback_url, start_time_seconds } = await getPlaybackUrl(
    source.video_id,
    source.start_time_seconds
  );
  // 2. Open the video player at the correct timestamp.
  window.open(`${playback_url}#t=${start_time_seconds}`, "_blank");
}
```

The full presigned URL flow — asset preference logic, TTL, env vars — is defined in DATABASE.md → S3 Architecture → Presigned URL Flow. The frontend never holds AWS credentials or constructs S3 URLs directly.
