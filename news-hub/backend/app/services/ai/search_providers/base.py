"""Shared models and interfaces for external search providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class ExternalSearchQuery:
    """Normalized query options for provider-agnostic external search."""

    query: str
    max_results: int = 10
    time_range: Optional[str] = None
    language: Optional[str] = None
    safe_search: int = 1
    engines: Optional[List[str]] = None


@dataclass
class ExternalSearchResult:
    """Normalized external search result item."""

    title: str
    url: str
    description: str = ""
    content: str = ""
    score: float = 0.0
    source_name: str = "Web"
    published_at: Optional[datetime] = None
    provider: str = ""
    engine: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_news_item(self) -> Dict[str, Any]:
        """Convert to ingestion-friendly dictionary."""
        return {
            "title": self.title,
            "url": self.url,
            "description": self.description,
            "content": self.content,
            "published_at": self.published_at,
            "score": self.score,
            "source_name": self.source_name,
            "origin": "external",
            "provider": self.provider,
            "engine": self.engine,
            "metadata": self.metadata,
        }


class ExternalSearchProvider(ABC):
    """Interface for concrete external search providers."""

    name: str

    @property
    @abstractmethod
    def available(self) -> bool:
        """Whether the provider is available in current runtime."""

    @abstractmethod
    async def search(self, request: ExternalSearchQuery) -> List[ExternalSearchResult]:
        """Run an external search request."""

    async def options(self) -> Dict[str, Any]:
        """Provider-specific options exposed to frontend control panels."""
        return {}

    async def healthcheck(self) -> Dict[str, Any]:
        """Provider health status for monitoring/UX diagnostics."""
        return {
            "provider": self.name,
            "available": self.available,
            "healthy": self.available,
            "latency_ms": 0,
            "message": "ok" if self.available else "not configured",
        }
