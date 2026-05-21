"""
Claude service - handles all interactions with Claude API.

Loads prompts at module import time and provides async functions for:
- contextualize_chunk: Enrich chunks with metadata
- rewrite_query: Optimize user questions for retrieval
- answer_from_chunks: Generate grounded answers
- rerank_chunks: Rerank candidate chunks (optional)
"""
import json
from pathlib import Path

from anthropic import AsyncAnthropic

from app.config import get_settings
from app.errors import ClaudeServiceError

settings = get_settings()

# Initialize Claude client
client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

# Load all prompts at module import time
PROMPTS: dict[str, str] = {}


def _load_prompts():
    """Load all prompt templates from the prompts/ directory."""
    prompt_dir = Path(__file__).parent.parent / "prompts"

    if not prompt_dir.exists():
        raise ClaudeServiceError(f"Prompts directory not found: {prompt_dir}")

    for prompt_file in prompt_dir.glob("*.txt"):
        prompt_name = prompt_file.stem
        PROMPTS[prompt_name] = prompt_file.read_text()
        print(f"✓ Loaded prompt: {prompt_name}")


# Load prompts when module is imported
_load_prompts()


def _render_template(template: str, **kwargs) -> str:
    """
    Render a prompt template with variables.

    Uses simple string replacement: {{variable_name}} → value
    """
    result = template
    for key, value in kwargs.items():
        placeholder = f"{{{{{key}}}}}"
        result = result.replace(placeholder, str(value))
    return result


async def _call_claude(prompt: str, *, max_retries: int = 5, backoff_base: float = 1.5, max_backoff: int = 60) -> dict:
    """
    Call Claude API and parse JSON response with retries on transient errors (e.g. rate limits).

    Args:
        prompt: The complete prompt to send
        max_retries: Number of retry attempts on transient failures (default 5)
        backoff_base: Exponential backoff base multiplier
        max_backoff: Maximum backoff seconds

    Returns:
        Parsed JSON response as dict

    Raises:
        ClaudeServiceError: If API call fails or JSON is invalid after retries
    """
    import asyncio
    import random

    attempt = 0
    while True:
        try:
            response = await client.messages.create(
                model=settings.CLAUDE_MODEL,
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}],
            )

            # Extract text content
            content = response.content[0].text

            # Strip markdown code blocks if present
            content = content.strip()
            if content.startswith("```json"):
                content = content[7:]
            elif content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()

            # Parse JSON
            try:
                return json.loads(content)
            except json.JSONDecodeError as e:
                # For invalid JSON, treat as transient and retry up to max_retries
                if attempt < max_retries:
                    attempt += 1
                    wait = min(max_backoff, (backoff_base ** attempt) + random.uniform(0, 1))
                    print(f"Warning: Invalid JSON from Claude, retrying in {wait:.1f}s... (attempt {attempt}/{max_retries})")
                    await asyncio.sleep(wait)
                    continue
                raise ClaudeServiceError(
                    f"Claude returned invalid JSON after {attempt + 1} attempts: {e}\nResponse: {content[:500]}"
                ) from e

        except Exception as e:
            # Determine if error looks like a rate limit / transient error
            msg = str(e).lower()
            is_rate_limit = "rate" in msg or "429" in msg or "rate_limit" in msg or "rate-limit" in msg

            if attempt < max_retries and is_rate_limit:
                attempt += 1
                wait = min(max_backoff, (backoff_base ** attempt) + random.uniform(0, 1))
                print(f"Claude API rate-limited (attempt {attempt}/{max_retries}). Backing off {wait:.1f}s and retrying...")
                await asyncio.sleep(wait)
                continue

            # If not retrying, raise wrapped error
            raise ClaudeServiceError(f"Claude API call failed: {e}") from e


async def contextualize_chunk(
    video_title: str,
    webinar_date: str,
    speaker_names: list[str],
    start_time: str,
    end_time: str,
    raw_chunk_text: str,
) -> dict:
    """
    Enrich a chunk with contextual information using Claude.

    Returns dict with keys:
    - contextual_text: Enhanced text with context
    - summary: One-sentence summary
    - topic_tags: List of topic tags
    - questions_this_answers: List of questions this chunk answers
    """
    prompt = _render_template(
        PROMPTS["contextualize_chunk"],
        video_title=video_title,
        webinar_date=webinar_date or "Unknown",
        speaker_names=", ".join(speaker_names) if speaker_names else "Unknown",
        start_time=start_time,
        end_time=end_time,
        raw_chunk_text=raw_chunk_text,
    )

    result = await _call_claude(prompt)

    # Validate response has required keys
    required_keys = ["contextual_text", "summary", "topic_tags", "questions_this_answers"]
    missing = [k for k in required_keys if k not in result]
    if missing:
        raise ClaudeServiceError(
            f"Claude response missing required keys: {missing}\n"
            f"Got: {list(result.keys())}"
        )

    return result


async def rewrite_query(user_question: str) -> dict:
    """
    Rewrite a user question to improve retrieval recall.

    Returns dict with keys:
    - rewritten_query: Expanded query string
    - search_terms: List of search terms
    - possible_topics: List of possible topics
    """
    prompt = _render_template(
        PROMPTS["rewrite_query"],
        user_question=user_question,
    )

    result = await _call_claude(prompt)

    # Validate response
    required_keys = ["rewritten_query", "search_terms", "possible_topics"]
    missing = [k for k in required_keys if k not in result]
    if missing:
        raise ClaudeServiceError(
            f"Claude response missing required keys: {missing}"
        )

    return result


async def answer_from_chunks(
    user_question: str,
    retrieved_chunks: str,
) -> dict:
    """
    Generate a grounded answer from retrieved chunks.

    Args:
        user_question: The original user question
        retrieved_chunks: Formatted string of retrieved chunks

    Returns dict with keys:
    - answer: Answer text
    - sources: List of source cards
    - suggested_questions: List of follow-up questions
    - confidence: "high" | "medium" | "low"
    - not_enough_evidence: bool
    """
    prompt = _render_template(
        PROMPTS["answer_from_chunks"],
        user_question=user_question,
        retrieved_chunks=retrieved_chunks,
    )

    result = await _call_claude(prompt)

    # Validate response
    required_keys = ["answer", "sources", "suggested_questions", "confidence", "not_enough_evidence"]
    missing = [k for k in required_keys if k not in result]
    if missing:
        raise ClaudeServiceError(
            f"Claude response missing required keys: {missing}"
        )

    return result


async def rerank_chunks(
    user_question: str,
    candidate_chunks: str,
) -> dict:
    """
    Rerank candidate chunks by relevance (optional).

    Returns dict with keys:
    - ranked_chunk_ids: List of chunk IDs in ranked order
    - reasoning_summary: One-sentence reasoning
    """
    prompt = _render_template(
        PROMPTS["rerank_chunks"],
        user_question=user_question,
        candidate_chunks=candidate_chunks,
    )

    result = await _call_claude(prompt)

    # Validate response
    required_keys = ["ranked_chunk_ids", "reasoning_summary"]
    missing = [k for k in required_keys if k not in result]
    if missing:
        raise ClaudeServiceError(
            f"Claude response missing required keys: {missing}"
        )

    return result
