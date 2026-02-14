"""
Search Service

Provides keyword search, semantic search, and hybrid search over news items.
Uses Elasticsearch for full-text and vector search.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from elasticsearch import AsyncElasticsearch
from loguru import logger

from app.core.config import settings
from app.db.es import es_client
from app.services.search.embedding import embedding_service


@dataclass
class SearchResult:
    """A single search result item."""

    id: str
    title: str
    url: str
    description: Optional[str]
    image_url: Optional[str]
    source_name: str
    source_id: str
    published_at: Optional[datetime]
    crawled_at: datetime
    tags: List[str]
    is_read: bool
    is_starred: bool
    score: float
    highlights: Dict[str, List[str]]


@dataclass
class SearchResponse:
    """Search response containing results and metadata."""

    query: str
    total: int
    results: List[SearchResult]
    took_ms: int
    search_type: str  # "keyword", "semantic", "hybrid"


class SearchService:
    """
    Search service for news items.

    Supports:
    - Keyword search (BM25 with IK analyzer)
    - Semantic search (dense vector similarity)
    - Hybrid search (combined keyword + semantic)
    - Autocomplete suggestions
    """

    def __init__(self, es: AsyncElasticsearch):
        """
        Initialize search service.

        Args:
            es: Elasticsearch async client
        """
        self.es = es

    def _get_index_name(self, user_id: str) -> str:
        """Get ES index name for user."""
        return es_client.index_name(f"news_{user_id}")

    async def search(
        self,
        user_id: str,
        query: str,
        search_type: str = "hybrid",
        source_ids: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        is_starred: Optional[bool] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> SearchResponse:
        """
        Search news items.

        Args:
            user_id: User ID
            query: Search query text
            search_type: "keyword", "semantic", or "hybrid"
            source_ids: Filter by source IDs
            tags: Filter by tags
            is_starred: Filter by starred status
            start_date: Filter from date
            end_date: Filter to date
            page: Page number (1-based)
            page_size: Results per page

        Returns:
            SearchResponse with results
        """
        index_name = self._get_index_name(user_id)

        # Build filter clauses
        filters = self._build_filters(
            source_ids=source_ids,
            tags=tags,
            is_starred=is_starred,
            start_date=start_date,
            end_date=end_date,
        )

        # Execute appropriate search type
        if search_type == "semantic":
            return await self._semantic_search(
                index_name, query, filters, page, page_size
            )
        elif search_type == "keyword":
            return await self._keyword_search(
                index_name, query, filters, page, page_size
            )
        else:  # hybrid
            return await self._hybrid_search(
                index_name, query, filters, page, page_size
            )

    async def _keyword_search(
        self,
        index_name: str,
        query: str,
        filters: List[Dict[str, Any]],
        page: int,
        page_size: int,
    ) -> SearchResponse:
        """Execute keyword (BM25) search."""
        body = {
            "query": {
                "bool": {
                    "must": [
                        {
                            "multi_match": {
                                "query": query,
                                "fields": [
                                    "title^3",
                                    "description^2",
                                    "content",
                                    "tags^2",
                                ],
                                "type": "best_fields",
                                "fuzziness": "AUTO",
                            }
                        }
                    ],
                    "filter": filters,
                }
            },
            "highlight": {
                "fields": {
                    "title": {"number_of_fragments": 0},
                    "description": {"number_of_fragments": 2, "fragment_size": 150},
                    "content": {"number_of_fragments": 2, "fragment_size": 150},
                },
                "pre_tags": ["<mark>"],
                "post_tags": ["</mark>"],
            },
            "from": (page - 1) * page_size,
            "size": page_size,
            "_source": {"excludes": ["embedding", "content"]},
        }

        try:
            response = await self.es.search(index=index_name, body=body)
            return self._parse_response(response, query, "keyword")
        except Exception as e:
            logger.error(f"Keyword search error: {e}")
            return SearchResponse(
                query=query,
                total=0,
                results=[],
                took_ms=0,
                search_type="keyword",
            )

    async def _semantic_search(
        self,
        index_name: str,
        query: str,
        filters: List[Dict[str, Any]],
        page: int,
        page_size: int,
    ) -> SearchResponse:
        """Execute semantic (vector) search."""
        # Generate query embedding
        query_vector = embedding_service.encode_for_search(query)

        if query_vector is None:
            logger.warning("Embedding unavailable, falling back to keyword search")
            return await self._keyword_search(
                index_name, query, filters, page, page_size
            )

        body = {
            "query": {
                "bool": {
                    "must": [
                        {
                            "script_score": {
                                "query": {"match_all": {}},
                                "script": {
                                    "source": "cosineSimilarity(params.query_vector, 'embedding') + 1.0",
                                    "params": {"query_vector": query_vector},
                                },
                            }
                        }
                    ],
                    "filter": filters + [{"exists": {"field": "embedding"}}],
                }
            },
            "from": (page - 1) * page_size,
            "size": page_size,
            "_source": {"excludes": ["embedding", "content"]},
        }

        try:
            response = await self.es.search(index=index_name, body=body)
            return self._parse_response(response, query, "semantic")
        except Exception as e:
            logger.error(f"Semantic search error: {e}")
            return SearchResponse(
                query=query,
                total=0,
                results=[],
                took_ms=0,
                search_type="semantic",
            )

    async def _hybrid_search(
        self,
        index_name: str,
        query: str,
        filters: List[Dict[str, Any]],
        page: int,
        page_size: int,
    ) -> SearchResponse:
        """
        Execute hybrid search combining keyword and semantic.

        Uses ES 8.x knn combined with text query.
        """
        query_vector = embedding_service.encode_for_search(query)

        # If no embedding available, fall back to keyword
        if query_vector is None:
            return await self._keyword_search(
                index_name, query, filters, page, page_size
            )

        # Hybrid query using bool with should
        body = {
            "query": {
                "bool": {
                    "should": [
                        # Keyword component (weighted)
                        {
                            "multi_match": {
                                "query": query,
                                "fields": [
                                    "title^3",
                                    "description^2",
                                    "content",
                                    "tags^2",
                                ],
                                "type": "best_fields",
                                "fuzziness": "AUTO",
                                "boost": 1.0,
                            }
                        },
                        # Semantic component (weighted)
                        {
                            "script_score": {
                                "query": {"exists": {"field": "embedding"}},
                                "script": {
                                    "source": "(cosineSimilarity(params.query_vector, 'embedding') + 1.0) * params.boost",
                                    "params": {
                                        "query_vector": query_vector,
                                        "boost": 2.0,  # Semantic weight
                                    },
                                },
                            }
                        },
                    ],
                    "filter": filters,
                    "minimum_should_match": 1,
                }
            },
            "highlight": {
                "fields": {
                    "title": {"number_of_fragments": 0},
                    "description": {"number_of_fragments": 2, "fragment_size": 150},
                },
                "pre_tags": ["<mark>"],
                "post_tags": ["</mark>"],
            },
            "from": (page - 1) * page_size,
            "size": page_size,
            "_source": {"excludes": ["embedding", "content"]},
        }

        try:
            response = await self.es.search(index=index_name, body=body)
            return self._parse_response(response, query, "hybrid")
        except Exception as e:
            logger.error(f"Hybrid search error: {e}")
            # Fall back to keyword search
            return await self._keyword_search(
                index_name, query, filters, page, page_size
            )

    async def suggest(
        self,
        user_id: str,
        prefix: str,
        size: int = 5,
    ) -> List[str]:
        """
        Get autocomplete suggestions.

        Args:
            user_id: User ID
            prefix: Search prefix
            size: Max suggestions

        Returns:
            List of suggested titles
        """
        index_name = self._get_index_name(user_id)

        body = {
            "suggest": {
                "title-suggest": {
                    "prefix": prefix,
                    "completion": {
                        "field": "title.suggest",
                        "size": size,
                        "skip_duplicates": True,
                        "fuzzy": {
                            "fuzziness": "AUTO",
                        },
                    },
                }
            },
        }

        try:
            response = await self.es.search(index=index_name, body=body)
            suggestions = []
            suggest_data = response.get("suggest", {}).get("title-suggest", [])
            for suggest_item in suggest_data:
                for option in suggest_item.get("options", []):
                    suggestions.append(option.get("text", ""))
            return suggestions
        except Exception as e:
            logger.error(f"Suggest error: {e}")
            return []

    def _build_filters(
        self,
        source_ids: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        is_starred: Optional[bool] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """Build Elasticsearch filter clauses."""
        filters = []

        if source_ids:
            filters.append({"terms": {"source_id": source_ids}})

        if tags:
            filters.append({"terms": {"tags": tags}})

        if is_starred is not None:
            filters.append({"term": {"is_starred": is_starred}})

        if start_date or end_date:
            range_filter: Dict[str, Any] = {"range": {"crawled_at": {}}}
            if start_date:
                range_filter["range"]["crawled_at"]["gte"] = start_date.isoformat()
            if end_date:
                range_filter["range"]["crawled_at"]["lte"] = end_date.isoformat()
            filters.append(range_filter)

        return filters

    def _parse_response(
        self,
        response: Dict[str, Any],
        query: str,
        search_type: str,
    ) -> SearchResponse:
        """Parse ES response into SearchResponse."""
        hits = response.get("hits", {})
        total = hits.get("total", {}).get("value", 0)
        took = response.get("took", 0)

        results = []
        for hit in hits.get("hits", []):
            source = hit.get("_source", {})
            highlights = hit.get("highlight", {})

            # Parse dates
            published_at = None
            if source.get("published_at"):
                try:
                    published_at = datetime.fromisoformat(
                        source["published_at"].replace("Z", "+00:00")
                    )
                except (ValueError, TypeError):
                    pass

            crawled_at = datetime.utcnow()
            if source.get("crawled_at"):
                try:
                    crawled_at = datetime.fromisoformat(
                        source["crawled_at"].replace("Z", "+00:00")
                    )
                except (ValueError, TypeError):
                    pass

            results.append(
                SearchResult(
                    id=hit.get("_id", ""),
                    title=source.get("title", ""),
                    url=source.get("url", ""),
                    description=source.get("description"),
                    image_url=source.get("image_url"),
                    source_name=source.get("source_name", ""),
                    source_id=source.get("source_id", ""),
                    published_at=published_at,
                    crawled_at=crawled_at,
                    tags=source.get("tags", []),
                    is_read=source.get("is_read", False),
                    is_starred=source.get("is_starred", False),
                    score=hit.get("_score", 0.0),
                    highlights=highlights,
                )
            )

        return SearchResponse(
            query=query,
            total=total,
            results=results,
            took_ms=took,
            search_type=search_type,
        )


async def get_search_service() -> SearchService:
    """Get search service instance with ES client."""
    return SearchService(es_client.client)
