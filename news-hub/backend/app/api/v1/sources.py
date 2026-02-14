"""
Source Management API Routes

Provides endpoints for creating, reading, updating, and deleting news sources.
"""

from datetime import datetime
from typing import List, Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.deps import get_current_user
from app.db.mongo import get_db
from app.schemas.response import ResponseBase, success_response
from app.schemas.source import (
    SourceCreate,
    SourceDetectRequest,
    SourceDetectResponse,
    SourceResponse,
    SourceStatus,
    SourceUpdate,
)
from app.schemas.user import UserInDB
from app.services.source.detector import SourceDetector

router = APIRouter(prefix="/sources", tags=["Sources"])


def source_doc_to_response(doc: dict) -> SourceResponse:
    """Convert MongoDB document to SourceResponse."""
    return SourceResponse(
        id=str(doc["_id"]),
        user_id=str(doc["user_id"]),
        name=doc["name"],
        url=doc["url"],
        source_type=doc["source_type"],
        description=doc.get("description"),
        logo_url=doc.get("logo_url"),
        homepage=doc.get("homepage"),
        tags=doc.get("tags", []),
        status=doc.get("status", SourceStatus.PENDING),
        parser_config=doc.get("parser_config"),
        refresh_interval_minutes=doc.get("refresh_interval_minutes", 30),
        last_fetched_at=doc.get("last_fetched_at"),
        last_error=doc.get("last_error"),
        fetch_count=doc.get("fetch_count", 0),
        item_count=doc.get("item_count", 0),
        created_at=doc.get("created_at", datetime.utcnow()),
    )


@router.get("", response_model=ResponseBase[List[SourceResponse]])
async def list_sources(
    status_filter: Optional[SourceStatus] = Query(None, alias="status"),
    tag: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: UserInDB = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    List all sources for the current user.

    - **status**: Filter by source status
    - **tag**: Filter by tag
    - **skip**: Pagination offset
    - **limit**: Max items to return (1-100)
    """
    query = {"user_id": current_user.id}

    if status_filter:
        query["status"] = status_filter.value

    if tag:
        query["tags"] = tag

    cursor = db.sources.find(query).skip(skip).limit(limit).sort("created_at", -1)
    sources = await cursor.to_list(length=limit)

    return success_response(data=[source_doc_to_response(doc) for doc in sources])


@router.post(
    "", response_model=ResponseBase[SourceResponse], status_code=status.HTTP_201_CREATED
)
async def create_source(
    source_data: SourceCreate,
    current_user: UserInDB = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Create a new news source.

    - **name**: Display name
    - **url**: Feed URL, API endpoint, or page URL
    - **source_type**: Collection method (rss, api, html)
    - **parser_config**: Optional parser configuration
    """
    # Check if source with same URL already exists for this user
    existing = await db.sources.find_one(
        {"user_id": current_user.id, "url": str(source_data.url)}
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A source with this URL already exists",
        )

    now = datetime.utcnow()
    source_doc = {
        "user_id": current_user.id,
        "name": source_data.name,
        "url": str(source_data.url),
        "source_type": source_data.source_type.value,
        "description": source_data.description,
        "logo_url": str(source_data.logo_url) if source_data.logo_url else None,
        "homepage": str(source_data.homepage) if source_data.homepage else None,
        "tags": source_data.tags,
        "parser_config": source_data.parser_config.model_dump()
        if source_data.parser_config
        else None,
        "refresh_interval_minutes": source_data.refresh_interval_minutes,
        "status": SourceStatus.PENDING.value,
        "last_fetched_at": None,
        "last_error": None,
        "fetch_count": 0,
        "item_count": 0,
        "created_at": now,
        "updated_at": now,
    }

    result = await db.sources.insert_one(source_doc)
    source_doc["_id"] = result.inserted_id

    return success_response(
        data=source_doc_to_response(source_doc), message="Source created successfully"
    )


@router.get("/{source_id}", response_model=ResponseBase[SourceResponse])
async def get_source(
    source_id: str,
    current_user: UserInDB = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Get a specific source by ID."""
    try:
        oid = ObjectId(source_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid source ID format"
        )

    source = await db.sources.find_one({"_id": oid, "user_id": current_user.id})

    if not source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Source not found"
        )

    return success_response(data=source_doc_to_response(source))


@router.patch("/{source_id}", response_model=ResponseBase[SourceResponse])
async def update_source(
    source_id: str,
    update_data: SourceUpdate,
    current_user: UserInDB = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Update a source's settings."""
    try:
        oid = ObjectId(source_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid source ID format"
        )

    # Check source exists and belongs to user
    source = await db.sources.find_one({"_id": oid, "user_id": current_user.id})

    if not source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Source not found"
        )

    # Build update document
    update_fields = {}
    update_dict = update_data.model_dump(exclude_unset=True)

    for key, value in update_dict.items():
        if value is not None:
            if key == "parser_config":
                update_fields[key] = value
            elif key == "status":
                update_fields[key] = value.value if hasattr(value, "value") else value
            elif key == "logo_url":
                update_fields[key] = str(value) if value else None
            else:
                update_fields[key] = value

    if not update_fields:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="No fields to update"
        )

    update_fields["updated_at"] = datetime.utcnow()

    await db.sources.update_one({"_id": oid}, {"$set": update_fields})

    updated_source = await db.sources.find_one({"_id": oid})
    if not updated_source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Source not found after update",
        )
    return success_response(
        data=source_doc_to_response(updated_source), message="Source updated"
    )


@router.delete("/{source_id}", response_model=ResponseBase[None])
async def delete_source(
    source_id: str,
    current_user: UserInDB = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Delete a source and all its collected news items."""
    try:
        oid = ObjectId(source_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid source ID format"
        )

    # Check source exists and belongs to user
    result = await db.sources.delete_one({"_id": oid, "user_id": current_user.id})

    if result.deleted_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Source not found"
        )

    # Also delete all news items from this source
    await db.news.delete_many({"source_id": source_id, "user_id": current_user.id})

    return success_response(data=None, message="Source deleted")


@router.post("/detect", response_model=ResponseBase[SourceDetectResponse])
async def detect_source(
    request: SourceDetectRequest,
    current_user: UserInDB = Depends(get_current_user),
):
    """
    Auto-detect source type and configuration from a URL.

    Analyzes the URL to determine if it's an RSS feed, API endpoint,
    or HTML page, and suggests appropriate parser configuration.
    """
    detector = SourceDetector()
    result = await detector.detect(str(request.url))

    return success_response(data=result)


@router.post("/{source_id}/refresh", response_model=ResponseBase[dict])
async def trigger_refresh(
    source_id: str,
    current_user: UserInDB = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Manually trigger a refresh for a source and collect news."""
    from app.services.pipeline import CollectionService

    try:
        oid = ObjectId(source_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid source ID format"
        )

    source = await db.sources.find_one({"_id": oid, "user_id": current_user.id})

    if not source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Source not found"
        )

    # Run collection
    service = CollectionService(db)
    result = await service.collect_source(source_id)

    if result["success"]:
        return success_response(
            data={
                "items_fetched": result["items_fetched"],
                "items_stored": result["items_stored"],
                "items_duplicated": result["items_duplicated"],
                "duration_seconds": result["duration_seconds"],
            },
            message=f"Collected {result['items_stored']} new items",
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result.get("error", "Collection failed"),
        )
