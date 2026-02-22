"""Deep Research Agent — multi-step research workflow.

Implements a structured research pipeline:
  plan → search → deep_read → synthesize

Unlike the basic ResearchAgent (single reason→tool loop), this agent
follows a deliberate multi-phase approach for thorough research tasks.
"""

import json
import time
from typing import Annotated, Any, AsyncGenerator, Dict, List, Literal, Optional, TypedDict

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from loguru import logger

from app.core.config import settings
from app.services.ai.audit import AuditLogger
from app.services.ai.model_provider import get_chat_model

# ---------------------------------------------------------------------------
# State schema
# ---------------------------------------------------------------------------

class ResearchState(TypedDict):
    """State that flows through the research graph."""
    query: str
    user_id: str
    system_prompt: str
    # plan phase
    sub_questions: List[str]
    # search phase
    search_results: List[Dict[str, Any]]
    # deep_read phase
    page_contents: List[Dict[str, Any]]
    # synthesize phase
    report: str
    sources: List[Dict[str, str]]
    # streaming
    status_updates: List[str]


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

PLAN_PROMPT = """你是一个研究规划专家。用户提出了一个研究问题，请将其分解为2-5个具体的子问题。
每个子问题应该是独立可搜索的。只输出JSON数组，不要其他内容。

用户问题: {query}

输出格式: ["子问题1", "子问题2", ...]"""

SYNTHESIZE_PROMPT = """你是一个研究报告撰写专家。基于以下搜索结果和网页内容，撰写一份结构化的研究报告。

原始问题: {query}

搜索结果:
{search_results}

网页详细内容:
{page_contents}

要求:
1. 用中文撰写
2. 开头给出简明摘要(2-3句话)
3. 按主题分段论述，每段有小标题
4. 关键信息标注来源 [来源标题](URL)
5. 结尾给出总结和建议
6. 如果信息不足，明确指出哪些方面需要进一步研究

请直接输出报告内容:"""

