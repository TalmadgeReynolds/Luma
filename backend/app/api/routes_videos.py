"""
Video-related endpoints.
"""
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.models import Video, Chunk
from app.db.schemas import VideoListResponse, VideoSummary, ChunkListResponse, ChunkDetail
from app.services.answer_service import format_time_range

router = APIRouter()


@router.get("/videos", response_model=VideoListResponse)
async def list_videos(
    db_session: AsyncSession = Depends(get_db),
) -> VideoListResponse:
    """
    List all videos with chunk counts.

    Returns:
        List of videos with metadata
    """
    # Query videos with chunk counts
    query = (
        select(
            Video,
            func.count(Chunk.id).label("chunk_count")
        )
        .outerjoin(Chunk, Video.id == Chunk.video_id)
        .group_by(Video.id)
        .order_by(Video.created_at.desc())
    )

    result = await db_session.execute(query)
    rows = result.all()

    videos = []
    for row in rows:
        video = row[0]
        chunk_count = row[1]

        video_summary = VideoSummary(
            id=video.id,
            title=video.title,
            description=video.description,
            webinar_date=video.webinar_date,
            speakers=video.speakers or [],
            video_url=video.video_url,
            status=video.status,
            chunk_count=chunk_count,
        )
        videos.append(video_summary)

    return VideoListResponse(
        videos=videos,
        total=len(videos),
    )


@router.get("/videos/{video_id}/chunks", response_model=ChunkListResponse)
async def get_video_chunks(
    video_id: UUID,
    db_session: AsyncSession = Depends(get_db),
) -> ChunkListResponse:
    """
    Get all chunks for a specific video.

    Args:
        video_id: Video UUID

    Returns:
        List of chunks with metadata

    Raises:
        HTTPException: If video not found
    """
    # Get video
    video_query = select(Video).where(Video.id == video_id)
    video_result = await db_session.execute(video_query)
    video = video_result.scalar_one_or_none()

    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    # Get chunks
    chunks_query = (
        select(Chunk)
        .where(Chunk.video_id == video_id)
        .order_by(Chunk.chunk_index)
    )
    chunks_result = await db_session.execute(chunks_query)
    chunks = chunks_result.scalars().all()

    # Format chunks
    chunk_details = []
    for chunk in chunks:
        chunk_detail = ChunkDetail(
            id=chunk.id,
            video_id=chunk.video_id,
            start_time_seconds=chunk.start_time_seconds,
            end_time_seconds=chunk.end_time_seconds,
            display_time=format_time_range(chunk.start_time_seconds, chunk.end_time_seconds),
            raw_text=chunk.raw_text,
            contextual_text=chunk.contextual_text,
            summary=chunk.summary,
            topic_tags=chunk.topic_tags or [],
            questions_answered=chunk.questions_answered or [],
            speaker_names=chunk.speaker_names or [],
            chunk_index=chunk.chunk_index,
            word_count=chunk.word_count,
        )
        chunk_details.append(chunk_detail)

    return ChunkListResponse(
        video_id=video.id,
        video_title=video.title,
        chunks=chunk_details,
        total=len(chunk_details),
    )
