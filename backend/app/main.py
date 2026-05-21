"""
FastAPI application entry point.
"""
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.api import routes_ask, routes_videos, routes_ingest

settings = get_settings()

# Create FastAPI application
app = FastAPI(
    title="Webinar Library Answer Engine",
    description="RAG-powered answer engine over timestamped webinar transcripts",
    version="0.1.0",
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],  # Frontend dev servers
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve video files from backend/videos/ at /videos
_VIDEOS_DIR = Path(__file__).parent.parent / "videos"
_VIDEOS_DIR.mkdir(exist_ok=True)
app.mount("/videos", StaticFiles(directory=str(_VIDEOS_DIR)), name="videos")

# Register routers
app.include_router(routes_ingest.router, tags=["health"])
app.include_router(routes_ask.router, tags=["ask"])
app.include_router(routes_videos.router, tags=["videos"])


@app.get("/")
async def root():
    """Root endpoint with basic info."""
    return {
        "service": "webinar-answer-engine",
        "version": "0.1.0",
        "status": "running"
    }
