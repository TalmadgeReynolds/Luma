/**
 * API client - all API calls go through here.
 *
 * Uses fetch() with proper error handling.
 */
import type {
  AskRequest,
  AskResponse,
  VideoListResponse,
  ChunkListResponse,
  HealthResponse,
  ErrorResponse,
} from '../types/api';

const API_BASE_URL = '';  // Empty string uses Vite proxy

/**
 * Base fetch wrapper with error handling.
 */
async function apiFetch<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${API_BASE_URL}${endpoint}`;

  try {
    const response = await fetch(url, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...options.headers,
      },
    });

    if (!response.ok) {
      // Try to parse error response
      let errorMessage = `HTTP ${response.status}: ${response.statusText}`;
      try {
        const errorData: ErrorResponse = await response.json();
        errorMessage = errorData.error?.message || errorMessage;
      } catch {
        // Failed to parse error, use status text
      }
      throw new Error(errorMessage);
    }

    return await response.json();
  } catch (error) {
    if (error instanceof Error) {
      throw error;
    }
    throw new Error('An unknown error occurred');
  }
}

/**
 * POST /ask - Submit a question
 */
export async function askQuestion(question: string): Promise<AskResponse> {
  const request: AskRequest = { question };
  return apiFetch<AskResponse>('/ask', {
    method: 'POST',
    body: JSON.stringify(request),
  });
}

/**
 * GET /videos - List all videos
 */
export async function listVideos(): Promise<VideoListResponse> {
  return apiFetch<VideoListResponse>('/videos');
}

/**
 * GET /videos/{video_id}/chunks - Get chunks for a video
 */
export async function getVideoChunks(videoId: string): Promise<ChunkListResponse> {
  return apiFetch<ChunkListResponse>(`/videos/${videoId}/chunks`);
}

/**
 * GET /health - Health check
 */
export async function healthCheck(): Promise<HealthResponse> {
  return apiFetch<HealthResponse>('/health');
}
