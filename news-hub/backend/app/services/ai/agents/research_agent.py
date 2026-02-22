"""LangGraph Research Agent.

A stateful agent that can autonomously search, fetch, and synthesize
information using the full tool set. Built on LangGraph StateGraph
with streaming support for FastAPI SSE endpoints.
"""

import json
import time
from typing import Any, AsyncGenerator, Dict, List, Literal, Optional

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, MessagesState, StateGraph
from loguru import logger

from app.core.config import settings
from app.services.ai.audit import AuditLogger
from app.services.ai.model_provider import get_chat_model
from app.services.ai.tools import create_tools_for_user


def _create_checkpointer():
    """Create the appropriate checkpointer based on config."""
    if settings.agent_checkpointer == "mongodb":
        try:
            from app.services.ai.checkpointer import MongoDBCheckpointer
            logger.info("Using MongoDB checkpointer for agent state persistence")
            return MongoDBCheckpointer()
        except Exception as e:
            logger.warning(f"MongoDB checkpointer init failed, falling back to memory: {e}")
    return MemorySaver()

RESEARCH_SYSTEM_PROMPT = """你是 News Hub 的智能研究助手。

你可以使用多种工具来帮助用户进行信息研究和分析：
- search_user_news: 搜索用户的新闻库
- get_recent_news: 获取用户最近的新闻
- web_search: 搜索互联网获取最新信息（SearXNG/Tavily）
- fetch_rss: 主动抓取RSS/Atom源的文章列表
- scrape_webpage: 抓取网页正文内容进行深度分析
- save_news_to_library: 保存新闻到用户的新闻库
- list_sources / add_source / delete_source: 管理订阅源
- list_tag_rules / add_tag_rule / delete_tag_rule: 管理标签规则

工作流程：
1. 理解用户的研究问题
2. 制定搜索策略（先查新闻库，不够再搜互联网）
3. 如需深入了解，抓取关键网页内容
4. 综合所有信息，生成结构化的研究回答
5. 引用来源时提供标题和链接

重要原则：
- 优先使用用户的新闻库
- 只在必要时搜索互联网
- 基于事实回答，不要编造信息
- 引用来源时提供标题和链接
- 执行删除等危险操作前，先确认用户意图
- 回答要有条理，适当使用列表和分段
"""


class ResearchAgent:
    """LangGraph-based research agent with tool calling."""

    def __init__(self):
        self.audit = AuditLogger()
        self._checkpointer = _create_checkpointer()

    def _build_graph(self, user_id: str) -> Any:
        """Build a LangGraph StateGraph for the given user."""
        model = get_chat_model()
        if model is None:
            return None

        tools = create_tools_for_user(user_id)
        tools_by_name = {t.name: t for t in tools}
        model_with_tools = model.bind_tools(tools)

        async def reason(state: MessagesState) -> Dict[str, List]:
            """LLM reasoning node — decides whether to call tools or respond."""
            messages = [SystemMessage(content=RESEARCH_SYSTEM_PROMPT)] + state["messages"]
            response = await model_with_tools.ainvoke(messages)
            return {"messages": [response]}

        async def execute_tools(state: MessagesState) -> Dict[str, List]:
            """Execute all tool calls from the last AI message."""
            last_message = state["messages"][-1]
            results = []
            for tool_call in last_message.tool_calls:
                tool_name = tool_call["name"]
                tool_args = tool_call["args"]
                logger.info(f"Agent calling tool: {tool_name} args={tool_args}")
                try:
                    tool_fn = tools_by_name[tool_name]
                    observation = await tool_fn.ainvoke(tool_args)
                except Exception as e:
                    logger.error(f"Tool {tool_name} failed: {e}")
                    observation = json.dumps({"error": str(e)}, ensure_ascii=False)
                results.append(ToolMessage(content=observation, tool_call_id=tool_call["id"]))
            return {"messages": results}

        def should_continue(state: MessagesState) -> Literal["execute_tools", "__end__"]:
            """Route: if the LLM made tool calls, execute them; otherwise finish."""
            last = state["messages"][-1]
            if isinstance(last, AIMessage) and last.tool_calls:
                return "execute_tools"
            return END

        # Build the graph
        builder = StateGraph(MessagesState)
        builder.add_node("reason", reason)
        builder.add_node("execute_tools", execute_tools)
        builder.add_edge(START, "reason")
        builder.add_conditional_edges("reason", should_continue, ["execute_tools", END])
        builder.add_edge("execute_tools", "reason")

        return builder.compile(checkpointer=self._checkpointer)

    async def chat(
        self,
        messages: List[Dict[str, str]],
        user_id: str,
        thread_id: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """Stream agent responses.

        Yields text chunks as the agent reasons and calls tools.
        Compatible with FastAPI StreamingResponse.
        """
        t0 = time.monotonic()

        graph = self._build_graph(user_id)
        if graph is None:
            fallback = "AI 助手暂不可用，请先配置 OPENAI_API_KEY。"
            yield fallback
            await self.audit.log(
                user_id=user_id,
                action="research_chat",
                input_summary=messages[-1].get("content", "")[:200] if messages else "",
                output_summary=fallback,
                latency_ms=int((time.monotonic() - t0) * 1000),
                fallback_used=True,
            )
            return

        # Convert dict messages to LangChain message objects
        lc_messages = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "user":
                lc_messages.append(HumanMessage(content=content))
            elif role == "assistant":
                lc_messages.append(AIMessage(content=content))

        config = {"configurable": {"thread_id": thread_id or user_id}}
        collected_text = []
        tool_calls_made = []

        try:
            async for event in graph.astream_events(
                {"messages": lc_messages}, config=config, version="v2"
            ):
                kind = event["event"]

                # Stream LLM tokens
                if kind == "on_chat_model_stream":
                    chunk = event["data"]["chunk"]
                    if hasattr(chunk, "content") and isinstance(chunk.content, str) and chunk.content:
                        collected_text.append(chunk.content)
                        yield chunk.content

                # Track tool calls for audit
                elif kind == "on_tool_start":
                    tool_name = event.get("name", "unknown")
                    tool_calls_made.append(tool_name)
                    yield f"\n[🔍 {tool_name}...]\n"

            await self.audit.log(
                user_id=user_id,
                action="research_chat",
                input_summary=messages[-1].get("content", "")[:200] if messages else "",
                output_summary="".join(collected_text)[:200],
                model=settings.agent_model,
                latency_ms=int((time.monotonic() - t0) * 1000),
            )

        except Exception as e:
            logger.error(f"Research agent failed: {e}")
            error_msg = f"抱歉，发生错误：{str(e)}"
            yield error_msg
            await self.audit.log(
                user_id=user_id,
                action="research_chat",
                input_summary=messages[-1].get("content", "")[:200] if messages else "",
                model=settings.agent_model,
                latency_ms=int((time.monotonic() - t0) * 1000),
                error=str(e),
            )

