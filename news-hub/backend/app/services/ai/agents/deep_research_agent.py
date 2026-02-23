"""Deep Research Agent v2 — iterative multi-step research workflow.

Pipeline:
  plan → search → smart_select → deep_read (parallel)
    → extract_entities → targeted_search → deep_read_2 (parallel)
    → synthesize

Key improvements over v1:
  - Short keyword search queries instead of academic questions
  - LLM-based URL relevance ranking before deep reading
  - Lightweight Crawl4AI extraction (skip Phase 2 LLM formatting)
  - Parallel deep reading via asyncio.gather
  - Iterative deepening: extract entities → targeted search → second read
  - Data provenance tracking throughout
"""

import asyncio
import json
import time
from typing import Any, AsyncGenerator, Dict, List, Literal, Optional, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from loguru import logger

from app.core.config import settings
from app.services.ai.audit import AuditLogger
from app.services.ai.model_provider import get_chat_model


# ---------------------------------------------------------------------------
# State schema
# ---------------------------------------------------------------------------

class ResearchState(TypedDict):
    query: str
    user_id: str
    system_prompt: str
    # plan
    search_queries: List[str]
    # search
    search_results: List[Dict[str, Any]]
    # smart_select + deep_read
    selected_urls: List[str]
    page_contents: List[Dict[str, Any]]
    # iterative deepening
    extracted_entities: List[str]
    targeted_queries: List[str]
    round2_results: List[Dict[str, Any]]
    round2_contents: List[Dict[str, Any]]
    # synthesize
    report: str
    sources: List[Dict[str, str]]
    # meta
    status_updates: List[str]
    provenance: List[Dict[str, Any]]


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

PLAN_PROMPT = """你是搜索查询专家。用户提出了一个研究问题，请生成3-5个简短的搜索关键词查询。

要求：
- 每个查询控制在5-15个字，像在搜索引擎里输入的那样
- 包含核心实体名+不同维度的关键词
- 不要写成问句，不要加引号
- 第一个查询应该是最直接的（实体名+身份）

用户问题: {query}

只输出JSON数组: ["查询1", "查询2", ...]"""

SELECT_URLS_PROMPT = """从以下搜索结果中，选出与研究主题最相关的URL（最多{max_urls}个）。

研究主题: {query}

搜索结果:
{results_text}

只输出JSON数组，包含你选择的URL序号（从1开始）: [1, 3, 5, ...]"""

EXTRACT_ENTITIES_PROMPT = """你是信息提取专家。从以下研究材料中，提取出可以用于进一步搜索的具体实体和线索。

研究主题: {query}

已获取的信息:
{content_summary}

请提取：
1. 具体作品名（动画/游戏/广播剧等）
2. 合作者/社团/工作室名称
3. 具体事件/活动/奖项
4. 平台账号/ID
5. 任何可以深挖的冷门线索

然后为每个有价值的线索生成一个简短搜索查询（5-15字）。

只输出JSON数组: ["查询1", "查询2", ...]"""

SYNTHESIZE_PROMPT = """你是研究报告撰写专家。基于以下多轮搜索和深度阅读的结果，撰写一份详尽的研究报告。

原始问题: {query}

== 第一轮搜索结果摘要 ==
{search_summary}

== 第一轮深度阅读内容 ==
{read_content}

== 第二轮定向搜索结果 ==
{round2_summary}

== 第二轮深度阅读内容 ==
{round2_content}

要求:
1. 用中文撰写
2. 开头给出简明摘要(2-3句话)
3. 按主题分段论述，每段有小标题
4. 尽可能包含具体细节（作品名、时间、角色、事件等）
5. 关键信息标注来源 [来源标题](URL)
6. 区分"已验证信息"和"待验证线索"
7. 结尾列出仍需进一步研究的方向

请直接输出报告:"""

