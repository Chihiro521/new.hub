"""
Source Schema Definitions

Pydantic models for news source management API contracts.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, HttpUrl


class SourceType(str, Enum):
    """Supported source types for data collection."""

    RSS = "rss"
    API = "api"
    HTML = "html"  # Web scraping via Scrapy
    VIRTUAL = "virtual"  # System-managed source for external search results


class SourceStatus(str, Enum):
    """Source operational status."""

    ACTIVE = "active"
    PAUSED = "paused"
    ERROR = "error"
    PENDING = "pending"


class ParserConfigAPI(BaseModel):
    """Parser configuration for API-type sources."""

    list_path: str = Field(
        ..., description="JMESPath to extract list from JSON response"
    )
    fields: Dict[str, str] = Field(
        default_factory=dict,
        description="Field mapping: {target_field: jmespath_expression}",
    )
    pagination: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Pagination config: {type: 'offset'|'cursor', param: str, step: int}",
    )
    headers: Optional[Dict[str, str]] = Field(
        default=None, description="Custom HTTP headers"
    )


class ParserConfigHTML(BaseModel):
    """Parser configuration for HTML/Scrapy sources."""

    list_selector: str = Field(..., description="CSS selector for list container items")
    link_selector: str = Field(
        ..., description="CSS selector for detail page link within each item"
    )
    fields: Optional[Dict[str, str]] = Field(
        default=None, description="Field mapping: {target_field: css_selector}"
    )
    use_playwright: bool = Field(
        default=False, description="Use Playwright for JavaScript rendering"
    )
    wait_for: Optional[str] = Field(
        default=None, description="CSS selector to wait for before extraction"
    )


class ParserConfig(BaseModel):
    """Unified parser configuration container."""

    mode: SourceType = Field(
        ..., description="Source type determines which config is used"
    )
    api: Optional[ParserConfigAPI] = None
    html: Optional[ParserConfigHTML] = None
    # RSS doesn't need extra config - feedparser handles it


class SourceBase(BaseModel):
    """Base source fields shared across schemas."""

    name: str = Field(
        ..., min_length=1, max_length=100, description="Display name for the source"
    )
    url: HttpUrl = Field(
        ..., description="Source URL (feed URL, API endpoint, or page URL)"
    )
    source_type: SourceType = Field(..., description="Collection method type")
    description: Optional[str] = Field(None, max_length=500)
    logo_url: Optional[HttpUrl] = None
    homepage: Optional[HttpUrl] = None
    tags: List[str] = Field(default_factory=list, description="Category tags")


class SourceCreate(SourceBase):
    """Schema for creating a new source."""

    parser_config: Optional[ParserConfig] = Field(
        default=None, description="Parser configuration (auto-detected if not provided)"
    )
    refresh_interval_minutes: int = Field(
        default=30, ge=5, le=1440, description="Auto-refresh interval in minutes"
    )


class SourceUpdate(BaseModel):
    """Schema for updating source settings."""

    name: Optional[str] = None
    description: Optional[str] = None
    logo_url: Optional[HttpUrl] = None
    parser_config: Optional[ParserConfig] = None
    refresh_interval_minutes: Optional[int] = Field(default=None, ge=5, le=1440)
    status: Optional[SourceStatus] = None
    tags: Optional[List[str]] = None


class SourceInDB(SourceBase):
    """Source model as stored in database."""

    id: str = Field(..., alias="_id", description="Source ID")
    user_id: str = Field(..., description="Owner user ID")
    parser_config: Optional[ParserConfig] = None
    status: SourceStatus = Field(default=SourceStatus.PENDING)
    refresh_interval_minutes: int = 30
    last_fetched_at: Optional[datetime] = None
    last_error: Optional[str] = None
    fetch_count: int = Field(default=0)
    item_count: int = Field(default=0)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True


class SourceResponse(SourceBase):
    """Source data returned in API responses."""

    id: str
    user_id: str
    status: SourceStatus
    parser_config: Optional[ParserConfig] = None
    refresh_interval_minutes: int
    last_fetched_at: Optional[datetime]
    last_error: Optional[str]
    fetch_count: int
    item_count: int
    created_at: datetime

    class Config:
        from_attributes = True


class SourceDetectRequest(BaseModel):
    """Request for auto-detecting source configuration."""

    url: HttpUrl = Field(..., description="URL to analyze")


class SourceDetectResponse(BaseModel):
    """Response from source auto-detection."""

    detected_type: SourceType
    suggested_name: Optional[str] = None
    suggested_config: Optional[ParserConfig] = None
    preview_items: List[Dict[str, Any]] = Field(
        default_factory=list, description="Sample items from the source"
    )
    confidence: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Detection confidence score"
    )
