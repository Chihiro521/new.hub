"""Provider router for external web search."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from app.core.config import settings
from app.services.ai.search_providers.base import (
    ExternalSearchQuery,
    ExternalSearchResult,
)
from app.services.ai.search_providers.searxng_provider import SearXNGProvider
from app.services.ai.search_providers.tavily_provider import TavilyProvider


@dataclass
class ExternalSearchExecution:
    """Result of provider-routed external search execution."""

    provider_requested: str
    provider_used: str
    fallback_used: bool
    results: List[ExternalSearchResult]


class ExternalSearchRouter:
    """Routes external search requests to available providers with fallback."""

    def __init__(self):
        self.providers = {
            "searxng": SearXNGProvider(),
            "tavily": TavilyProvider(),
        }

    async def search(
        self,
        request: ExternalSearchQuery,
        provider: str = "auto",
    ) -> ExternalSearchExecution:
        requested = (provider or "auto").lower()
        primary_name = self._resolve_primary_provider(requested)
        primary = self.providers.get(primary_name)

        if primary and primary.available:
            primary_results = await primary.search(request)
            if primary_results:
                return ExternalSearchExecution(
                    provider_requested=requested,
                    provider_used=primary_name,
                    fallback_used=False,
                    results=primary_results,
                )

        fallback_name = self._resolve_fallback_provider(primary_name)
        fallback = self.providers.get(fallback_name) if fallback_name else None
        if fallback and fallback.available:
            fallback_results = await fallback.search(request)
            if fallback_results:
                return ExternalSearchExecution(
                    provider_requested=requested,
                    provider_used=fallback_name,
                    fallback_used=True,
                    results=fallback_results,
                )

        return ExternalSearchExecution(
            provider_requested=requested,
            provider_used=primary_name,
            fallback_used=False,
            results=[],
        )

    async def options(self) -> Dict[str, object]:
        providers = []
        for name, provider in self.providers.items():
            data = await provider.options()
            providers.append(data)

        return {
            "default_provider": settings.external_search_default_provider,
            "fallback_provider": settings.external_search_fallback_provider,
            "providers": providers,
        }

    async def status(self) -> Dict[str, object]:
        checks = []
        for provider in self.providers.values():
            checks.append(await provider.healthcheck())

        healthy = [item for item in checks if item.get("healthy")]
        return {
            "default_provider": settings.external_search_default_provider,
            "fallback_provider": settings.external_search_fallback_provider,
            "healthy_provider_count": len(healthy),
            "providers": checks,
        }

    def _resolve_primary_provider(self, requested: str) -> str:
        if requested in self.providers:
            return requested
        configured = settings.external_search_default_provider.lower()
        if configured in self.providers:
            return configured
        if self.providers["searxng"].available:
            return "searxng"
        return "tavily"

    def _resolve_fallback_provider(self, primary_name: str) -> str | None:
        fallback = settings.external_search_fallback_provider.lower()
        if fallback in self.providers and fallback != primary_name:
            return fallback
        candidates = [name for name in self.providers if name != primary_name]
        return candidates[0] if candidates else None
