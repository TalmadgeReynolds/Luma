# RAG_PIPELINE.md — Webinar Library Answer Engine

## Relationship to README.md and DATABASE.md

This document is the RAG engineering companion to the build spec. README.md is the source of truth for architecture, data model, all four Claude prompts, ingestion pipeline steps, retrieval and answer service interfaces, API endpoints, frontend, project structure, and implementation sequence. DATABASE.md is the schema reference, covering table definitions, indexes, retrieval query patterns, and the processing lifecycle. Where any section here conflicts with the README, the README wins. This document covers what those two docs intentionally omit: the retrieval science behind design choices, prompt engineering rationale, quality tuning parameters, failure mode diagnosis, and evaluation methodology.

---

## Transcript Cleaning

Apply lightweight cleaning to raw transcript segments **before** chunking. The goal is mechanical noise removal, not editorial revision.

### Do clean

- Remove repeated filler phrases caused by transcription glitches (e.g., "um um um um").
- Normalize whitespace: collapse multiple spaces, strip leading/trailing whitespace per segment.
- Fix obvious timestamp ordering violations (segment `start_time_seconds` ≥ preceding `end_time_seconds`).
- Remove empty segments (zero-length or whitespace-only `text`).
- Merge ultra-short fragments (under 5 words) into the adjacent segment when they form a natural continuation.
- Preserve speaker labels through any merge.
- Preserve original wording otherwise — the raw transcript is the citable evidence.

### Do not over-clean