DEFAULT_RESEARCH_SYSTEM = "你是 News Hub 的深度研究助手，擅长多步骤信息搜集和综合分析。"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _scrape_light(url: str, timeout_s: int = 75) -> Dict[str, Any]:
    """Scrape a single URL using light mode with timeout."""
    from app.services.collector.webpage_extractor import WebpageExtractor
    extractor = WebpageExtractor()
    try:
        result = await asyncio.wait_for(extractor.extract_light(url), timeout=timeout_s)
        return result or {}
    except asyncio.TimeoutError:
        logger.warning(f"Light scrape timed out ({timeout_s}s) for {url}")
        return {}
    except Exception as e:
        logger.warning(f"Light scrape failed for {url}: {e}")
        return {}


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class DeepResearchAgent:
    """Multi-step research agent v2 with iterative deepening."""

    def __init__(self):
        self.audit = AuditLogger()

    def _build_graph(self, user_id: str) -> Any:
        model = get_chat_model()
        if model is None:
            return None

        async def _llm(system: str, user: str, timeout_s: int = 90) -> str:
            for attempt in range(3):
                try:
                    # Brief pause between LLM calls to avoid proxy rate limits
                    await asyncio.sleep(3)
                    resp = await asyncio.wait_for(
                        model.ainvoke([SystemMessage(content=system), HumanMessage(content=user)]),
                        timeout=timeout_s,
                    )
                    return resp.content or ""
                except Exception as e:
                    logger.warning(f"LLM attempt {attempt+1} failed: {e}")
                    if attempt < 2:
                        await asyncio.sleep(5)
            return ""

        # ---- Node: plan ----
        async def plan(state: ResearchState) -> dict:
            raw = await _llm("你是搜索查询专家。", PLAN_PROMPT.format(query=state["query"]))
            try:
                start, end = raw.find("["), raw.rfind("]")
                queries = json.loads(raw[start:end + 1]) if start >= 0 else [state["query"]]
            except Exception:
                queries = [state["query"]]
            # Ensure queries are short
            queries = [q[:30] for q in queries[:5]]
            return {
                "search_queries": queries,
                "status_updates": [f"[Plan] 生成 {len(queries)} 个搜索查询: {'; '.join(queries)}"],
            }

        # ---- Node: search ----
        async def search(state: ResearchState) -> dict:
            from app.services.ai.tools.search_tools import create_search_tools
            tools = create_search_tools(user_id)
            search_user = tools[0]
            web_search = tools[2]

            all_results = []
            prov = []
            es_count = web_count = 0

            for q in state["search_queries"]:
                # ES
                try:
                    es_raw = await search_user.ainvoke({"query": q, "limit": 3})
                    es_data = json.loads(es_raw) if isinstance(es_raw, str) else es_raw
                    hits = es_data.get("results", [])
                    for r in hits:
                        r["origin"] = "internal"
                        all_results.append(r)
                    es_count += len(hits)
                    prov.append({"phase": "search", "source": "elasticsearch", "query": q, "hits": len(hits)})
                except Exception as e:
                    prov.append({"phase": "search", "source": "elasticsearch", "query": q, "hits": 0, "error": str(e)})

                # Web
                try:
                    web_raw = await web_search.ainvoke({"query": q, "max_results": 8})
                    web_data = json.loads(web_raw) if isinstance(web_raw, str) else web_raw
                    hits = web_data.get("results", [])
                    provider = web_data.get("provider", "unknown")
                    for r in hits:
                        r["origin"] = "external"
                        all_results.append(r)
                    web_count += len(hits)
                    prov.append({"phase": "search", "source": f"web/{provider}", "query": q, "hits": len(hits),
                                 "engines": list({r.get("engine", "?") for r in hits})})
                except Exception as e:
                    prov.append({"phase": "search", "source": "web", "query": q, "hits": 0, "error": str(e)})

            # Deduplicate
            seen = set()
            unique = []
            for r in all_results:
                url = r.get("url", "")
                if url and url not in seen:
                    seen.add(url)
                    unique.append(r)

            return {
                "search_results": unique,
                "status_updates": [f"[Search] {len(unique)} 条结果 (ES:{es_count}, Web:{web_count})"],
                "provenance": prov,
            }

        # ---- Node: smart_select ----
        async def smart_select(state: ResearchState) -> dict:
            external = [r for r in state["search_results"] if r.get("origin") == "external"]
            if not external:
                return {"selected_urls": [], "status_updates": ["[Select] 无外部结果"]}

            results_text = "\n".join(
                f"{i+1}. [{r.get('engine','?')}] {r.get('title','')} — {r.get('url','')}"
                for i, r in enumerate(external[:30])
            )
            raw = await _llm(
                "你是信息相关性评估专家。",
                SELECT_URLS_PROMPT.format(query=state["query"], results_text=results_text, max_urls=5),
            )
            try:
                start, end = raw.find("["), raw.rfind("]")
                indices = json.loads(raw[start:end + 1]) if start >= 0 else []
                selected = [external[i - 1]["url"] for i in indices if 1 <= i <= len(external)]
            except Exception:
                # Fallback: take first 5
                selected = [r["url"] for r in external[:5]]

            selected = selected[:5]
            return {
                "selected_urls": selected,
                "status_updates": [f"[Select] LLM 筛选出 {len(selected)} 个最相关URL"],
            }

        # ---- Node: deep_read (parallel) ----
        async def deep_read(state: ResearchState) -> dict:
            urls = state["selected_urls"]
            if not urls:
                return {"page_contents": [], "status_updates": ["[Read] 无URL可读"], "provenance": []}

            t0 = time.monotonic()
            tasks = [_scrape_light(url) for url in urls]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            contents = []
            prov = []
            for url, result in zip(urls, results):
                elapsed_ms = int((time.monotonic() - t0) * 1000)
                if isinstance(result, Exception):
                    prov.append({"phase": "deep_read", "url": url, "status": "error", "error": str(result)})
                    continue
                if result and result.get("content"):
                    content = result["content"]
                    if len(content) > 8000:
                        content = content[:8000]
                    contents.append({"title": result.get("title", ""), "url": url, "content": content})
                    prov.append({"phase": "deep_read", "url": url, "status": "ok",
                                 "chars": len(content), "quality": result.get("quality_score", 0)})
                else:
                    prov.append({"phase": "deep_read", "url": url, "status": "empty"})

            return {
                "page_contents": contents,
                "status_updates": [f"[Read] 深度阅读 {len(contents)}/{len(urls)} 成功"],
                "provenance": prov,
            }

        # ---- Node: extract_entities ----
        async def extract_entities(state: ResearchState) -> dict:
            # Build summary from search results + page contents
            search_summary = "\n".join(
                f"- {r.get('title','')} ({r.get('url','')}): {r.get('description','')[:80]}"
                for r in state["search_results"][:20]
            )
            content_summary = "\n\n".join(
                f"### {p['title']}\n{p['content'][:2000]}"
                for p in state["page_contents"]
            )
            full_summary = f"搜索结果:\n{search_summary}\n\n深度阅读:\n{content_summary}"

            raw = await _llm(
                "你是信息提取专家。",
                EXTRACT_ENTITIES_PROMPT.format(query=state["query"], content_summary=full_summary),
            )
            try:
                start, end = raw.find("["), raw.rfind("]")
                queries = json.loads(raw[start:end + 1]) if start >= 0 else []
            except Exception:
                queries = []

            queries = [q[:30] for q in queries[:6]]
            return {
                "targeted_queries": queries,
                "status_updates": [f"[Extract] 提取 {len(queries)} 个深挖查询: {'; '.join(queries[:3])}..."]
                if queries else ["[Extract] 未发现可深挖线索"],
            }

        # ---- Node: targeted_search ----
        async def targeted_search(state: ResearchState) -> dict:
            queries = state["targeted_queries"]
            if not queries:
                return {"round2_results": [], "status_updates": ["[Search2] 跳过（无定向查询）"], "provenance": []}

            from app.services.ai.tools.search_tools import create_search_tools
            web_search = create_search_tools(user_id)[2]

            all_results = []
            prov = []
            existing_urls = {r.get("url") for r in state["search_results"]}

            for q in queries:
                try:
                    raw = await web_search.ainvoke({"query": q, "max_results": 5})
                    data = json.loads(raw) if isinstance(raw, str) else raw
                    hits = data.get("results", [])
                    new_hits = [r for r in hits if r.get("url") not in existing_urls]
                    for r in new_hits:
                        r["origin"] = "external_r2"
                        all_results.append(r)
                        existing_urls.add(r.get("url"))
                    prov.append({"phase": "targeted_search", "query": q, "hits": len(hits), "new": len(new_hits)})
                except Exception as e:
                    prov.append({"phase": "targeted_search", "query": q, "hits": 0, "error": str(e)})

            # Deduplicate
            seen = set()
            unique = []
            for r in all_results:
                url = r.get("url", "")
                if url and url not in seen:
                    seen.add(url)
                    unique.append(r)

            return {
                "round2_results": unique,
                "status_updates": [f"[Search2] 定向搜索发现 {len(unique)} 条新结果"],
                "provenance": prov,
            }

        # ---- Node: deep_read_2 (parallel, with LLM selection) ----
        async def deep_read_2(state: ResearchState) -> dict:
            results = state["round2_results"]
            if not results:
                return {"round2_contents": [], "status_updates": ["[Read2] 无新结果可读"], "provenance": []}

            # LLM select top URLs from round 2
            results_text = "\n".join(
                f"{i+1}. [{r.get('engine','?')}] {r.get('title','')} — {r.get('url','')}"
                for i, r in enumerate(results[:20])
            )
            raw = await _llm(
                "你是信息相关性评估专家。",
                SELECT_URLS_PROMPT.format(query=state["query"], results_text=results_text, max_urls=4),
            )
            try:
                start, end = raw.find("["), raw.rfind("]")
                indices = json.loads(raw[start:end + 1]) if start >= 0 else []
                urls = [results[i - 1]["url"] for i in indices if 1 <= i <= len(results)]
            except Exception:
                urls = [r["url"] for r in results[:4]]
            urls = urls[:4]

            if not urls:
                return {"round2_contents": [], "status_updates": ["[Read2] 无相关URL"], "provenance": []}

            t0 = time.monotonic()
            tasks = [_scrape_light(url) for url in urls]
            raw_results = await asyncio.gather(*tasks, return_exceptions=True)

            contents = []
            prov = []
            for url, result in zip(urls, raw_results):
                if isinstance(result, Exception):
                    prov.append({"phase": "deep_read_2", "url": url, "status": "error", "error": str(result)})
                    continue
                if result and result.get("content"):
                    content = result["content"]
                    if len(content) > 8000:
                        content = content[:8000]
                    contents.append({"title": result.get("title", ""), "url": url, "content": content})
                    prov.append({"phase": "deep_read_2", "url": url, "status": "ok", "chars": len(content)})
                else:
                    prov.append({"phase": "deep_read_2", "url": url, "status": "empty"})

            return {
                "round2_contents": contents,
                "status_updates": [f"[Read2] 第二轮深度阅读 {len(contents)}/{len(urls)} 成功"],
                "provenance": prov,
            }

        # ---- Node: synthesize ----
        async def synthesize(state: ResearchState) -> dict:
            # Brief cooldown to avoid proxy rate limits after many LLM calls
            await asyncio.sleep(5)

            search_summary = "\n".join(
                f"- [{r.get('title', 'N/A')}]({r.get('url', '')}): {r.get('description', '')[:80]}"
                for r in state["search_results"][:12]
            )
            read_content = "\n\n".join(
                f"### {p['title']}\nURL: {p['url']}\n{p['content'][:1500]}"
                for p in state["page_contents"]
            ) or "(无)"
            round2_summary = "\n".join(
                f"- [{r.get('title', 'N/A')}]({r.get('url', '')}): {r.get('description', '')[:80]}"
                for r in state["round2_results"][:8]
            ) or "(无)"
            round2_content = "\n\n".join(
                f"### {p['title']}\nURL: {p['url']}\n{p['content'][:1500]}"
                for p in state["round2_contents"]
            ) or "(无)"

            prompt = SYNTHESIZE_PROMPT.format(
                query=state["query"],
                search_summary=search_summary,
                read_content=read_content,
                round2_summary=round2_summary,
                round2_content=round2_content,
            )
            report = await _llm(state.get("system_prompt", DEFAULT_RESEARCH_SYSTEM), prompt, timeout_s=180)

            sources = []
            seen = set()
            for r in state["search_results"] + state["round2_results"]:
                url = r.get("url", "")
                if url and url not in seen:
                    seen.add(url)
                    sources.append({"title": r.get("title", ""), "url": url})

            return {
                "report": report,
                "sources": sources[:30],
                "status_updates": ["[Done] 报告生成完成"],
            }

        # ---- Routing ----
        def should_deep_read(state: ResearchState) -> Literal["deep_read", "synthesize"]:
            return "deep_read" if state["selected_urls"] else "synthesize"

        def should_iterate(state: ResearchState) -> Literal["extract_entities", "synthesize"]:
            if state["page_contents"]:
                return "extract_entities"
            return "synthesize"

        def should_read2(state: ResearchState) -> Literal["deep_read_2", "synthesize"]:
            return "deep_read_2" if state["round2_results"] else "synthesize"

        # ---- Build Graph ----
        builder = StateGraph(ResearchState)
        builder.add_node("plan", plan)
        builder.add_node("search", search)
        builder.add_node("smart_select", smart_select)
        builder.add_node("deep_read", deep_read)
        builder.add_node("extract_entities", extract_entities)
        builder.add_node("targeted_search", targeted_search)
        builder.add_node("deep_read_2", deep_read_2)
        builder.add_node("synthesize", synthesize)

        builder.add_edge(START, "plan")
        builder.add_edge("plan", "search")
        builder.add_edge("search", "smart_select")
        builder.add_conditional_edges("smart_select", should_deep_read, ["deep_read", "synthesize"])
        builder.add_conditional_edges("deep_read", should_iterate, ["extract_entities", "synthesize"])
        builder.add_edge("extract_entities", "targeted_search")
        builder.add_conditional_edges("targeted_search", should_read2, ["deep_read_2", "synthesize"])
        builder.add_edge("deep_read_2", "synthesize")
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

        initial: ResearchState = {
            "query": query,
            "user_id": user_id,
            "system_prompt": system_prompt or DEFAULT_RESEARCH_SYSTEM,
            "search_queries": [],
            "search_results": [],
            "selected_urls": [],
            "page_contents": [],
            "extracted_entities": [],
            "targeted_queries": [],
            "round2_results": [],
            "round2_contents": [],
            "report": "",
            "sources": [],
            "status_updates": [],
            "provenance": [],
        }

        try:
            final_state = None
            async for event in graph.astream(initial, stream_mode="updates"):
                for node_name, node_output in event.items():
                    for status in node_output.get("status_updates", []):
                        yield status + "\n"
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
