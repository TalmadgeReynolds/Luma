"""Application configuration using Pydantic Settings."""
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database
    DATABASE_URL: str = Field(
        description="PostgreSQL connection string with asyncpg driver"
    )

    # Anthropic / Claude
    ANTHROPIC_API_KEY: str = Field(description="Anthropic API key")
    ANTHROPIC_WORKSPACE: str | None = Field(
        default=None,
        description="Anthropic workspace ID (for workspace-scoped keys)"
    )
    CLAUDE_MODEL: str = Field(
        default="claude-sonnet-4-20250514",
        description="Claude model identifier"
    )

    # Embedding Provider
    EMBEDDING_PROVIDER: str = Field(
        description="Embedding provider: 'voyage' or 'openai'"
    )
    EMBEDDING_MODEL: str = Field(
        description="Embedding model name"
    )
    EMBEDDING_DIMENSION: int = Field(
        description="Vector dimension for embeddings"
    )

    # API Keys
    VOYAGE_API_KEY: str | None = Field(
        default=None,
        description="Voyage AI API key (required if EMBEDDING_PROVIDER='voyage')"
    )
    OPENAI_API_KEY: str | None = Field(
        default=None,
        description="OpenAI API key (required if EMBEDDING_PROVIDER='openai')"
    )

    # Transcription
    TRANSCRIPTION_PROVIDER: str = Field(
        default="json",
        description="Transcription provider: 'whisper', 'deepgram', 'assemblyai', or 'json'"
    )
    ASSEMBLYAI_API_KEY: str | None = Field(
        default=None,
        description="AssemblyAI API key (required if TRANSCRIPTION_PROVIDER='assemblyai')"
    )
    DEEPGRAM_API_KEY: str | None = Field(
        default=None,
        description="Deepgram API key (required if TRANSCRIPTION_PROVIDER='deepgram')"
    )

    # API access
    API_KEY: str | None = Field(default=None, description="API key for external access (X-API-Key header)")

    # Video
    VIDEO_BASE_URL: str = Field(
        default="http://localhost:8000/videos",
        description="Base URL for video files"
    )

    @field_validator("EMBEDDING_DIMENSION")
    @classmethod
    def validate_dimension_matches_model(cls, v: int, info) -> int:
        """Validate that EMBEDDING_DIMENSION matches the chosen EMBEDDING_MODEL."""
        model = info.data.get("EMBEDDING_MODEL")

        if model == "voyage-3-large" and v != 1024:
            raise ValueError(
                "voyage-3-large requires EMBEDDING_DIMENSION=1024, "
                f"but got {v}"
            )
        if model == "text-embedding-3-small" and v != 1536:
            raise ValueError(
                "text-embedding-3-small requires EMBEDDING_DIMENSION=1536, "
                f"but got {v}"
            )

        return v

    @field_validator("VOYAGE_API_KEY")
    @classmethod
    def validate_voyage_key(cls, v: str | None, info) -> str | None:
        """Validate that VOYAGE_API_KEY is provided when using Voyage provider."""
        provider = info.data.get("EMBEDDING_PROVIDER")
        if provider == "voyage" and not v:
            raise ValueError(
                "VOYAGE_API_KEY is required when EMBEDDING_PROVIDER='voyage'"
            )
        return v

    @field_validator("OPENAI_API_KEY")
    @classmethod
    def validate_openai_key(cls, v: str | None, info) -> str | None:
        """Validate that OPENAI_API_KEY is provided when using OpenAI provider."""
        provider = info.data.get("EMBEDDING_PROVIDER")
        if provider == "openai" and not v:
            raise ValueError(
                "OPENAI_API_KEY is required when EMBEDDING_PROVIDER='openai'"
            )
        return v

    class Config:
        env_file = ".env"
        case_sensitive = True


# Global settings instance
_settings: Settings | None = None


def get_settings() -> Settings:
    """Get or create the global settings instance."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
