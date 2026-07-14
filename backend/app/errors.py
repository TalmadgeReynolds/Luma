"""Domain exception classes for the application."""


class IngestionError(Exception):
    """Raised when ingestion pipeline encounters an error."""
    pass


class ChunkingError(Exception):
    """Raised when chunking fails."""
    pass


class RetrievalError(Exception):
    """Raised when retrieval pipeline encounters an error."""
    pass


class ClaudeServiceError(Exception):
    """Raised when Claude API calls fail."""
    pass


class EmbeddingError(Exception):
    """Raised when embedding service encounters an error."""
    pass


class DatabaseError(Exception):
    """Raised when database operations fail."""
    pass


class AnswerServiceError(Exception):
    """Raised when answer generation fails."""
    pass
