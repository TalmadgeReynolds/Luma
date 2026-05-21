# CLAUDE.md — Webinar Library Answer Engine

A retrieval-augmented answer engine over timestamped webinar transcripts. Users ask questions; the system retrieves grounded transcript chunks, sends them to Claude, and returns an answer with timestamped source cards.

**Read these docs in this order before writing code: README.md → DATABASE.md → API_CONTRACT.md → RAG_PIPELINE.md.**

---

## Quick Start

```bash
# Infrastructure
docker-compose up -d
cd backen
cp .env.example .env              # fill in ANTHROPIC_API_KEY, VOYAGE_API_KEY (or OPENAI_API_KEY)
pip install -r requirements.txt
python -m app.scripts.run_migrations

# Ingest fixture data
python -m app.scripts.ingest_webinar --fixture

# Run backend
uvicorn app.main:app --reload

# In another terminal — run frontend
cd frontend
npm install
npm run dev
```

After these steps: `curl http://localhost:8000/health` → `{"status": "ok"}`, and `http://localhost:5173` renders the UI.

---

## Document Map

| Document | Role | When to read it |
|---|---|---|
| `README.md` | Build spec and source of truth | Architecture, naming, schemas, service interfaces, endpoints, project structure, implementation sequence |
| `DATABASE.md` | Schema companion | Confused about a table schema, index, migration, processing lifecycle, or S3 path? |
| `API_CONTRACT.md` | Frontend-backend contract | Confused about an endpoint shape, request/response field, Pydantic schema, or TypeScript type? |
| `RAG_PIPELINE.md` | Retrieval engineering | Confused about chunking parameters, embedding strategy, hybrid scoring, confidence calibration, or failure modes? |

README wins all conflicts. These docs do not repeat each other. Do not add content from one doc into another.

---

## Code Conventions

### Python (backend)

- Python 3.11+. Minimum target: 3.11.
- **Async everywhere.** All service functions are `async def`. All DB calls use async SQLAlchemy. No synchronous DB calls anywhere.
- **Type hints on every function signature** — both parameters and return type. No exceptions.
- Dataclasses for internal data objects (`RetrievedChunk`, `AnswerResponse`, `SourceCard`). Pydantic for API request/response schemas in `db/schemas.py`.
- Import ordering: stdlib → third-party → local. One blank line between groups.
- String formatting: f-strings only. Never `.format()` or `%`.
- Constants: `UPPER_SNAKE_CASE` in `config.py`. Never scattered across files.
- **No classes where a function suffices.** Services are modules with functions, not class instances. Write `async def retrieve_chunks()` in `retrieval_service.py`, not `class RetrievalService`.
- Logging: use `structlog` or stdlib `logging` with structured key-value pairs. INFO for pipeline milestones, DEBUG for intermediate results, WARNING for degraded behavior, ERROR for failures.
- Every service function calling an external API (Claude, embeddings, DB) must catch exceptions and raise a domain-specific error. Raw `httpx`, `anthropic`, and `sqlalchemy` exceptions must not reach route handlers.

### TypeScript (frontend)

- React 18+ with functional components only.
- TypeScript strict mode.
- Named exports. No default exports.
- Props as inline type annotations or imported interfaces.
- State management: `useState` / `useReducer` only. No Redux, no Zustand, no external state library.
- API calls only in `api/client.ts`. Components never call `fetch` directly.
- All API types in `types/api.ts`. Single source of truth; must match `API_CONTRACT.md`.

### Naming

| Artifact | Convention |
|---|---|
| Python files | `snake_case` (`retrieval_service.py`) |
| React component files | `PascalCase` (`SourceCard.tsx`) |
| Non-component TypeScript files | `camelCase` (`client.ts`) |
| Python functions | `snake_case` |
| TypeScript functions | `camelCase` |
| Database columns | `snake_case` |
| API JSON fields | `snake_case` |
| Environment variables | `UPPER_SNAKE_CASE` |

---

## Error Handling Patterns

### Backend

Define all domain exceptions in `backend/app/errors.py`:

```python
class RetrievalError(Exception): ...
class ClaudeServiceError(Exception): ...
class EmbeddingError(Exception): ...
class IngestionError(Exception): ...
```

**Route handlers are thin.** They catch domain exceptions and map them to HTTP error responses using the standard `{"error": {"code": ..., "message": ..., "details": ...}}` shape defined in `API_CONTRACT.md → Standard Error Response`. No business logic in routes.

**Services raise domain exceptions.** `retrieval_service.py` raises `RetrievalError`. `claude_service.py` raises `ClaudeServiceError`. `embedding_service.py` raises `EmbeddingError`. `ingestion_service.py` raises `IngestionError`.

