"""LangChain ChatModel provider.

Provides a unified factory for creating LangChain chat models.
Currently supports OpenAI-compatible endpoints (GPT-5.2).
"""

from functools import lru_cache
from typing import Optional

from langchain_openai import ChatOpenAI
from loguru import logger

from app.core.config import settings


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
