"""
News API Routes

Provides endpoints for reading, filtering, and managing news items.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.deps import get_current_user
from app.db.mongo import get_db
from app.schemas.response import ResponseBase, success_response
from app.schemas.news import (
    NewsItemResponse,
    NewsItemBrief,
    NewsStateUpdate,
    NewsMetadata,
)
from app.schemas.user import UserInDB

router = APIRouter(prefix="/news", tags=["News"])


def news_doc_to_response(doc: dict) -> NewsItemResponse:
    """Convert MongoDB document to NewsItemResponse."""
    return NewsItemResponse(
        id=str(doc["_id"]),
        source_id=doc["source_id"],
        source_name=doc["source_name"],
        source_type=doc["source_type"],
        title=doc["title"],
        url=doc["url"],
        description=doc.get("description"),
        content=doc.get("content"),
        image_url=doc.get("image_url"),
        published_at=doc.get("published_at"),
        tags=doc.get("tags", []),
        metadata=NewsMetadata(**doc.get("metadata", {})),
        is_read=doc.get("is_read", False),
        is_starred=doc.get("is_starred", False),
        crawled_at=doc.get("crawled_at", datetime.utcnow()),
        proxied_image_url=None,  # TODO: Implement image proxy
    )


def news_doc_to_brief(doc: dict) -> NewsItemBrief:
    """Convert MongoDB document to NewsItemBrief for list views."""
    return NewsItemBrief(
        id=str(doc["_id"]),
        title=doc["title"],
        url=doc["url"],
        description=doc.get("description"),
        image_url=doc.get("image_url"),
        source_name=doc["source_name"],
        published_at=doc.get("published_at"),
        tags=doc.get("tags", []),
        is_read=doc.get("is_read", False),
        is_starred=doc.get("is_starred", False),
    )


@router.get("", response_model=ResponseBase[List[NewsItemBrief]])
async def list_news(
    source_id: Optional[str] = Query(None, description="Filter by source ID"),
    tag: Optional[str] = Query(None, description="Filter by tag"),
    is_starred: Optional[bool] = Query(None, description="Filter starred items"),
    is_read: Optional[bool] = Query(None, description="Filter read/unread items"),
    start_date: Optional[datetime] = Query(None, description="Filter from date"),
    end_date: Optional[datetime] = Query(None, description="Filter to date"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    sort_by: str = Query("crawled_at", description="Sort by: crawled_at, published_at"),
    current_user: UserInDB = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    List news items for the current user.

    - Supports filtering by source, tags, starred, read status
    - Supports date range filtering
    - Sorted by crawl time (newest first) by default
    """
    query: Dict[str, Any] = {"user_id": current_user.id}

    if source_id:
        query["source_id"] = source_id

    if tag:
        query["tags"] = tag

    if is_starred is not None:
        query["is_starred"] = is_starred

    if is_read is not None:
        query["is_read"] = is_read

    if start_date:
        query.setdefault("crawled_at", {})["$gte"] = start_date

    if end_date:
        query.setdefault("crawled_at", {})["$lte"] = end_date

    # Determine sort field
    sort_field = sort_by if sort_by in ["crawled_at", "published_at"] else "crawled_at"

    cursor = db.news.find(query).sort(sort_field, -1).skip(skip).limit(limit)
    news_items = await cursor.to_list(length=limit)

    return success_response(data=[news_doc_to_brief(doc) for doc in news_items])


@router.get("/count", response_model=ResponseBase[dict])
async def get_news_count(
    source_id: Optional[str] = Query(None),
    is_starred: Optional[bool] = Query(None),
    is_read: Optional[bool] = Query(None),
    current_user: UserInDB = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Get count of news items matching filters."""
    query: Dict[str, Any] = {"user_id": current_user.id}

    if source_id:
        query["source_id"] = source_id

    if is_starred is not None:
        query["is_starred"] = is_starred

    if is_read is not None:
        query["is_read"] = is_read

    count = await db.news.count_documents(query)

    return success_response(data={"count": count})


@router.get("/stats", response_model=ResponseBase[dict])
async def get_news_stats(
    current_user: UserInDB = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Get news statistics for the current user."""
    pipeline = [
        {"$match": {"user_id": current_user.id}},
        {
            "$group": {
                "_id": None,
                "total": {"$sum": 1},
                "unread": {"$sum": {"$cond": [{"$eq": ["$is_read", False]}, 1, 0]}},
                "starred": {"$sum": {"$cond": ["$is_starred", 1, 0]}},
            }
        },
    ]

    result = await db.news.aggregate(pipeline).to_list(length=1)

    if result:
        stats = result[0]
        stats.pop("_id", None)
    else:
        stats = {"total": 0, "unread": 0, "starred": 0}

    return success_response(data=stats)


@router.get("/{news_id}", response_model=ResponseBase[NewsItemResponse])
async def get_news_item(
    news_id: str,
    current_user: UserInDB = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Get a specific news item by ID."""
    try:
        oid = ObjectId(news_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid news ID format"
        )

    news_item = await db.news.find_one({"_id": oid, "user_id": current_user.id})

    if not news_item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="News item not found"
        )

    return success_response(data=news_doc_to_response(news_item))


@router.patch("/{news_id}", response_model=ResponseBase[NewsItemBrief])
async def update_news_state(
    news_id: str,
    update_data: NewsStateUpdate,
    current_user: UserInDB = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Update news item read/starred state."""
    try:
        oid = ObjectId(news_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid news ID format"
        )

    # Check item exists and belongs to user
    news_item = await db.news.find_one({"_id": oid, "user_id": current_user.id})

    if not news_item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="News item not found"
        )

    # Build update document
    update_fields = {"updated_at": datetime.utcnow()}

    if update_data.is_read is not None:
        update_fields["is_read"] = update_data.is_read
        if update_data.is_read:
            update_fields["read_at"] = datetime.utcnow()

    if update_data.is_starred is not None:
        update_fields["is_starred"] = update_data.is_starred

    await db.news.update_one({"_id": oid}, {"$set": update_fields})

    updated_item = await db.news.find_one({"_id": oid})
    return success_response(data=news_doc_to_brief(updated_item))


@router.post("/mark-all-read", response_model=ResponseBase[dict])
async def mark_all_read(
    source_id: Optional[str] = Query(
        None, description="Only mark items from this source"
    ),
    current_user: UserInDB = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Mark all (or filtered) news items as read."""
    query = {"user_id": current_user.id, "is_read": False}

    if source_id:
        query["source_id"] = source_id

    now = datetime.utcnow()
    result = await db.news.update_many(
        query,
        {"$set": {"is_read": True, "read_at": now, "updated_at": now}},
    )

    return success_response(
        data={"marked_count": result.modified_count},
        message=f"Marked {result.modified_count} items as read",
    )


@router.delete("/{news_id}", response_model=ResponseBase[None])
async def delete_news_item(
    news_id: str,
    current_user: UserInDB = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Delete a news item."""
    try:
        oid = ObjectId(news_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid news ID format"
        )

    result = await db.news.delete_one({"_id": oid, "user_id": current_user.id})

    if result.deleted_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="News item not found"
        )

    return success_response(data=None, message="News item deleted")