- Do not rewrite the speaker's meaning, even if a sentence is incomplete.
- Do not summarize at this stage.
- Do not delete segments that seem uncertain or meandering — they may contain important terms.
- Do not remove product names, feature names, or company terminology because they look unusual. ASR often mangles these; see [Terminology & Cleanup Dictionaries](#terminology--cleanup-dictionaries).
- Do not normalize company-specific terminology to generic synonyms.

The transcript at this stage should be as close to the spoken source as possible. Claude contextualization (Step 4 in README → Ingestion Pipeline) will do the semantic enrichment.

---

## Chunking Strategy

The README specifies 600-word target chunks with 120-word overlap (acceptable range: 500–700 words, 100–150 overlap). This section explains why.

### Why 600 words

600 words is roughly 2–3 minutes of spoken presentation at webinar pace. It is large enough to contain a complete thought (a concept introduced, explained, and illustrated with an example) while small enough that a timestamp link lands the viewer near the relevant moment. Shorter chunks (< 300 words) fragment ideas and produce vague, context-poor retrieval units. Longer chunks (> 900 words) dilute the vector signal and make timestamps unhelpful.

### Preferred boundary types

When segment structure allows, prefer chunk boundaries at (in priority order):

1. Speaker change
2. Topic change or slide transition signal
3. Q&A boundary (question followed by answer from a different speaker)
4. Long pause in the transcript
5. Paragraph boundary in the text

Fall back to word-count chunking when structure is unavailable. The chunking service should never produce a chunk that starts or ends mid-sentence when a clean boundary exists within ±50 words.

### Why 120-word overlap

Overlap ensures that a concept discussed across a chunk boundary is fully represented in at least one chunk. Without overlap, a retrieval query that matches only the second half of a discussion would return a chunk that starts mid-explanation. The 120-word value covers approximately one paragraph of spoken content — enough to preserve trailing context without creating so much duplication that retrieval is dominated by near-identical chunks.

Overlap does not create duplicate answers if deduplication is applied at retrieval time. See [Hybrid Ranking → Deduplication Rules](#deduplication-rules).

### Human-debuggability rule

A developer inspecting a retrieved chunk in the `retrieval_logs` output should immediately understand why it matched. A chunk fails this test if it:

- Contains only greetings, housekeeping, or outro content with no substantive material
- Has no speaker attribution
- Has a timestamp range so large it is useless as a deep-link (> 10 minutes)
- Consists mostly of slide-reading with no explanation

The chunking service should track `chunk_index` (position within video) and `word_count` per chunk (see DATABASE.md → Core Schema → `004_create_chunks.sql`). Both fields aid debugging and future chunk-quality analysis.

---

## Contextualization Rationale

See README → Claude Prompts → `contextualize_chunk.txt` for the prompt definition. This section explains why contextualization is required and what it should produce.

### Why raw chunks fail at retrieval

Webinar transcripts contain speech patterns that break semantic search:

- **Vague pronouns**: "That's why you do it this way" — no referent is resolvable without context.
- **Callback references**: "As we showed on slide 3..." — the slide is not in the transcript.
- **Implicit subjects**: "The key insight is..." — which product, which workflow, which user?
- **Inside terminology**: product names used casually, features referenced by nickname.

Without a contextual wrapper, vector search cannot match these chunks against precise user questions.

### Weak vs. strong chunk example

**Raw chunk (weak for retrieval):**
```
Yeah, exactly. That's why you do it first. If you wait until after the next one, it gets harder to keep it from drifting.
```
This chunk is potentially high-value (it explains a sequencing requirement) but unretrievable — the embedding captures "drifting" in isolation with no semantic anchor.

**Contextualized chunk (strong for retrieval):**
```
This excerpt is from the Character Consistency Deep Dive webinar. The speaker explains that users should establish a locked reference image before beginning multi-shot generation, because delaying the reference until after the sequence starts makes identity drift harder to correct.

Original transcript: Yeah, exactly. That's why you do it first. If you wait until after the next one, it gets harder to keep it from drifting.
```
The embedding now captures: character consistency, locked reference, multi-shot, identity drift, sequencing — all concepts a user question is likely to contain.

### Schema additions from contextualization

The README's `contextualize_chunk.txt` prompt returns: `contextual_text`, `summary`, `topic_tags`, `questions_this_answers`. These map directly to `chunks` columns.

**Addition — not in README:** Add `important_terms` as a returned field and a stored column on `chunks`:

```sql
-- Add to 004_create_chunks.sql
important_terms  TEXT[]
```

`important_terms` is a Claude-identified list of product names, feature names, and domain terms that appear in the chunk and are likely to be exact-match searched. Example: `["locked reference", "identity drift", "multi-shot sequence"]`. This list feeds the keyword search expansion and the terminology dictionary matching described in [Terminology & Cleanup Dictionaries](#terminology--cleanup-dictionaries).

**Drop `retrieval_notes`**: RAG_PIPELINE's original source included a `retrieval_notes` field in the contextualization output. This is internal Claude reasoning about chunk quality and does not need to be stored. Discard it after the contextualization call.

### Optional: adjacent-chunk context

For complex webinar content, passing the previous chunk's `summary` to the contextualization prompt helps resolve callbacks and pronoun chains. This is optional for MVP: the `contextualize_chunk.txt` prompt already receives the full video title, date, speaker names, and timestamp, which resolves most ambiguity. Add previous/next summaries only if evaluation reveals a pattern of unresolved references.

---

## Embedding Strategy

See README → Ingestion Pipeline → Step 5 for the embedding input string format.

### Why embed enriched text, not raw text

The raw transcript is the evidence; the contextual text is the retrieval signal. Embedding raw text would produce vectors that match the surface language of the spoken answer (which is often vague) rather than the semantic content of what was explained. Embedding the enriched `contextual_text` — combined with the structured metadata prefix — aligns the vector space with the vocabulary users bring to their questions.

### Input composition rationale

The README's embedding input string is:
```
{video_title} | {webinar_date} | {speaker_names joined} | {summary} | {topic_tags joined} | {contextual_text}
```

Each field contributes a distinct signal:

| Field | Retrieval contribution |
|---|---|
| `video_title` | Enables title-keyword matching; boosts recall for "where did we talk about X" queries |
| `webinar_date` | Supports date-filtered or recency-weighted retrieval |
| `speaker_names` | Surfaces chunks when users ask "what did [speaker] say about…" |
| `summary` | Dense semantic signal; often the clearest expression of the chunk's main point |
| `topic_tags` | Controlled vocabulary that bridges colloquial user terms to technical content |
| `contextual_text` | Full enriched text with resolved references; primary semantic content |

Do not include `raw_text` in the embedding input. It adds noise (vague pronouns, fillers) that dilutes the signal from the enriched fields. `raw_text` is used for keyword search (tsvector) and for the verbatim `snippet` in source cards — not for embedding.

**Full example embedding payload:**
```
Character Consistency Deep Dive | 2026-04-12 | Product Lead | Explains why locked reference images help prevent identity drift. | character consistency, reference images, identity drift, multi-shot workflow | This excerpt is from the Character Consistency Deep Dive webinar. The speaker explains that users should establish a locked reference image before beginning multi-shot generation, because delaying the reference makes identity drift harder to correct. Original transcript: The safest way to keep the character consistent is to start with a locked reference...
```

---

## Hybrid Ranking

See README → Retrieval Pipeline for the service interface and merge logic. See DATABASE.md → Retrieval Queries for the vector and keyword SQL. This section adds the scoring formula and deduplication rules.

### Scoring formula

After merging vector and keyword result sets, compute a hybrid score for each chunk:

```
hybrid_score = 0.65 × normalized_vector_score
             + 0.25 × normalized_keyword_score
             + 0.10 × metadata_bonus
```

**Normalization:** Vector scores from pgvector cosine distance are already in [0, 1]. Keyword `ts_rank` scores are unbounded; normalize by dividing by the maximum `ts_rank` score in the current result set. If a chunk appeared in only one result set, set the other component to 0.

**Weights rationale:** Vector search carries most of the weight because semantic matching handles the broadest range of user phrasings. Keyword search gets a meaningful share (0.25) because exact product names and feature terms are critical in this domain and often missed by embedding models. The metadata bonus (0.10) prevents it from overpowering actual relevance while still rewarding signal-rich matches.

### Metadata bonus rules

Apply the following additive bonuses (each bonus is a fraction of the 0.10 ceiling; the combined metadata component is capped at 0.10):

| Condition | Bonus |
|---|---|
| A `search_terms` term appears verbatim in `video_title` | +0.04 |
| A `search_terms` term appears in `topic_tags` array | +0.03 |
| Query mentions a speaker name and `speaker_names` contains it | +0.02 |
| A `questions_this_answers` entry semantically matches the query | +0.02 |
| Query mentions a date and `webinar_date` matches | +0.01 |

Do not apply a bonus for `summary` matching — this is already captured by the keyword score. Do not let any single metadata bonus push an otherwise-weak chunk above a strong semantic match.

### Deduplication rules

The README's merge step deduplicates by `chunk_id`. Apply two additional deduplication passes:

**Timestamp-overlap deduplication:** If two chunks share the same `video_id` and their time ranges overlap by more than 50%, keep the one with the higher hybrid score and discard the other. This prevents the same 3-minute segment from appearing twice because overlap chunking produced two nearly identical chunks.

**Adjacent-chunk collapsing:** If two chunks share the same `video_id`, are consecutive by `chunk_index`, and both made the merged result set with strong scores, keep both — they represent genuinely different but related content. Collapse only if their `raw_text` similarity (simple character overlap) exceeds 70%, which indicates the overlap window dominated both chunks.

---

## Reranking Decision Logic

The README's retrieval service interface lists reranking as optional. See README → Claude Prompts → `rerank_chunks.txt` for the prompt.

### Use reranking when

- Vector and keyword results disagree significantly (top-3 differs between the two result sets with no overlap).
- The query is multi-part or conceptually complex (contains "and", "versus", "compared to", or multiple distinct topics).
- Multiple chunks in the merged set have hybrid scores within 0.05 of each other — the scoring formula cannot discriminate.
- Several chunks are suspected to be topically adjacent but contextually redundant (same example explained twice).

### Skip reranking when

- The merged top-3 chunks are clearly strong (hybrid score ≥ 0.75) and come from at least two different webinars.
- The corpus is small (< 200 chunks): the initial ranking is reliable enough and reranking adds Claude API latency with minimal recall improvement.
- Latency is the primary constraint for the current request.
- Running against the eval set for benchmarking (keep the pipeline deterministic; log a flag if reranking was skipped).

Reranking is most valuable when the library grows beyond a single webinar and query specificity varies widely.

---

## Query Categories & Answer Formatting

The `answer_from_chunks.txt` prompt (README → Claude Prompts) already instructs Claude to use numbered steps for how-to questions. The following category-specific formatting rules should be included as conditional instructions in that prompt or applied by `answer_service.py` when passing the question type to Claude.

### Optional: query classification

Add `backend/app/prompts/classify_question.txt` — an optional MVP enhancement. This prompt classifies the question type before answer synthesis and allows `answer_service.py` to inject formatting guidance.

**`prompts/classify_question.txt`** *(optional — not in README prompt list; add to `backend/app/prompts/` if implementing)*:
```
Classify the user's question type.

User question:
{{user_question}}

Return valid JSON only:
{
  "question_type": "definition | how_to | where | comparison | troubleshooting | strategy | unknown",
  "reason": "<one sentence>"
}
```

### Category formatting rules

| Question type | Example | Preferred answer structure |
|---|---|---|
| `definition` | "What is Brainstorm Mode?" | Definition sentence, context from webinar, one source card, related follow-ups |
| `how_to` | "How do I keep a character consistent?" | Numbered steps derived from webinar evidence, best-practice warnings, source timestamps per step |
| `where` | "Where did we talk about Ray 3.14?" | List of source moments with short explanation of each, timestamped cards |
| `comparison` | "What is the difference between Brainstorm Mode and Create Mode?" | Side-by-side bullets or table, cite evidence for each side, note if one side has weaker coverage |
| `troubleshooting` | "Why does my character keep changing?" | Likely causes from webinar evidence, workflow fixes from webinar evidence, source timestamps |
| `strategy` | "What should enterprise users do before a big campaign?" | Planning checklist or priority list, source-backed recommendations, caveat if policy is not explicit in evidence |
| `unknown` | Ambiguous question | Retrieve broadly, answer with stated uncertainty, suggest clarifying follow-up questions |

For all categories: cite every major claim with webinar title and timestamp. Do not fabricate steps, causes, or policy not present in the retrieved chunks.

---

## Confidence Calibration

The `answers.confidence` field (`"high" | "medium" | "low"`) must be set by Claude in the `answer_from_chunks.txt` response. Use these rules consistently:

### High

- Multiple chunks (≥ 2) directly answer the question with specific, concrete content.
- At least one chunk contains the exact concept, term, or workflow the user asked about.
- Sources are specific (timestamp range ≤ 5 minutes, clear speaker attribution).
- The answer is well-supported with no significant gaps.

### Medium

- One strong chunk directly answers the question, **or**
- Two or more chunks partially support the answer but each covers only part of it, **or**
- The answer requires mild synthesis across chunks from different webinars.
- No invented claims, but some aspects of the question are not fully addressed by available evidence.

### Low

- Chunks retrieved are topically related but do not directly answer the question.
- Sources mention the concept but do not explain it (e.g., a slide title is mentioned but not elaborated).
- The answer is primarily a pointer to related material rather than a direct response.
- Evidence is from a single weak chunk with a broad timestamp range.

When `confidence` is `"low"`, Claude should explicitly state what evidence is available and what is missing. Do not return `"low"` confidence and a confident-sounding answer.

---

## Failure Behavior

Four patterns require specific handling. The README's service interface covers the no-results case (return `not_enough_evidence` immediately when `chunks` is empty). The following patterns extend that.

### No results

No chunks retrieved from either vector or keyword search.

**Response:**
```json
{
  "answer": "I could not find enough evidence in the webinar library to answer that confidently.",
  "sources": [],
  "suggested_questions": [],
  "confidence": "low",
  "not_enough_evidence": true,
  "missing_evidence_note": "No relevant transcript chunks were retrieved for this question."
}
```

Return immediately without calling Claude for answer synthesis. Log the empty retrieval result to `retrieval_logs`.

### Weak results

Chunks retrieved are related but insufficient — the topic is adjacent but the specific question is not answered.

**Response pattern:** Claude should acknowledge what evidence exists and what it does not cover. Example phrasing: "The webinar library discusses reference images and identity drift, but does not directly address [the specific aspect asked about]." Include the closest source cards. Set `confidence: "low"` and `not_enough_evidence: false` (evidence exists; it just does not fully answer).

### Conflicting results

Two or more chunks from the same or different webinars express different approaches or recommendations.

**Response pattern:** Claude should surface the conflict rather than resolve it silently. Example: "Two webinar excerpts take different approaches here. [Webinar A, timestamp] recommends X, while [Webinar B, timestamp] emphasizes Y. Both point toward [shared underlying principle]." Cite both sources. Do not pick one and omit the other.

### Ambiguous question

The user's question is too broad or under-specified to retrieve meaningfully (e.g., "How do I make it better?").

**Response pattern:** For MVP, retrieve broadly and answer with explicit uncertainty. Include this in the answer: "I need more context to give you a precise answer from the webinar library. Based on what I retrieved, [best available answer]. Are you asking about [option A], [option B], or [option C]?" Use `suggested_questions` to surface the likely specific variants. Set `confidence: "low"`.

---

## Hallucination Guardrails

The README's hard rules (README → Constraints & Non-Negotiables) define the behavioral constraints. The following system-level instruction and implementation rules translate those constraints into Claude API call behavior.

### System-level instruction for answer synthesis

Prepend this instruction to the system turn of every `answer_from_chunks.txt` call:

```
You are not a general assistant right now.

You are a grounded answer engine for a private webinar library.

Your only knowledge source is the transcript excerpts provided in this request.

If the transcript excerpts do not support an answer, say so explicitly. Do not fill gaps with outside knowledge.
```

### Guardrail rules

These rules constrain `answer_service.py` behavior, not just prompt behavior:

- **No chunks = no synthesis.** If `chunks` is empty, return the `not_enough_evidence` response immediately without calling Claude. Do not send an empty chunks list and hope Claude refuses.
- **Validate citations.** After parsing Claude's JSON response, verify that every `chunk_id` in `sources` exists in the `chunks` list that was sent to Claude. Discard any source card referencing a `chunk_id` not in the input.
- **Reject invented feature names.** Maintain the terminology dictionary (see [Terminology & Cleanup Dictionaries](#terminology--cleanup-dictionaries)). If Claude's answer text contains a term not present in the retrieved chunks and not in the terminology dictionary, log a warning. Do not auto-correct — flag for manual review.
- **Fallback message is not negotiable.** The answer text `"I could not find enough evidence in the webinar library to answer that confidently."` is the canonical fallback. If `not_enough_evidence` is true, the `answer` field must contain this string (or a localized equivalent). Do not let Claude substitute a different refusal phrasing.
- **Snippet must be verbatim.** The `snippet` field in each source card must be a verbatim excerpt from `raw_text`, not a paraphrase. The answer synthesis prompt already specifies `"≤ 2 sentences"` — enforce this at parse time.

---

## Source Snippet Rules

The `snippet` field in each source card (see README → Answer Generation → `SourceCard`) must satisfy:

- **Length:** 200–500 characters. Long enough to be meaningful in context; short enough to display as an inline card without overwhelming the UI.
- **Verbatim:** The snippet must be copied directly from `raw_text` or `contextual_text`, not paraphrased. This is the evidence the user can verify against the video.
- **Directly related:** The snippet must contain or immediately surround the specific claim it supports. Do not use the opening sentence of a chunk as the snippet if the relevant claim appears later in the chunk.
- **Not a wall of text:** If the only relevant passage in the chunk is longer than 500 characters, truncate after a complete sentence and append `"…"`.

---

## Terminology & Cleanup Dictionaries

Two dictionaries support retrieval quality. Both live in `backend/fixtures/` as JSON files loaded by the ingestion and retrieval services.

### Product term alias dictionary

`backend/fixtures/terminology.json` — maps canonical product and feature names to their known aliases. Used during transcript cleanup, query rewrite synonym expansion, and keyword search term expansion.

```json
{
  "Luma Agents": ["Agents", "agent", "agentic workflow"],
  "Brainstorm Mode": ["brainstorm", "planning mode", "ideation mode"],
  "Create Mode": ["create", "execution mode", "generation mode"],
  "Ray 3.14": ["RayPi", "Ray 3.14", "3.14"],
  "reference image": ["character reference", "locked reference", "visual reference"]
}
```

**Query rewrite integration:** When `rewrite_query` returns `expanded_synonyms` *(Addition — not in README: `expanded_synonyms` is a useful field to add to the `rewrite_query.txt` prompt output alongside `rewritten_query`, `search_terms`, and `possible_topics`. See [Query Rewrite Additions](#query-rewrite-additions))*, cross-reference against this dictionary to add canonical term variants to the keyword search input.

**Transcript cleanup integration:** Apply alias corrections as a pre-chunking pass. Normalize clearly wrong transcription variants (e.g., "loom agents" → "Luma Agents") where context is unambiguous. Do not apply corrections where the surrounding context is unclear — flag for human review instead.

### ASR correction dictionary

`backend/fixtures/asr_corrections.json` — maps known ASR transcription errors for this webinar library to their correct forms.

```json
{
  "loom agents": "Luma Agents",
  "ray pie": "RayPi",
  "right click model": "Right-Click modal",
  "nano banana": "Nano Banana",
  "nana banana": "Nano Banana"
}
```

Apply these corrections during the transcript cleaning step before chunking. Apply carefully: do not blindly replace terms where context is unclear or where the phrase appears in a different semantic context (e.g., "model" used to mean "AI model" vs. "modal").

Both dictionaries should be human-maintained and updated after each ingestion run that reveals new ASR errors or product name variants.

### Query rewrite additions

**Addition — not in README:** Add `expanded_synonyms` to the `rewrite_query.txt` prompt output. The README's `rewrite_query.txt` returns `rewritten_query`, `search_terms`, and `possible_topics`. `expanded_synonyms` adds a flat list of term variants for keyword search expansion, derived from the Claude rewrite pass:

```json
{
  "rewritten_query": "...",
  "search_terms": ["..."],
  "possible_topics": ["..."],
  "expanded_synonyms": ["same character", "same person", "consistent face", "character reference", "identity drift"]
}
```

Drop `must_include_terms` and `ambiguity_notes` from the original RAG_PIPELINE source — these add Claude API cost without clear retrieval benefit in MVP. `expanded_synonyms` is the one addition with direct retrieval value.

---

## Common Failure Modes

### Failure mode 1: Answer sounds good but is unsupported

**Cause:** Claude filled gaps from general knowledge because the retrieved chunks were weak but not empty. Claude's instruction to stay grounded is probabilistic — it can be overridden by plausible-sounding general knowledge when evidence is thin.

**Fix:** Tighten the answer synthesis prompt with the system-level instruction block above. Add explicit instruction: "If a claim is not directly supported by the provided excerpts, do not include it." Increase the not-enough-evidence threshold by reducing `top_k` until only strong retrievals go to synthesis. Use the manual review rubric to identify recurrence patterns.

### Failure mode 2: Wrong chunks retrieved

**Cause:** Weak chunking (raw text without contextualization), vector-only retrieval missing exact product names, or missing keyword search component.

**Fix:** Ensure all chunks have `contextual_text` populated before any retrieval (check `videos.status = 'ready'` gate per DATABASE.md → Processing Lifecycle). Add keyword search if not yet implemented. Improve `topic_tags` quality in the contextualization prompt. Expand the eval question set to cover the failing query types.

### Failure mode 3: Too many near-duplicate chunks

**Cause:** Chunk overlap plus a query that strongly matches one section of a webinar produces 4–6 chunks from the same 10-minute window, consuming the entire `top_k` budget.

**Fix:** Apply timestamp-overlap deduplication (see [Hybrid Ranking → Deduplication Rules](#deduplication-rules)). Apply adjacent-chunk collapsing. If reranking is enabled, the reranker prompt already penalizes redundant chunks — use `rejected_chunk_ids` from the reranking response to log and skip duplicates.

### Failure mode 4: Product names missed

**Cause:** Embedding search misses exact product/feature names because the model generalizes them semantically. ASR has mangled the term in the transcript, so keyword search also misses it.

**Fix:** Apply ASR corrections before chunking. Expand keyword search input using the `expanded_synonyms` from the query rewrite. Ensure `important_terms` from contextualization is populated and indexed (use the `topic_tags` GIN index in `004_create_chunks.sql` as a model — a similar GIN index on `important_terms` is worth adding). Verify the terminology dictionary covers the missed term.

### Failure mode 5: Timestamp links are unhelpful

**Cause:** Chunks are too large (timestamp range spans 8–15 minutes), transcript timestamps are inaccurate, or the answer cites a broad range when a specific moment is the actual source.

**Fix:** Prefer smaller chunks by using natural boundaries aggressively. The `start_time_seconds` in the source card should be the timestamp of the specific relevant segment, not the beginning of the chunk. If transcript timestamps are inaccurate, flag during ingestion and set `videos.status = 'failed'`. Consider clipping the `video_url` start offset 5–10 seconds before the cited `start_time_seconds` to account for seek-to-timecode imprecision in video players.

---

## Debug Endpoint

Add the following development-only endpoint to `backend/app/api/routes_ask.py` or a separate `routes_debug.py`. Do not expose in production.

**`GET /debug/queries/{query_id}`** *(optional MVP endpoint — not in README API Endpoints)*:

```json
{
  "user_question": "...",
  "rewritten_question": "...",
  "search_terms": ["..."],
  "retrieved_chunks": [
    {
      "rank": 1,
      "retrieval_method": "merged",
      "score": 0.87,
      "video_title": "...",
      "display_time": "00:14:02–00:17:10",
      "summary": "...",
      "raw_text": "..."
    }
  ],
  "answer": "...",
  "source_chunk_ids": ["uuid", "uuid"],
  "confidence": "high",
  "not_enough_evidence": false
}
```

This endpoint joins `queries`, `retrieval_logs`, `chunks`, `videos`, and `answers` for the given `query_id`. It is the primary tool for diagnosing retrieval quality during development without writing raw SQL.

Guard with an environment check:
```python
if not settings.DEBUG:
    raise HTTPException(status_code=404)
```

Add `DEBUG=true` to `.env.example` as a non-secret development flag.

---

## Evaluation Methodology

The README defines the evaluation script interface and the eval fixture path (`backend/fixtures/eval_questions.json`). See README → Evaluation for the script output format and MVP target (≥ 80% correct-source-in-top-5). This section extends that with a 25-question eval structure, additional metrics, and a manual answer review rubric.

### Eval question set structure

Each eval question in `backend/fixtures/eval_questions.json` should include:

```json
{
  "question": "...",
  "expected_video_title": "...",
  "expected_terms": ["...", "..."],
  "expected_answer_behavior": "...",
  "question_type": "definition | how_to | where | comparison | troubleshooting | strategy",
  "notes": "..."
}
```

The README's base format includes `question`, `expected_video_title`, and `expected_terms`. Add `expected_answer_behavior`, `question_type`, and `notes` to enable category-level analysis of retrieval failures.

### Recommended 25-question set (5 per category)

Replace with questions grounded in your actual webinar library. These illustrate the coverage target:

**Definition (5):**
- "What are Luma Agents?"
- "What is Brainstorm Mode?"
- "What is Create Mode?"
- "What is identity drift?"
- "What is a locked reference image?"

**How-to (5):**
- "How do I keep a character consistent across multiple shots?"
- "How should I use reference images before generating a sequence?"
- "How do I set up a pre-flight checklist before a big campaign?"
- "How do I avoid identity drift?"
- "How do I use Brainstorm Mode to plan a project?"

**Troubleshooting (5):**
- "Why does my character's face keep changing between shots?"
- "Why is the model ignoring my reference image?"
- "What causes inconsistent results when generating multi-shot stories?"
- "Why are my prompt descriptions producing wrong characters?"
- "What mistakes do users make when using Agents?"

**Where-did-we-talk-about (5):**
- "Where did we talk about Ray 3.14?"
- "Where did we cover enterprise workflow setup?"
- "Where did we discuss using prompts versus references?"
- "Where did we talk about the Right-Click modal?"
- "Where was the onboarding workflow explained?"

**Comparison / strategy (5):**
- "What is the difference between Brainstorm Mode and Create Mode?"
- "What should enterprise users do before a big campaign?"
- "Should I use a text description or a reference image for character consistency?"
- "What did the webinars say about prompt-based versus reference-based workflows?"
- "How does the recommended workflow differ for single-shot versus multi-shot generation?"

### Retrieval eval metrics

The `test_retrieval.py` script (README → Evaluation) reports top-5 hit rate. Extend it to track:

| Metric | Definition |
|---|---|
| Top-1 accuracy | Expected video title appears in rank-1 chunk |
| Top-3 accuracy | Expected video title appears in top-3 chunks |
| Top-5 accuracy | Expected video title appears in top-5 chunks (primary MVP target) |
| Term coverage | Fraction of `expected_terms` found in the top-5 chunk texts |
| Groundedness rate | Fraction of manually reviewed answers where all claims are supported by cited chunks (manual review required) |
| Hallucination rate | Fraction of manually reviewed answers containing at least one unsupported claim (manual review required) |
| Not-enough-evidence correctness | For questions intentionally outside the webinar library: fraction that correctly returns `not_enough_evidence: true` |

Run `test_retrieval.py` after every significant change to chunking parameters, embedding model, or retrieval logic.

### Manual answer review rubric

Score each answer from 1 to 5. Use this rubric for the groundedness and hallucination metrics above.

**5 — Excellent:**
- Directly answers the question
- Uses only webinar evidence, no general-knowledge gap-filling
- Cites exact, useful timestamps
- Source cards match the cited claims
- No hallucinated feature names, policies, or terminology
- Suggested follow-ups are grounded in retrieved content

**4 — Good:**
- Mostly answers the question
- Sources are relevant and cited
- Minor vagueness or one uncited supporting detail
- No serious unsupported claims

**3 — Mixed:**
- Partially answers the question
- Some source cards are weak or loosely relevant
- Answer may be too generic or synthesizes too broadly
- Retrieval or synthesis needs improvement, but no clear hallucination

**2 — Poor:**
- Retrieves related but wrong material
- Answer is vague, incomplete, or misleading
- Citations do not directly support the claims made
- User would likely find this unhelpful

**1 — Failure:**
- Wrong answer, or answer contains invented feature names or policy
- Sources do not support the answer
- Obvious relevant webinar was missed entirely
- `not_enough_evidence` should have been returned but was not

Scores 1–2 should trigger a diagnostic pass: check retrieval logs via the debug endpoint to identify whether the failure is in retrieval (wrong chunks returned) or synthesis (right chunks, wrong answer).

---

## MVP Performance Targets

For the MVP corpus (5–10 webinars, hundreds to low thousands of chunks):

| Target | Value |
|---|---|
| Answer latency (p50) | < 10 seconds end-to-end |
| Answer latency (p95) | < 20 seconds |
| Retrieval: correct source in top-5 | ≥ 80% of eval questions |
| Retrieval: correct source in top-3 (aspirational) | ≥ 80% of eval questions |
| Manual review score | Average ≥ 3.5 across eval set |
| Hallucination rate | < 10% of reviewed answers |

Retrieval correctness is the only target that gates MVP readiness. Do not optimize latency or UI before the retrieval target is met. The `retrieval_logs` table provides the data for offline analysis; use the debug endpoint to inspect individual failures.
