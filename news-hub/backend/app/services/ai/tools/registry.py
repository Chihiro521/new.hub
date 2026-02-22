"""Tool registry — assembles all LangChain tools for a given user."""

from typing import List

from langchain_core.tools import BaseTool

from app.services.ai.tools.content_tools import create_content_tools
from app.services.ai.tools.library_tools import create_library_tools
from app.services.ai.tools.search_tools import create_search_tools
from app.services.ai.tools.tag_tools import create_tag_tools


def create_tools_for_user(user_id: str) -> List[BaseTool]:
    """Create the full set of tools bound to a specific user context.

    Returns a flat list of all available tools for the LangGraph agent.
    """
    return [
        *create_search_tools(user_id),
        *create_content_tools(),
        *create_library_tools(user_id),
        *create_tag_tools(user_id),
    ]
