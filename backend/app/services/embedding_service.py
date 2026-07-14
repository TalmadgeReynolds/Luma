"""
Embedding service - handles text-to-vector conversion.

Supports multiple providers:
- Voyage AI (voyage-3-large, 1024-dim)
- OpenAI (text-embedding-3-small, 1536-dim)

Provider is selected via EMBEDDING_PROVIDER env var.
"""
from openai import AsyncOpenAI
import voyageai

from app.config import get_settings
from app.errors import EmbeddingError

settings = get_settings()

# Initialize clients based on provider
_voyage_client = None
_openai_client = None

if settings.EMBEDDING_PROVIDER == "voyage":
    if not settings.VOYAGE_API_KEY:
        raise EmbeddingError("VOYAGE_API_KEY is required when EMBEDDING_PROVIDER='voyage'")
    _voyage_client = voyageai.Client(api_key=settings.VOYAGE_API_KEY)
    print(f"✓ Initialized Voyage AI client (model: {settings.EMBEDDING_MODEL})")

elif settings.EMBEDDING_PROVIDER == "openai":
    if not settings.OPENAI_API_KEY:
        raise EmbeddingError("OPENAI_API_KEY is required when EMBEDDING_PROVIDER='openai'")
    _openai_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    print(f"✓ Initialized OpenAI client (model: {settings.EMBEDDING_MODEL})")

else:
    raise EmbeddingError(
        f"Unknown EMBEDDING_PROVIDER: {settings.EMBEDDING_PROVIDER}. "
        "Must be 'voyage' or 'openai'"
    )

# ---------------------------------------------------------------------------
# Embedding cache (in-process LRU, max 1000 entries ≈ 4 MB at 1024-dim)
# ---------------------------------------------------------------------------
_embedding_cache: dict[str, list[float]] = {}
_EMBEDDING_CACHE_MAX = 1000


async def embed_text(text: str) -> list[float]:
    """
    Convert text to embedding vector.

    Args:
        text: Input text to embed

    Returns:
        List of floats representing the embedding vector

    Raises:
        EmbeddingError: If embedding fails or dimension mismatch
    """
    # Check cache before hitting the API
    if text in _embedding_cache:
        print(f"[Embedding] Cache hit ({len(_embedding_cache)} entries)")
        return _embedding_cache[text]

    try:
        if settings.EMBEDDING_PROVIDER == "voyage":
            # Voyage AI uses sync client
            result = _voyage_client.embed(
                texts=[text],
                model=settings.EMBEDDING_MODEL,
            )
            embedding = result.embeddings[0]

        elif settings.EMBEDDING_PROVIDER == "openai":
            # OpenAI uses async client
            response = await _openai_client.embeddings.create(
                input=text,
                model=settings.EMBEDDING_MODEL,
            )
            embedding = response.data[0].embedding

        else:
            raise EmbeddingError(f"Unknown provider: {settings.EMBEDDING_PROVIDER}")

        # Validate dimension
        if len(embedding) != settings.EMBEDDING_DIMENSION:
            raise EmbeddingError(
                f"Embedding dimension mismatch: got {len(embedding)}, "
                f"expected {settings.EMBEDDING_DIMENSION} for model {settings.EMBEDDING_MODEL}"
            )

        # Store in cache, evicting oldest entry if full
        if len(_embedding_cache) >= _EMBEDDING_CACHE_MAX:
            _embedding_cache.pop(next(iter(_embedding_cache)))
        _embedding_cache[text] = embedding

        return embedding

    except EmbeddingError:
        # Re-raise our own errors
        raise
    except Exception as e:
        raise EmbeddingError(
            f"Embedding failed with provider {settings.EMBEDDING_PROVIDER}: {e}"
        ) from e


async def embed_texts_batch(texts: list[str]) -> list[list[float]]:
    """
    Convert multiple texts to embeddings (batch operation).

    Args:
        texts: List of input texts

    Returns:
        List of embedding vectors

    Raises:
        EmbeddingError: If any embedding fails
    """
    try:
        if settings.EMBEDDING_PROVIDER == "voyage":
            # Voyage AI supports batch natively
            result = _voyage_client.embed(
                texts=texts,
                model=settings.EMBEDDING_MODEL,
            )
            embeddings = result.embeddings

        elif settings.EMBEDDING_PROVIDER == "openai":
            # OpenAI also supports batch
            response = await _openai_client.embeddings.create(
                input=texts,
                model=settings.EMBEDDING_MODEL,
            )
            embeddings = [item.embedding for item in response.data]

        else:
            raise EmbeddingError(f"Unknown provider: {settings.EMBEDDING_PROVIDER}")

        # Validate all dimensions
        for i, embedding in enumerate(embeddings):
            if len(embedding) != settings.EMBEDDING_DIMENSION:
                raise EmbeddingError(
                    f"Embedding {i} dimension mismatch: got {len(embedding)}, "
                    f"expected {settings.EMBEDDING_DIMENSION}"
                )

        return embeddings

    except EmbeddingError:
        raise
    except Exception as e:
        raise EmbeddingError(
            f"Batch embedding failed with provider {settings.EMBEDDING_PROVIDER}: {e}"
        ) from e
