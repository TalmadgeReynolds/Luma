"""Saved items CRUD endpoints."""
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.models import SavedItem
from app.db.schemas import SavedItemCreate, SavedItemListResponse, SavedItemResponse

router = APIRouter()


def _to_response(item: SavedItem) -> SavedItemResponse:
    return SavedItemResponse(
        id=item.id,
        type=item.type,
        label=item.label,
        detail=item.detail,
        savedAt=item.saved_at.isoformat(),
    )


@router.get("/saved", response_model=SavedItemListResponse)
async def list_saved_items(
    x_session_id: str = Header(..., description="Client session UUID"),
    db: AsyncSession = Depends(get_db),
) -> SavedItemListResponse:
    result = await db.execute(
        select(SavedItem)
        .where(SavedItem.session_id == x_session_id)
        .order_by(SavedItem.saved_at.asc())
    )
    items = result.scalars().all()
    responses = [_to_response(i) for i in items]
    return SavedItemListResponse(items=responses, total=len(responses))


@router.post("/saved", response_model=SavedItemResponse, status_code=201)
async def create_saved_item(
    body: SavedItemCreate,
    x_session_id: str = Header(..., description="Client session UUID"),
    db: AsyncSession = Depends(get_db),
) -> SavedItemResponse:
    item = SavedItem(
        session_id=x_session_id,
        type=body.type,
        label=body.label,
        detail=body.detail,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return _to_response(item)


@router.delete("/saved/{item_id}", status_code=204)
async def delete_saved_item(
    item_id: UUID,
    x_session_id: str = Header(..., description="Client session UUID"),
    db: AsyncSession = Depends(get_db),
) -> None:
    result = await db.execute(
        select(SavedItem).where(
            SavedItem.id == item_id,
            SavedItem.session_id == x_session_id,
        )
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    await db.execute(
        delete(SavedItem).where(SavedItem.id == item_id)
    )
    await db.commit()
