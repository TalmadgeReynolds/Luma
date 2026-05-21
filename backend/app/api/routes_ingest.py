"""
Health check and system endpoints.
"""
from fastapi import APIRouter

from app.db.schemas import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """
    Health check endpoint.

    Returns:
        Status: ok
    """
    return HealthResponse(status="ok")
