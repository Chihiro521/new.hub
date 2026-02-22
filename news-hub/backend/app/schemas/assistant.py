"""
AI Assistant Schema

Request and response models for the AI assistant endpoints.
"""

from datetime import datetime
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    """A single chat message."""

    role: Literal["user", "assistant", "system"] = Field(
        ..., description="Message role"
    )
    content: str = Field(..., description="Message content")


class ChatRequest(BaseModel):
    """Chat request with conversation history."""

    messages: List[ChatMessage] = Field(..., description="Conversation messages")
    stream: bool = Field(default=True, description="Enable streaming response")
    system_prompt: Optional[str] = Field(
        default=None,
        max_length=2000,
        description="自定义系统提示词，覆盖默认助手行为",
    )


class SummarizeRequest(BaseModel):
    """Request to summarize a news article."""

    news_id: str = Field(..., description="News article ID to summarize")


class ClassifyRequest(BaseModel):
    """Request to classify a news article."""

    news_id: str = Field(..., description="News article ID to classify")


class DiscoverSourcesRequest(BaseModel):
    """Request to discover new sources based on a topic."""

    topic: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Topic to find sources for",
    )


class ChatResponseData(BaseModel):
    """Non-streaming chat response data."""

    reply: str = Field(..., description="Assistant reply")


class SummarizeResponseData(BaseModel):
    """Summary response data."""

    news_id: str
    summary: str
    method: str = Field(default="ai", description="ai or extractive")


class ClassifyResponseData(BaseModel):
    """Classification response data."""

    news_id: str
    suggested_tags: List[str]
    method: str = Field(default="ai", description="ai or rule_based")


class SourceSuggestion(BaseModel):
    """A suggested news source."""

    name: str
    url: str
    type: str = Field(default="rss", description="Source type: rss, api, html")
    description: str = ""


class DiscoverSourcesResponseData(BaseModel):
    """Source discovery response data."""

    topic: str
    suggestions: List[SourceSuggestion]


class AugmentedSearchRequest(BaseModel):
    """Request for AI-augmented search across internal + external sources."""

    query: str = Field(..., min_length=1, max_length=500, description="Search query")
    include_external: bool = Field(
        default=True, description="Include external web search results"
    )
    persist_external: bool = Field(
        default=False, description="Persist external results to user's library"
    )
    persist_mode: Literal["none", "snippet", "enriched"] = Field(
        default="none", description="How external results should be persisted"
    )
    external_provider: Literal["auto", "searxng", "tavily"] = Field(
        default="auto", description="Preferred external search provider"
    )
    max_external_results: int = Field(
        default=10, ge=1, le=50, description="Max number of external results"
    )
    time_range: Optional[str] = Field(
        default=None, description="Optional time range: day, week, month, year"
    )
    language: Optional[str] = Field(
        default=None, description="Language code, e.g. zh-CN, en-US"
    )
    engines: Optional[List[str]] = Field(
        default=None, description="Optional SearXNG engines filter"
    )


class SearchResultItem(BaseModel):
    """A single search result item."""

    title: str = ""
    url: str = ""
    description: str = ""
    source_name: str = ""
    score: float = 0.0
    origin: str = Field(default="internal", description="internal or external")
    news_id: Optional[str] = None
    provider: Optional[str] = None
    engine: Optional[str] = None


class AugmentedSearchResponseData(BaseModel):
    """Augmented search response data."""

    query: str
    summary: str = ""
    results: List[SearchResultItem] = Field(default_factory=list)
    internal_count: int = 0
    external_count: int = 0
    provider_used: Optional[str] = None
    fallback_used: bool = False
    search_session_id: Optional[str] = None


class ExternalSearchProviderOption(BaseModel):
    """Provider capabilities and availability."""

    name: str
    available: bool
    supports: Dict[str, bool] = Field(default_factory=dict)
    engines: List[str] = Field(default_factory=list)
    languages: List[str] = Field(default_factory=list)
    time_ranges: List[str] = Field(default_factory=list)


class ExternalSearchOptionsResponseData(BaseModel):
    """External search provider options returned to frontend."""

    default_provider: str
    fallback_provider: str
    providers: List[ExternalSearchProviderOption] = Field(default_factory=list)


class SearchIngestRequest(BaseModel):
    """Request to ingest selected search results into user library."""

    session_id: str = Field(..., min_length=1, max_length=128)
    selected_urls: List[str] = Field(default_factory=list)
    persist_mode: Literal["snippet", "enriched"] = Field(default="enriched")


class SearchIngestResponseData(BaseModel):
    """Accepted ingest job response."""

    job_id: str
    status: str
    queued_count: int
    persist_mode: str


