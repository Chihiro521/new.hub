"""
News Item Schema Definitions

Pydantic models for news article data.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, HttpUrl


class NewsMetadata(BaseModel):
    """Additional metadata for a news item."""

    author: Optional[str] = None
    hot_score: float = Field(default=0.0, description="Popularity/heat score")
    view_count: int = Field(default=0)
    like_count: int = Field(default=0)
    comment_count: int = Field(default=0)
    word_count: Optional[int] = None
    read_time_minutes: Optional[int] = None
    language: str = Field(default="zh", description="Content language code")
    extra: Dict[str, Any] = Field(
        default_factory=dict, description="Source-specific data"
    )


class NewsItemBase(BaseModel):
    """Base news item fields."""

    title: str = Field(..., min_length=1, max_length=500, description="Article title")
    url: HttpUrl = Field(..., description="Original article URL")
    description: Optional[str] = Field(
        None, max_length=2000, description="Article summary"
    )
    content: Optional[str] = Field(
        None, description="Full article content (HTML or plain text)"
    )
    image_url: Optional[HttpUrl] = Field(None, description="Cover image URL")
    published_at: Optional[datetime] = Field(None, description="Original publish time")


class NewsItemCreate(NewsItemBase):
    """Schema for creating a news item (internal use)."""

    source_id: str = Field(..., description="Associated source ID")
    source_name: str = Field(..., description="Source display name")
    source_type: str = Field(..., description="Source type (rss/api/html)")
    tags: List[str] = Field(default_factory=list, description="Auto-generated tags")
    metadata: NewsMetadata = Field(default_factory=NewsMetadata)


class NewsItemInDB(NewsItemBase):
    """News item as stored in database."""

    id: str = Field(..., alias="_id", description="News item ID")
    user_id: str = Field(..., description="Owner user ID")
    source_id: str
    source_name: str
    source_type: str
    tags: List[str] = Field(default_factory=list)
    metadata: NewsMetadata = Field(default_factory=NewsMetadata)

    # Reading state
    is_read: bool = Field(default=False)
    is_starred: bool = Field(default=False)
    read_at: Optional[datetime] = None

    # Vector embedding
    embedding: Optional[List[float]] = Field(None, description="Text embedding vector")

    # Timestamps
    crawled_at: datetime = Field(default_factory=datetime.utcnow)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True


class NewsItemResponse(NewsItemBase):
    """News item returned in API responses."""

    id: str
    source_id: str
    source_name: str
    source_type: str
    tags: List[str]
    metadata: NewsMetadata
    is_read: bool
    is_starred: bool
    crawled_at: datetime

    # Computed fields
    proxied_image_url: Optional[str] = Field(
        None, description="Image URL proxied through our server"
    )

    class Config:
        from_attributes = True


class NewsItemBrief(BaseModel):
    """Minimal news item for list views."""

    id: str
    title: str
    url: HttpUrl
    description: Optional[str] = None
    image_url: Optional[HttpUrl] = None
    source_name: str
    published_at: Optional[datetime]
    tags: List[str] = Field(default_factory=list)
    is_read: bool = False
    is_starred: bool = False


class NewsStateUpdate(BaseModel):
    """Schema for updating news item read/star state."""

    is_read: Optional[bool] = None
    is_starred: Optional[bool] = None


class NewsSearchQuery(BaseModel):
    """Search query parameters."""

    q: str = Field(..., min_length=1, description="Search query text")
    source_ids: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    source_types: Optional[List[str]] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    is_starred: Optional[bool] = None
    use_vector: bool = Field(default=True, description="Enable semantic search")
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    sort_by: str = Field(
        default="relevance", description="Sort by: relevance, date, popularity"
    )
