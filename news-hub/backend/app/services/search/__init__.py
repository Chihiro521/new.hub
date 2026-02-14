"""
Search Services Package

Provides text embedding and search functionality for news items.
"""

from app.services.search.embedding import EmbeddingService, embedding_service
from app.services.search.search_service import (
    SearchService,
    SearchResult,
    SearchResponse,
    get_search_service,
)


__all__ = [
    "EmbeddingService",
    "embedding_service",
    "SearchService",
    "SearchResult",
    "SearchResponse",
    "get_search_service",
]