**Claude calls:** always validate JSON response. If Claude returns invalid JSON, retry once, then raise `ClaudeServiceError`. Never pass raw Claude output to the next pipeline stage without parsing.

**Embedding calls:** if the provider returns an error, raise `EmbeddingError` with the provider name and model name in the message.

**DB calls:** wrap in try/except, raise domain errors. Raw SQLAlchemy exceptions must not reach routes.

### Frontend

- The API client (`client.ts`) throws on any non-2xx response. See `API_CONTRACT.md → Frontend API Client` for the implementation.
- Components catch thrown errors and display user-friendly messages.
- Never swallow errors silently.
- Loading states: disable input while a request is in-flight, show spinner.

---

## Testing Rules

Framework: `pytest` with `pytest-asyncio` for async tests.

Test file naming: `test_<module>.py` in `backend/tests/`, mirroring `app/` structure. Example: `backend/tests/services/test_chunking_service.py`.

**Mock all external calls in unit tests.** Claude (Anthropic API), embedding providers (Voyage/OpenAI), and the database must all be mocked. Unit tests never hit the network or a real database.

**Integration tests** may use the Docker Postgres instance with test fixtures. They must never call real Claude or embedding APIs.

**Fixture strategy:** `backend/fixtures/sample_transcript.json` is the canonical test fixture. All tests that need transcript data use this file.

### What to test

| Module | What to verify |
|---|---|
| `chunking_service.py` | Chunk count, overlap correctness, timestamp preservation, speaker preservation |
| `retrieval_service.py` | Mock Claude rewrite + mock embedding + mock DB → verify merge/dedupe logic |
| `answer_service.py` | Mock Claude response → verify `AnswerResponse` shape; verify `not_enough_evidence` path |
| `claude_service.py` | Prompt loading, JSON parsing, retry on invalid JSON |
| Route handlers | Request validation, error response shapes |

### What not to test

Don't test trivial getters. Don't test SQLAlchemy ORM behavior. Don't test third-party libraries.

Run tests:
```bash
cd backend && pytest -v
```

---

## Dependency Management

### Python — `backend/requirements.txt` (pin exact versions)

```
fastapi>=0.104.0
uvicorn>=0.24.0
sqlalchemy[asyncio]>=2.0.0
asyncpg>=0.29.0
anthropic>=0.40.0
httpx>=0.25.0
pydantic>=2.5.0
pydantic-settings>=2.1.0
pgvector>=0.2.4
voyageai>=0.3.0
openai>=1.6.0
python-dotenv>=1.0.0
structlog>=24.0.0
pytest>=7.4.0
pytest-asyncio>=0.21.0
```

`voyageai` is used when `EMBEDDING_PROVIDER=voyage`. `openai` is used when `EMBEDDING_PROVIDER=openai`. Both go in `requirements.txt`.

### TypeScript — `frontend/package.json`

Key dependencies (exact or `~` pinned):
```
react, react-dom  (18+)
typescript        (5+)
vite              (5+)
```

No additional UI framework unless explicitly requested. No Tailwind, no Material UI, no Chakra. Use plain CSS or CSS modules for MVP.

### Do not install

LangChain, LlamaIndex, ChromaDB, Pinecone, any vector DB other than pgvector, any ORM other than SQLAlchemy, any external state management library, any CSS framework.

---

## Prompt File Rules

- All Claude prompts live in `backend/app/prompts/*.txt`.
- Prompts are loaded once at service startup, not re-read per request.
- Template variables use `{{variable_name}}` syntax.
- `claude_service.py` owns all prompt loading and template rendering.
- Never hardcode prompt text in service functions.
- When modifying a prompt: update the `.txt` file, not the Python code.

Prompt files defined in `README.md`:
- `contextualize_chunk.txt`
- `rewrite_query.txt`
- `rerank_chunks.txt`
- `answer_from_chunks.txt`

Optional addition from `RAG_PIPELINE.md`:
- `classify_question.txt`

---

## Database Rules

- Migrations: raw SQL files in `backend/app/db/migrations/`, numbered `001_*.sql` through `007_*.sql` (core) + `008_*` through `010_*` (optional enhancements from `DATABASE.md`).
- Run migrations: `python -m app.scripts.run_migrations` — executes SQL files in lexicographic order.
- No Alembic for MVP.
- All DB access through async SQLAlchemy.
- UUID primary keys everywhere (`gen_random_uuid()`).
- Timestamps stored as `FLOAT` seconds. Displayed as timecode (`HH:MM:SS`). See `API_CONTRACT.md → Time Formatting Utility` for the conversion function.
- `EMBEDDING_DIMENSION` must be read from env at migration time. Do not hardcode `VECTOR(1024)`.
- Only `status = 'ready'` videos enter the retrieval pipeline. See `DATABASE.md → Processing Lifecycle`.
- Full schema reference: `DATABASE.md → Core Schema`.

