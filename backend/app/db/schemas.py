"""
Pydantic schemas for API request/response validation.
"""
from datetime import date
from uuid import UUID
from pydantic import BaseModel, Field


# ============================================================================
# POST /ask - Main query endpoint
# ============================================================================

class AskRequest(BaseModel):
    """Request to ask a question."""
    question: str = Field(..., min_length=1, max_length=1000)


class SourceCard(BaseModel):
    """A source excerpt with video link."""
    chunk_id: UUID
    video_id: UUID
    video_title: str
    video_url: str  # Includes ?t={start_time_seconds} parameter
    start_time_seconds: float
    end_time_seconds: float
    display_time: str  # Formatted as "HH:MM:SS–HH:MM:SS"
    excerpt: str  # contextual_text or summary
    speaker_names: list[str]


class AskResponse(BaseModel):
    """Response to a question with answer and sources."""
    answer: str
    sources: list[SourceCard]
    suggested_questions: list[str] = Field(default_factory=list)
    confidence: str  # "high" | "medium" | "low"
    not_enough_evidence: bool = False


# ============================================================================
# GET /videos - List all videos
# ============================================================================

class VideoSummary(BaseModel):
    """Summary of a video."""
    id: UUID
    title: str
    description: str | None
    webinar_date: date | None
    speakers: list[str]
    video_url: str | None
    status: str  # "processing" | "contextualized" | "embedded" | "failed"
    chunk_count: int


class VideoListResponse(BaseModel):
    """Response with list of videos."""
    videos: list[VideoSummary]
    total: int


# ============================================================================
# GET /videos/{video_id}/chunks - Get chunks for a video
# ============================================================================

class ChunkDetail(BaseModel):
    """Detailed chunk information."""
    id: UUID
    video_id: UUID
    start_time_seconds: float
    end_time_seconds: float
    display_time: str  # Formatted as "HH:MM:SS–HH:MM:SS"
    raw_text: str
    contextual_text: str
    summary: str | None
    topic_tags: list[str]
    questions_answered: list[str]
    speaker_names: list[str]
    chunk_index: int
    word_count: int


class ChunkListResponse(BaseModel):
    """Response with list of chunks."""
    video_id: UUID
    video_title: str
    chunks: list[ChunkDetail]
    total: int


# ============================================================================
# GET /health - Health check
# ============================================================================

class HealthResponse(BaseModel):
    """Health check response."""
    status: str = "ok"


# ============================================================================
# Error responses
# ============================================================================

class ErrorDetail(BaseModel):
    """Error detail information."""
    code: str
    message: str
    details: dict | None = None


class ErrorResponse(BaseModel):
    """Standard error response."""
    error: ErrorDetail
