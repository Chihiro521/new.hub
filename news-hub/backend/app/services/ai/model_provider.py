"""LangChain ChatModel provider.

Provides a unified factory for creating LangChain chat models.
Currently supports OpenAI-compatible endpoints (GPT-5.2).
"""

from functools import lru_cache
from typing import Optional

from langchain_openai import ChatOpenAI
from loguru import logger

from app.core.config import settings

_cache_initialized = False


def _ensure_llm_cache():
    """Activate MongoDB-backed LLM response cache (once)."""
    global _cache_initialized
    if _cache_initialized or not settings.llm_cache_enabled:
        return
    try:
        from langchain_core.globals import set_llm_cache
        from app.services.ai.llm_cache import MongoDBLLMCache

        set_llm_cache(MongoDBLLMCache())
        _cache_initialized = True
        logger.info(f"LangChain LLM cache activated (MongoDB, TTL={settings.llm_cache_ttl_hours}h)")
    except Exception as e:
        logger.warning(f"Failed to initialize LLM cache: {e}")


@lru_cache(maxsize=1)
def get_chat_model(
    model: Optional[str] = None,
    temperature: Optional[float] = None,
) -> Optional[ChatOpenAI]:
    """Get a cached LangChain ChatOpenAI instance.

    Uses the same OpenAI-compatible config as the existing llm_client,
    but returns a LangChain ChatModel for use with LangGraph agents.
    """
    if not settings.openai_api_key:
        logger.info("OPENAI_API_KEY not configured, agent runs in fallback mode")
        return None

    _ensure_llm_cache()

    effective_model = model or settings.agent_model
    effective_temp = temperature if temperature is not None else settings.agent_temperature

    logger.info(f"Initializing LangChain ChatModel: {effective_model}")
    return ChatOpenAI(
        model=effective_model,
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        temperature=effective_temp,
        timeout=max(settings.openai_timeout, 120),
        max_retries=settings.openai_max_retries,
    )
