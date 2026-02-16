"""
AI Assistant Schema

Request and response models for the AI assistant endpoints.
"""

from typing import List, Literal, Optional

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


class SearchResultItem(BaseModel):
    """A single search result item."""

    title: str = ""
    url: str = ""
    description: str = ""
    source_name: str = ""
    score: float = 0.0
    origin: str = Field(default="internal", description="internal or external")
    news_id: Optional[str] = None


class AugmentedSearchResponseData(BaseModel):
    """Augmented search response data."""

    query: str
    summary: str = ""
    results: List[SearchResultItem] = Field(default_factory=list)
    internal_count: int = 0
    external_count: int = 0
