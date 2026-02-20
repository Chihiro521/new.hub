"""Compatibility wrapper over the new provider-routed external search layer."""

from typing import Any, Dict, List

from app.services.ai.search_providers import ExternalSearchQuery, ExternalSearchRouter


class WebSearchClient:
    """Backward-compatible interface used by assistant and RAG flows."""

    def __init__(self, provider: str = "auto"):
        self.provider = provider
        self.router = ExternalSearchRouter()

    @property
    def available(self) -> bool:
        """Check if at least one provider is available."""
        return any(provider.available for provider in self.router.providers.values())

    async def search(
        self,
        query: str,
        max_results: int = 5,
        search_depth: str = "basic",
        include_answer: bool = False,
    ) -> List[Dict[str, Any]]:
        """Execute a web search and return normalised result dicts."""
        _ = (search_depth, include_answer)  # kept for call-site compatibility
        execution = await self.router.search(
            request=ExternalSearchQuery(query=query, max_results=max_results),
            provider=self.provider,
        )
        return [
            {
                "title": item.title,
                "url": item.url,
                "description": item.description,
                "content": item.content,
                "score": item.score,
                "provider": item.provider,
                "engine": item.engine,
            }
            for item in execution.results
        ]