class IngestJobStatusResponseData(BaseModel):
    """Status payload for an ingest job."""

    job_id: str
    status: str
    session_id: str
    persist_mode: str
    total_items: int = 0
    processed_items: int = 0
    stored_items: int = 0
    failed_items: int = 0
    retry_count: int = 0
    average_quality_score: float = 0.0
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class ExternalSearchProviderStatusItem(BaseModel):
    """Health item for one external search provider."""

    provider: str
    available: bool
    healthy: bool
    latency_ms: int = 0
    message: str = ""


class ExternalSearchStatusResponseData(BaseModel):
    """Aggregated external search status response."""

    default_provider: str
    fallback_provider: str
    healthy_provider_count: int = 0
    providers: List[ExternalSearchProviderStatusItem] = Field(default_factory=list)


# --- External Search (pure SearXNG) ---


class ExternalSearchRequest(BaseModel):
    """Request for pure external search (SearXNG/Tavily only, no RRF fusion)."""

    query: str = Field(..., min_length=1, max_length=500, description="Search query")
    provider: Literal["auto", "searxng", "tavily"] = Field(
        default="auto", description="Search provider"
    )
    max_results: int = Field(default=10, ge=1, le=50, description="Max results")
    time_range: Optional[str] = Field(
        default=None, description="Time range: day, week, month, year"
    )
    language: Optional[str] = Field(default=None, description="Language code")


class ExternalSearchResultItem(BaseModel):
    """A single external search result."""

    title: str = ""
    url: str = ""
    description: str = ""
    source_name: str = ""
    score: float = 0.0
    provider: Optional[str] = None
    engine: Optional[str] = None
    published_at: Optional[str] = None


class ExternalSearchResponseData(BaseModel):
    """External search response."""

    query: str
    results: List[ExternalSearchResultItem] = Field(default_factory=list)
    total: int = 0
    provider_used: Optional[str] = None


# --- Ingest One ---


class IngestOneRequest(BaseModel):
    """Request to crawl and ingest a single external URL."""

    url: str = Field(..., min_length=1, description="URL to crawl and ingest")
    title: str = Field(default="", description="Title from search result")
    description: str = Field(default="", description="Snippet from search result")
    provider: str = Field(default="searxng", description="Source provider name")


class IngestOneResponseData(BaseModel):
    """Response after ingesting a single URL."""

    success: bool
    news_id: Optional[str] = None
    quality_score: float = 0.0
    message: str = ""
    # Extracted data for visualization
    extracted_title: str = ""
    extracted_description: str = ""
    extracted_content_preview: str = ""
    extracted_author: Optional[str] = None
    extracted_image_url: Optional[str] = None
    extracted_published_at: Optional[str] = None
    content_length: int = 0
    crawl_method: str = ""


# --- Batch Ingest All ---


class BatchIngestItem(BaseModel):
    """A single item for batch ingestion."""

    url: str = Field(..., min_length=1, description="URL to crawl")
    title: str = Field(default="", description="Title from search result")
    description: str = Field(default="", description="Snippet from search result")


class BatchIngestAllRequest(BaseModel):
    """Request to batch-crawl and ingest all external search results."""

    items: List[BatchIngestItem] = Field(
        ..., min_length=1, max_length=50, description="Items to ingest"
    )
    provider: str = Field(default="searxng", description="Source provider name")


class BatchIngestItemResult(BaseModel):
    """Result for a single item in batch ingestion."""

    url: str
    success: bool
    news_id: Optional[str] = None
    quality_score: float = 0.0
    title: str = ""
    content_length: int = 0
    error: Optional[str] = None


class BatchIngestAllResponseData(BaseModel):
    """Response after batch ingesting multiple URLs."""

    total: int = 0
    succeeded: int = 0
    failed: int = 0
    average_quality_score: float = 0.0
    results: List[BatchIngestItemResult] = Field(default_factory=list)


# === Deep Research ===

class DeepResearchRequest(BaseModel):
    """Request for deep multi-step research."""

    query: str = Field(..., min_length=1, max_length=500, description="研究问题")
    stream: bool = Field(default=True, description="Enable streaming response")
    system_prompt: Optional[str] = Field(
        default=None,
        max_length=2000,
        description="自定义系统提示词，覆盖默认研究助手行为",
    )


class ResearchSource(BaseModel):
    """A cited source in the research report."""

    title: str = ""
    url: str = ""


class DeepResearchResponseData(BaseModel):
    """Structured research report response."""

    query: str
    report: str = ""
    sources: List[ResearchSource] = Field(default_factory=list)
    sub_questions: List[str] = Field(default_factory=list)