DEFAULT_RESEARCH_SYSTEM = "你是 News Hub 的深度研究助手，擅长多步骤信息搜集和综合分析。"


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class DeepResearchAgent:
    """Multi-step research agent: plan → search → deep_read → synthesize."""

    def __init__(self):
        self.audit = AuditLogger()

    def _build_graph(self, user_id: str) -> Any:
        model = get_chat_model()
        if model is None:
            return None

        # --- Node: plan ---
        async def plan(state: ResearchState) -> dict:
            """Decompose the user query into sub-questions."""
            prompt = PLAN_PROMPT.format(query=state["query"])
            response = await model.ainvoke([
                SystemMessage(content=state.get("system_prompt", DEFAULT_RESEARCH_SYSTEM)),
                HumanMessage(content=prompt),
            ])
            text = response.content or "[]"
            try:
                start = text.find("[")
                end = text.rfind("]")
                sub_questions = json.loads(text[start:end + 1]) if start >= 0 else [state["query"]]
            except Exception:
                sub_questions = [state["query"]]

            return {
                "sub_questions": sub_questions,
                "status_updates": [f"[📋 已分解为 {len(sub_questions)} 个子问题]"],
            }

        # --- Node: search ---
        async def search(state: ResearchState) -> dict:
            """Search ES + web for each sub-question."""
            from app.services.ai.tools.search_tools import create_search_tools

            tools = create_search_tools(user_id)
            search_user = tools[0]  # search_user_news
            web_search = tools[2]   # web_search

            all_results = []
            updates = []

            for q in state["sub_questions"]:
                # ES search
                try:
                    es_raw = await search_user.ainvoke({"query": q, "limit": 3})
                    es_data = json.loads(es_raw) if isinstance(es_raw, str) else es_raw
                    for r in es_data.get("results", []):
                        r["origin"] = "internal"
                        all_results.append(r)
                except Exception as e:
                    logger.warning(f"ES search failed for '{q}': {e}")

                # Web search
                try:
                    web_raw = await web_search.ainvoke({"query": q, "max_results": 5})
                    web_data = json.loads(web_raw) if isinstance(web_raw, str) else web_raw
                    for r in web_data.get("results", []):
                        r["origin"] = "external"
                        all_results.append(r)
                except Exception as e:
                    logger.warning(f"Web search failed for '{q}': {e}")

                updates.append(f"[🔍 搜索: {q}]")

            # Deduplicate by URL
            seen_urls = set()
            unique = []
            for r in all_results:
                url = r.get("url", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    unique.append(r)

            return {
                "search_results": unique,
                "status_updates": updates + [f"[📊 共找到 {len(unique)} 条不重复结果]"],
            }

        # --- Node: deep_read ---
        async def deep_read(state: ResearchState) -> dict:
            """Scrape top-ranked pages for full content."""
            from app.services.ai.tools.content_tools import create_content_tools

            scrape_tool = create_content_tools()[1]  # scrape_webpage

            # Pick top 3 external results to deep-read
            external = [r for r in state["search_results"] if r.get("origin") == "external"]
            to_read = external[:3]

            contents = []
            updates = []
            for item in to_read:
                url = item.get("url", "")
                if not url:
                    continue
                try:
                    raw = await scrape_tool.ainvoke({"url": url})
                    data = json.loads(raw) if isinstance(raw, str) else raw
                    if data.get("content") and not data.get("error"):
                        contents.append({
                            "title": data.get("title", item.get("title", "")),
                            "url": url,
                            "content": data["content"],
                        })
                        updates.append(f"[📖 已读取: {data.get('title', url)[:40]}]")
                except Exception as e:
                    logger.warning(f"Scrape failed for {url}: {e}")

            return {
                "page_contents": contents,
                "status_updates": updates if updates else ["[📖 无需深度阅读]"],
            }

        # --- Node: synthesize ---
        async def synthesize(state: ResearchState) -> dict:
            """Generate the final research report."""
            search_text = "\n".join(
                f"- [{r.get('title', 'N/A')}]({r.get('url', '')}) ({r.get('origin', '')}): {r.get('description', '')[:120]}"
                for r in state["search_results"][:15]
            )
            page_text = "\n\n".join(
                f"### {p['title']}\nURL: {p['url']}\n{p['content'][:1500]}"
                for p in state["page_contents"]
            ) or "(无深度阅读内容)"

            prompt = SYNTHESIZE_PROMPT.format(
                query=state["query"],
                search_results=search_text,
                page_contents=page_text,
            )
            response = await model.ainvoke([
                SystemMessage(content=state.get("system_prompt", DEFAULT_RESEARCH_SYSTEM)),
                HumanMessage(content=prompt),
            ])

            report = response.content or ""

            # Extract sources
            sources = []
            seen = set()
            for r in state["search_results"]:
                url = r.get("url", "")
                if url and url not in seen:
                    seen.add(url)
                    sources.append({"title": r.get("title", ""), "url": url})

            return {
                "report": report,
                "sources": sources[:20],
                "status_updates": ["[✅ 报告生成完成]"],
            }

        # --- Decide whether to deep_read ---
        def should_deep_read(state: ResearchState) -> Literal["deep_read", "synthesize"]:
            external = [r for r in state["search_results"] if r.get("origin") == "external"]
            if external:
                return "deep_read"
            return "synthesize"

        # --- Build graph ---
        builder = StateGraph(ResearchState)
        builder.add_node("plan", plan)
        builder.add_node("search", search)
        builder.add_node("deep_read", deep_read)
        builder.add_node("synthesize", synthesize)

        builder.add_edge(START, "plan")
        builder.add_edge("plan", "search")
        builder.add_conditional_edges("search", should_deep_read, ["deep_read", "synthesize"])
        builder.add_edge("deep_read", "synthesize")
        builder.add_edge("synthesize", END)

        return builder.compile()

    async def research(
        self,
        query: str,
        user_id: str,
        system_prompt: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """Run deep research and stream status updates + final report."""
        t0 = time.monotonic()

        graph = self._build_graph(user_id)
        if graph is None:
            yield "AI 助手暂不可用，请先配置 OPENAI_API_KEY。"
            return

        initial_state: ResearchState = {
            "query": query,
            "user_id": user_id,
            "system_prompt": system_prompt or DEFAULT_RESEARCH_SYSTEM,
            "sub_questions": [],
            "search_results": [],
            "page_contents": [],
            "report": "",
            "sources": [],
            "status_updates": [],
        }

        try:
            # Stream node-by-node updates
            final_state = None
            async for event in graph.astream(initial_state, stream_mode="updates"):
                for node_name, node_output in event.items():
                    # Yield status updates
                    for status in node_output.get("status_updates", []):
                        yield status + "\n"

                    # If synthesize node, stream the report
                    if node_name == "synthesize" and node_output.get("report"):
                        yield "\n---\n\n"
                        yield node_output["report"]
                        final_state = node_output

            await self.audit.log(
                user_id=user_id,
                action="deep_research",
                input_summary=query[:200],
                output_summary=(final_state or {}).get("report", "")[:200],
                model=settings.agent_model,
                latency_ms=int((time.monotonic() - t0) * 1000),
            )

        except Exception as e:
            logger.error(f"Deep research failed: {e}")
            yield f"\n抱歉，研究过程中发生错误：{str(e)}"
            await self.audit.log(
                user_id=user_id,
                action="deep_research",
                input_summary=query[:200],
                model=settings.agent_model,
                latency_ms=int((time.monotonic() - t0) * 1000),
                error=str(e),
            )
