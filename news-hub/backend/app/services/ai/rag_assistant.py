"""RAG-enabled AI Assistant — LangGraph implementation.

Delegates to the LangGraph ResearchAgent for tool-calling and reasoning.
Maintains the same public interface (chat_with_rag AsyncGenerator) so that
the /chat-rag API endpoint requires zero changes.
"""

import time
from typing import AsyncGenerator, Dict, List

from loguru import logger

from app.core.config import settings
from app.services.ai.audit import AuditLogger
from app.services.ai.model_provider import get_chat_model


class RAGAssistant:
    """AI Assistant with RAG capabilities, powered by LangGraph."""

    def __init__(self):
        self.audit = AuditLogger()

    async def chat_with_rag(
        self,
        messages: List[Dict[str, str]],
        user_id: str,
        max_iterations: int = 5,
    ) -> AsyncGenerator[str, None]:
        """Chat with RAG capabilities via LangGraph agent.

        The AI can autonomously decide when to retrieve information from:
        - User's news library (Elasticsearch)
        - Recent news (MongoDB)
        - External web search (SearXNG/Tavily)
        """
        from app.services.ai.agents.research_agent import ResearchAgent

        agent = ResearchAgent()
        async for chunk in agent.chat(
            messages=messages,
            user_id=user_id,
        ):
            yield chunk
