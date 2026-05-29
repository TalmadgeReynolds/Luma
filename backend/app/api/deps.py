from fastapi import Header, HTTPException
from app.config import get_settings


async def verify_api_key(x_api_key: str = Header(..., description="API key for access")):
    settings = get_settings()
    if settings.API_KEY and x_api_key != settings.API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")
