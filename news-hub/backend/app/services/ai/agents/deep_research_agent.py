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
REPORT_SEPARATOR = "\n[REPORT_START]\n"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _content_to_text(content: Any) -> str:
    """Best-effort extraction of plain text from model content payloads."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [_content_to_text(item) for item in content]
        return "".join(p for p in parts if p)
    if isinstance(content, dict):
        text = content.get("text")
        if isinstance(text, str):
            return text
        if isinstance(text, dict):
            nested = text.get("value") or text.get("text")
            if isinstance(nested, str):
                return nested
        for key in ("output_text", "content", "value", "delta"):
            value = content.get(key)
            if isinstance(value, str):
                return value
            if isinstance(value, (list, dict)):
                nested = _content_to_text(value)
                if nested:
                    return nested
        return ""
    text_attr = getattr(content, "text", None)
    if isinstance(text_attr, str):
        return text_attr
    content_attr = getattr(content, "content", None)
    if content_attr is not None and content_attr is not content:
        return _content_to_text(content_attr)
    # Final fallback: stringify non-empty objects
    # Be conservative: only return if it looks like real text (not repr of objects)
    fallback = str(content).strip()
    if fallback and fallback not in ("None", "", "{}") and len(fallback) > 5 and not fallback.startswith(("AIMessage", "HumanMessage", "content=")):
        return fallback
    return ""


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

    @staticmethod
    def _build_fallback_report(state: ResearchState) -> str:
        """Build a deterministic markdown report when LLM synthesis returns empty."""
        query = str(state.get("query", "")).strip()
        search_results = state.get("search_results", []) or []
        page_contents = state.get("page_contents", []) or []
        round2_results = state.get("round2_results", []) or []
        round2_contents = state.get("round2_contents", []) or []

        lines: List[str] = []
        lines.append("## 研究摘要")
        lines.append("")
        lines.append("本次研究流程已完成，但模型整合阶段未返回完整文本。以下为基于已抓取数据自动生成的结构化报告。")
        lines.append("")
        if query:
            lines.append(f"- 研究主题：{query}")
        lines.append(f"- 第一轮检索结果：{len(search_results)} 条")
        lines.append(f"- 第一轮深度阅读成功：{len(page_contents)} 条")
        lines.append(f"- 第二轮定向检索结果：{len(round2_results)} 条")
        lines.append(f"- 第二轮深度阅读成功：{len(round2_contents)} 条")
        lines.append("")

        lines.append("## 第一轮高相关来源")
        lines.append("")
        if search_results:
            for r in search_results[:10]:
                title = str(r.get("title", "")).strip() or "N/A"
                url = str(r.get("url", "")).strip() or ""
                desc = str(r.get("description", "")).strip()
                source = f"- [{title}]({url})" if url else f"- {title}"
                if desc:
                    source += f"：{desc[:120]}"
                lines.append(source)
        else:
            lines.append("- （无）")
        lines.append("")

        lines.append("## 深度阅读要点")
        lines.append("")
        if page_contents or round2_contents:
            merged_pages = (page_contents + round2_contents)[:8]
            for p in merged_pages:
                title = str(p.get("title", "")).strip() or "N/A"
                url = str(p.get("url", "")).strip() or ""
                content = str(p.get("content", "")).strip()
                preview = content[:260].replace("\n", " ").strip()
                source = f"- [{title}]({url})" if url else f"- {title}"
                if preview:
                    source += f"：{preview}"
                lines.append(source)
        else:
            lines.append("- （无）")
        lines.append("")

        lines.append("## 后续建议")
        lines.append("")
        lines.append("1. 重试一次深度研究（可能是模型瞬时超时或空响应）。")
        lines.append("2. 缩小主题范围并指定时间窗（可提升最终整合稳定性）。")
        lines.append("3. 对关键来源执行二次核验（优先官方访谈、制作人员采访、发行方资料）。")
        lines.append("")

        return "\n".join(lines).strip()

    def _build_graph(self, user_id: str) -> Any:
        model = get_chat_model()
        if model is None:
            return None

        async def _llm(system: str, user: str, timeout_s: int = 90) -> str:
            for attempt in range(2):
                try:
                    # Brief pause between LLM calls to avoid proxy rate limits
                    await asyncio.sleep(0.3)
                    resp = await asyncio.wait_for(
                        model.ainvoke([SystemMessage(content=system), HumanMessage(content=user)]),
                        timeout=timeout_s,
                    )
                    text = _content_to_text(getattr(resp, "content", None))
                    if text:
                        return text
                    logger.warning(f"LLM attempt {attempt+1} returned empty/non-text content")
                except Exception as e:
                    logger.warning(f"LLM attempt {attempt+1} failed: {e}")
                    if attempt < 1:
                        await asyncio.sleep(1)
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

            async def _search_one_query(q: str):
                """Run ES + web search for a single query, return (results, provenance, es_hits, web_hits)."""
                results = []
                p = []
                es_h = web_h = 0
                # ES
                try:
                    es_raw = await search_user.ainvoke({"query": q, "limit": 3})
                    es_data = json.loads(es_raw) if isinstance(es_raw, str) else es_raw
                    hits = es_data.get("results", [])
                    for r in hits:
                        r["origin"] = "internal"
                        results.append(r)
                    es_h = len(hits)
                    p.append({"phase": "search", "source": "elasticsearch", "query": q, "hits": len(hits)})
                except Exception as e:
                    p.append({"phase": "search", "source": "elasticsearch", "query": q, "hits": 0, "error": str(e)})
                # Web
                try:
                    web_raw = await web_search.ainvoke({"query": q, "max_results": 8})
                    web_data = json.loads(web_raw) if isinstance(web_raw, str) else web_raw
                    hits = web_data.get("results", [])
                    provider = web_data.get("provider", "unknown")
                    for r in hits:
                        r["origin"] = "external"
                        results.append(r)
                    web_h = len(hits)
                    p.append({"phase": "search", "source": f"web/{provider}", "query": q, "hits": len(hits),
                              "engines": list({r.get("engine", "?") for r in hits})})
                except Exception as e:
                    p.append({"phase": "search", "source": "web", "query": q, "hits": 0, "error": str(e)})
                return results, p, es_h, web_h

            # Run all queries in parallel
            query_results = await asyncio.gather(
                *[_search_one_query(q) for q in state["search_queries"]],
                return_exceptions=True,
            )
            for qr in query_results:
                if isinstance(qr, Exception):
                    logger.warning(f"Search query failed: {qr}")
                    continue
                results, p, es_h, web_h = qr
                all_results.extend(results)
                prov.extend(p)
                es_count += es_h
                web_count += web_h

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
                    if len(content) > 6000:
                        content = content[:6000]
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

            async def _targeted_one(q: str):
                """Run a single targeted web search query."""
                results = []
                p_item = None
                try:
                    raw = await web_search.ainvoke({"query": q, "max_results": 5})
                    data = json.loads(raw) if isinstance(raw, str) else raw
                    hits = data.get("results", [])
                    new_hits = [r for r in hits if r.get("url") not in existing_urls]
                    for r in new_hits:
                        r["origin"] = "external_r2"
                        results.append(r)
                    p_item = {"phase": "targeted_search", "query": q, "hits": len(hits), "new": len(new_hits)}
                except Exception as e:
                    p_item = {"phase": "targeted_search", "query": q, "hits": 0, "error": str(e)}
                return results, p_item

            # Run all targeted queries in parallel
            targeted_results = await asyncio.gather(
                *[_targeted_one(q) for q in queries],
                return_exceptions=True,
            )
            for tr in targeted_results:
                if isinstance(tr, Exception):
                    logger.warning(f"Targeted search query failed: {tr}")
                    continue
                results, p_item = tr
                for r in results:
                    existing_urls.add(r.get("url"))
                all_results.extend(results)
                if p_item:
                    prov.append(p_item)

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
                    if len(content) > 6000:
                        content = content[:6000]
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
            await asyncio.sleep(0.5)

            search_summary = "\n".join(
                f"- [{r.get('title', 'N/A')}]({r.get('url', '')}): {r.get('description', '')[:80]}"
                for r in state["search_results"][:12]
            )
            read_content = "\n\n".join(
                f"### {p['title']}\nURL: {p['url']}\n{p['content'][:1200]}"
                for p in state["page_contents"]
            ) or "(无)"
            round2_summary = "\n".join(
                f"- [{r.get('title', 'N/A')}]({r.get('url', '')}): {r.get('description', '')[:80]}"
                for r in state["round2_results"][:8]
            ) or "(无)"
            round2_content = "\n\n".join(
                f"### {p['title']}\nURL: {p['url']}\n{p['content'][:1200]}"
                for p in state["round2_contents"]
            ) or "(无)"

            prompt = SYNTHESIZE_PROMPT.format(
                query=state["query"],
                search_summary=search_summary,
                read_content=read_content,
                round2_summary=round2_summary,
                round2_content=round2_content,
            )
            report = await _llm(state.get("system_prompt", DEFAULT_RESEARCH_SYSTEM), prompt, timeout_s=60)
            if not isinstance(report, str) or not report.strip():
                logger.warning("Synthesize returned empty report, using deterministic fallback report")
                report = self._build_fallback_report(state)

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
                    if node_name == "synthesize":
                        raw_report = node_output.get("report")
                        report_text = raw_report if isinstance(raw_report, str) else str(raw_report or "")
                        report_text = report_text.strip()
                        logger.info(
                            "deep_research synthesize output: report_len={} raw_type={} sources={}",
                            len(report_text), type(raw_report).__name__,
                            len(node_output.get("sources", [])),
                        )
                        if not report_text:
                            source_count = len(node_output.get("sources", []))
                            logger.warning("Deep research synthesize returned empty report, using fallback text")
                            report_text = (
                                "## 研究结果\n\n"
                                "本次深度研究流程已完成，但最终整合阶段未返回正文内容。\n\n"
                                f"- 主题：{query}\n"
                                f"- 已汇总来源：{source_count} 条\n\n"
                                "请重试一次，或缩小研究范围后再试。"
                            )
                        # Yield separator + first chunk together to reduce
                        # chance of TCP split between marker and content
                        first_chunk = report_text[:80]
                        yield REPORT_SEPARATOR + first_chunk
                        # Stream remaining report in small chunks
                        chunk_size = 80
                        for i in range(80, len(report_text), chunk_size):
                            yield report_text[i:i + chunk_size]
                        final_state = {**node_output, "report": report_text}

            # Safety net: if graph completed but synthesize was never reached
            if final_state is None:
                logger.warning("deep_research graph completed without synthesize output, injecting fallback")
                yield REPORT_SEPARATOR
                fallback = self._build_fallback_report(initial)
                chunk_size = 80
                for i in range(0, len(fallback), chunk_size):
                    yield fallback[i:i + chunk_size]

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
