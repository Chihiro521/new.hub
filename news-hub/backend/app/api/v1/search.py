"""
Search API Routes

Provides endpoints for searching news items using keyword, semantic, and hybrid search.
"""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.core.deps import get_current_user
from app.db.es import es_client
from app.schemas.response import ResponseBase, success_response
from app.schemas.user import UserInDB
from app.services.search import SearchService, embedding_service

router = APIRouter(prefix="/search", tags=["Search"])


class SearchResultItem(BaseModel):
    """Search result item for API response."""

    id: str
    title: str
    url: str
    description: Optional[str] = None
    image_url: Optional[str] = None
    source_name: str
    source_id: str
    published_at: Optional[datetime] = None
    crawled_at: datetime
    tags: List[str] = []
    is_read: bool = False
    is_starred: bool = False
    score: float = 0.0
    highlights: dict = Field(default_factory=dict)


class SearchResponseData(BaseModel):
    """Search response data."""

    query: str
    total: int
    results: List[SearchResultItem]
    took_ms: int
    search_type: str


class SuggestResponseData(BaseModel):
    """Autocomplete suggestions response."""

    prefix: str
    suggestions: List[str]


class SearchStatusData(BaseModel):
    """Search system status."""

    elasticsearch_available: bool
    embedding_available: bool
    embedding_model: Optional[str] = None


@router.get("", response_model=ResponseBase[SearchResponseData])
async def search_news(
    q: str = Query(..., min_length=1, max_length=200, description="Search query"),
    search_type: str = Query(
        "hybrid", description="Search type: keyword, semantic, or hybrid"
    ),
    source_ids: Optional[str] = Query(
        None, description="Comma-separated source IDs to filter"
    ),
    tags: Optional[str] = Query(None, description="Comma-separated tags to filter"),
    is_starred: Optional[bool] = Query(None, description="Filter starred items"),
    start_date: Optional[datetime] = Query(None, description="Filter from date"),
    end_date: Optional[datetime] = Query(None, description="Filter to date"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Results per page"),
    current_user: UserInDB = Depends(get_current_user),
):
    """
    Search news items.

    Supports three search modes:
    - **keyword**: Traditional BM25 full-text search with IK Chinese analyzer
    - **semantic**: Vector similarity search using embeddings
    - **hybrid**: Combined keyword + semantic search (recommended)

    Returns results with relevance scores and highlighted matches.
    """
    # Validate search type
    if search_type not in ["keyword", "semantic", "hybrid"]:
        search_type = "hybrid"

    # Check if ES is available
    if es_client.client is None:
        return success_response(
            data=SearchResponseData(
                query=q,
                total=0,
                results=[],
                took_ms=0,
                search_type=search_type,
            ),
            message="Search unavailable: Elasticsearch not connected",
        )

    # Parse comma-separated filters
    source_id_list = source_ids.split(",") if source_ids else None
    tag_list = tags.split(",") if tags else None

    # Execute search
    service = SearchService(es_client.client)
    response = await service.search(
        user_id=current_user.id,
        query=q,
        search_type=search_type,
        source_ids=source_id_list,
        tags=tag_list,
        is_starred=is_starred,
        start_date=start_date,
        end_date=end_date,
        page=page,
        page_size=page_size,
    )

    # Convert to API response
    results = [
        SearchResultItem(
            id=r.id,
            title=r.title,
            url=r.url,
            description=r.description,
            image_url=r.image_url,
            source_name=r.source_name,
            source_id=r.source_id,
            published_at=r.published_at,
            crawled_at=r.crawled_at,
            tags=r.tags,
            is_read=r.is_read,
            is_starred=r.is_starred,
            score=r.score,
            highlights=r.highlights,
        )
        for r in response.results
    ]

    return success_response(
        data=SearchResponseData(
            query=response.query,
            total=response.total,
            results=results,
            took_ms=response.took_ms,
            search_type=response.search_type,
        )
    )


@router.get("/suggest", response_model=ResponseBase[SuggestResponseData])
async def suggest_completions(
    q: str = Query(..., min_length=1, max_length=100, description="Search prefix"),
    size: int = Query(5, ge=1, le=10, description="Max suggestions"),
    current_user: UserInDB = Depends(get_current_user),
):
    """
    Get autocomplete suggestions based on news titles.

    Returns up to `size` title suggestions matching the prefix.
    """
    if es_client.client is None:
        return success_response(
            data=SuggestResponseData(prefix=q, suggestions=[]),
            message="Suggestions unavailable: Elasticsearch not connected",
        )

    service = SearchService(es_client.client)
    suggestions = await service.suggest(
        user_id=current_user.id,
        prefix=q,
        size=size,
    )

    return success_response(data=SuggestResponseData(prefix=q, suggestions=suggestions))


@router.get("/status", response_model=ResponseBase[SearchStatusData])
async def get_search_status(
    current_user: UserInDB = Depends(get_current_user),
):
    """
    Get search system status.

    Returns availability of Elasticsearch and embedding model.
    """
    from app.core.config import settings

    es_available = es_client.client is not None
    embedding_available = embedding_service.is_available

    return success_response(
        data=SearchStatusData(
            elasticsearch_available=es_available,
            embedding_available=embedding_available,
            embedding_model=settings.embedding_model_name
            if embedding_available
            else None,
        )
    )


@router.post("/reindex", response_model=ResponseBase[dict])
async def reindex_user_news(
    current_user: UserInDB = Depends(get_current_user),
):
    """
    Reindex all news items for the current user.

    This is useful after enabling semantic search or fixing indexing issues.
    """
    from app.db.mongo import mongodb
    from app.services.search.indexer import ESIndexer

    if es_client.client is None:
        return success_response(
            data={"indexed": 0},
            message="Elasticsearch not connected",
        )

    # Ensure index exists
    await es_client.ensure_user_index(current_user.id)

    # Get all news items from MongoDB
    cursor = mongodb.db.news.find({"user_id": current_user.id})
    docs = await cursor.to_list(length=10000)

    if not docs:
        return success_response(
            data={"indexed": 0},
            message="No news items to index",
        )

    # Batch index
    indexer = ESIndexer(es_client.client)
    indexed = await indexer.index_batch(
        user_id=current_user.id,
        items=docs,
        generate_embeddings=True,
    )

    return success_response(
        data={"indexed": indexed, "total": len(docs)},
        message=f"Indexed {indexed}/{len(docs)} news items",
    )