---

## Git & Commits

- Commit after each completed implementation phase (matching `README.md → Implementation Sequence`).
- Commit message format: `phase N: <brief description>` (e.g., `phase 1: infrastructure and migrations`).
- Do not commit broken code. Each commit must pass `pytest` once tests exist.

`.gitignore` must include:
```
.env
__pycache__/
node_modules/
.venv/
*.pyc
.pytest_cache/
```

---

## What's Already Decided — Do Not Change

These are non-negotiable. Do not substitute alternatives.

| Decision | What's locked |
|---|---|
| Backend framework | FastAPI — not Flask, not Django |
| ORM | SQLAlchemy async — raw SQL only in migration files |
| Vector store | pgvector — not ChromaDB, Pinecone, Qdrant, or any other |
| LLM SDK | Anthropic SDK direct — not LangChain, not LlamaIndex |
| Schema validation | Pydantic v2 |
| Frontend bundler | React + Vite — not Next.js, not Remix |
| Component style | Functional components only — no class components |
| CSS approach | CSS modules or plain CSS — not Tailwind, not MUI, not Chakra |
| Test framework | pytest — not unittest |
| Embedding storage | `chunks.embedding` column — not a separate table |
| Migration tool | Raw SQL files — not Alembic |
| Ingestion primary path | CLI script — API endpoint is optional |

---

## What You Can Decide

These are genuinely open. Make a choice and be consistent.

- Specific CSS styling approach (modules vs. plain)
- Internal helper function names and utility modules
- Logging format details beyond structured key-value
- Test fixture content (as long as it is realistic and conforms to the transcript schema)
- Retry strategy for external API calls (1–3 retries is acceptable)
- Batch sizes for embedding calls
- Connection pool sizes
- Whether to use `asyncio.gather` for parallel operations

---

## Common Mistakes to Avoid

**Python:**
- Don't use `datetime.utcnow()` — deprecated in Python 3.12+. Use `datetime.now(UTC)`.
- Don't forget `__init__.py` — every Python package directory needs one. Can be empty.
- Don't hardcode `VECTOR(1024)` — read `EMBEDDING_DIMENSION` from env.
- Don't use synchronous DB calls — everything is async.
- Don't put business logic in route handlers — routes are thin dispatchers to services.
- Don't embed `raw_text` — embed `contextual_text`. See `README.md → Ingestion Pipeline → Step 5`.
- Don't use `json.loads()` on Claude responses without validating the parsed result against the expected schema.
- Don't skip retrieval logging — every query's retrieved chunks must be written to `retrieval_logs`.

**Project setup:**
- Don't forget CORS middleware. The frontend requires it. See `README.md → API Endpoints` for the exact middleware config.
- Don't serve `status != 'ready'` videos through the retrieval pipeline.
- Don't construct timecodes in SQL. Store as `FLOAT`, convert in Python. See `DATABASE.md → Timestamp Conventions`.

**Frontend:**
- Don't call `fetch` in components. All API calls go through `api/client.ts`.
- Don't add types outside `types/api.ts` for API shapes. One source of truth.
- Don't construct the `?t=` URL parameter client-side. It comes pre-built in `video_url` from the API.

---

## File Reading Checklist

Before implementing any section, read the relevant doc first:

| Task | Read |
|---|---|
| Setting up the project | `README.md → Implementation Sequence → Phase 1` |
| Creating database tables | `DATABASE.md → Core Schema` |
| Writing a migration | `DATABASE.md → Migration Order` |
| Writing a service | `README.md → Project Structure` + the relevant pipeline section |
| Implementing an endpoint | `API_CONTRACT.md` → relevant endpoint section |
| Writing Claude prompts | `README.md → Claude Prompts` |
| Tuning retrieval | `RAG_PIPELINE.md` |
| Writing tests | This file → Testing Rules |
| Handling errors | `API_CONTRACT.md → Standard Error Response` + this file → Error Handling Patterns |
| Adding a TypeScript type | `API_CONTRACT.md → Frontend TypeScript Types` |
| Implementing Pydantic schemas | `API_CONTRACT.md → Backend Pydantic Schemas` |
| Diagnosing retrieval quality | `RAG_PIPELINE.md → Common Failure Modes` + `GET /debug/queries/{query_id}` |
