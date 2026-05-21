/**
 * TypeScript types for API requests and responses.
 *
 * SINGLE SOURCE OF TRUTH for all API types.
 * Must match backend Pydantic schemas exactly.
 */

// ============================================================================
// POST /ask
// ============================================================================

export interface AskRequest {
  question: string;
}

export interface SourceCard {
  chunk_id: string;
  video_id: string;
  video_title: string;
  video_url: string;  // Includes ?t={start_time_seconds}
  start_time_seconds: number;
  end_time_seconds: number;
  display_time: string;  // "HH:MM:SS–HH:MM:SS"
  excerpt: string;
  speaker_names: string[];
}

export interface AskResponse {
  answer: string;
  sources: SourceCard[];
  suggested_questions: string[];
  confidence: "high" | "medium" | "low";
  not_enough_evidence: boolean;
}

// ============================================================================
// GET /videos
// ============================================================================

export interface VideoSummary {
  id: string;
  title: string;
  description: string | null;
  webinar_date: string | null;  // ISO date string
  speakers: string[];
  video_url: string | null;
  status: "processing" | "contextualized" | "embedded" | "failed";
  chunk_count: number;
}

export interface VideoListResponse {
  videos: VideoSummary[];
  total: number;
}

// ============================================================================
// GET /videos/{video_id}/chunks
// ============================================================================

export interface ChunkDetail {
  id: string;
  video_id: string;
  start_time_seconds: number;
  end_time_seconds: number;
  display_time: string;
  raw_text: string;
  contextual_text: string;
  summary: string | null;
  topic_tags: string[];
  questions_answered: string[];
  speaker_names: string[];
  chunk_index: number;
  word_count: number;
}

export interface ChunkListResponse {
  video_id: string;
  video_title: string;
  chunks: ChunkDetail[];
  total: number;
}

// ============================================================================
// GET /health
// ============================================================================

export interface HealthResponse {
  status: string;
}

// ============================================================================
// Error responses
// ============================================================================

export interface ErrorDetail {
  code: string;
  message: string;
  details?: Record<string, unknown>;
}

export interface ErrorResponse {
  error: ErrorDetail;
}
