"""Multi-Agent Debate System — inspired by Grok 4.2 architecture.

Implements a four-agent debate workflow:
  Captain (协调者) → Harper/Benjamin/Lucas (并行) → Debate (辩论) → Captain (合成)

Agents:
  - Captain:   任务分解、策略制定、冲突解决、最终合成
  - Harper:    研究 & 事实专家，拥有搜索/抓取工具
  - Benjamin:  逻辑/分析专家，推理验证、一致性检查
  - Lucas:     创意 & 质疑者，反向思考、偏见检测
"""

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
# Shared State
# ---------------------------------------------------------------------------

class DebateState(TypedDict):
    """Shared state flowing through the multi-agent debate graph."""
    query: str
    user_id: str
    custom_system_prompt: Optional[str]
    # Captain decomposition
    complexity: str          # "simple" | "moderate" | "complex"
    sub_tasks: List[str]
    active_agents: List[str]
    # Agent outputs (round 1)
    harper_output: str
    benjamin_output: str
    lucas_output: str
    # Debate outputs (round 2)
    harper_rebuttal: str
    benjamin_rebuttal: str
    lucas_rebuttal: str
    # Final
    final_report: str
    confidence: str
    sources: List[Dict[str, str]]
    # Streaming
    status_updates: List[str]


# ---------------------------------------------------------------------------
# Agent Prompts
# ---------------------------------------------------------------------------

CAPTAIN_DECOMPOSE_PROMPT = """你是研究团队的队长(Captain)。你的职责是分析用户问题的复杂度，并分解为子任务。

请分析以下问题，输出严格的JSON（不要其他内容）：
{{
  "complexity": "simple|moderate|complex",
  "sub_tasks": ["子任务1", "子任务2", ...],
  "active_agents": ["harper", "benjamin", "lucas"],
  "strategy": "简要说明研究策略"
}}

规则：
- simple: 只需Harper搜索即可回答，active_agents=["harper"]
- moderate: 需要搜索+逻辑验证，active_agents=["harper","benjamin"]
- complex: 需要全部代理参与辩论，active_agents=["harper","benjamin","lucas"]
- sub_tasks: 2-5个具体可执行的子任务

用户问题: {query}"""

HARPER_PROMPT = """你是Harper，研究团队的事实与信息专家。

你的核心职责：
- 基于搜索结果提供准确、最新的事实信息
- 整理关键数据点，标注来源
- 区分已证实的事实和未经验证的说法
- 如果信息不足，明确指出

你的风格：严谨、数据驱动、注重来源可信度。

{custom_prompt}

用户问题: {query}
子任务: {sub_tasks}

搜索结果:
{search_data}

请提供你的研究发现（用中文）:"""

BENJAMIN_PROMPT = """你是Benjamin，研究团队的逻辑与分析专家。

你的核心职责：
- 对问题进行严谨的逻辑分析
- 检验推理链的每一步是否成立
- 识别因果关系、相关性与巧合的区别
- 指出论证中的逻辑漏洞或隐含假设
- 如果涉及数据，验证数值的合理性

你的风格：严密、结构化、不放过任何逻辑缺陷。

{custom_prompt}

用户问题: {query}
子任务: {sub_tasks}

Harper的研究发现:
{harper_output}

请提供你的逻辑分析（用中文）:"""

LUCAS_PROMPT = """你是Lucas，研究团队的创意思考者与质疑者。

你的核心职责：
- 挑战主流观点，提出反向论证
- 检测潜在的认知偏见（确认偏误、幸存者偏差等）
- 提供被忽视的替代视角或解读
- 评估结论的全面性，指出盲点
- 让最终输出更具可读性和平衡性

你的风格：发散、批判性、富有洞察力，但不为反对而反对。

{custom_prompt}

用户问题: {query}
子任务: {sub_tasks}

Harper的研究发现:
{harper_output}

Benjamin的逻辑分析:
{benjamin_output}

请提供你的批判性视角（用中文）:"""

DEBATE_PROMPT = """你是{agent_name}。在看到其他代理的分析后，请进行交叉校验。

你之前的分析:
{own_output}

其他代理的观点:
{other_outputs}

请简要回应：
1. 你同意或修正哪些观点？
2. 你仍然坚持的核心论点是什么？
3. 有什么新的补充？

保持简洁（200字以内）:"""

CAPTAIN_SYNTHESIZE_PROMPT = """你是研究团队的队长(Captain)。现在需要将团队的研究成果合成为最终报告。

原始问题: {query}

== Harper（研究专家）的发现 ==
{harper_output}
{harper_rebuttal}

== Benjamin（逻辑专家）的分析 ==
{benjamin_output}
{benjamin_rebuttal}

== Lucas（创意质疑者）的视角 ==
{lucas_output}
{lucas_rebuttal}

请合成最终研究报告，要求：
1. 开头给出2-3句话的核心结论
2. 按主题分段，整合三位专家的最佳观点
3. 对有争议的点，呈现不同视角并给出你的判断
4. 关键信息标注来源 [来源](URL)
5. 结尾给出置信度评估（高/中/低）和理由
6. 如果Lucas指出了有效的盲点，必须在报告中体现

{custom_prompt}

请输出最终报告（用中文）:"""


# ---------------------------------------------------------------------------
# Multi-Agent Debate Engine
# ---------------------------------------------------------------------------

class MultiAgentDebate:
    """Four-agent debate system inspired by Grok 4.2 architecture."""

    def __init__(self):
        self.audit = AuditLogger()

    def _build_graph(self, user_id: str) -> Any:
        model = get_chat_model()
        if model is None:
            return None

        async def _llm(system: str, user: str) -> str:
            """Helper: single LLM call with retry."""
            import asyncio
            for attempt in range(3):
                try:
                    resp = await asyncio.wait_for(
                        model.ainvoke([
                            SystemMessage(content=system),
                            HumanMessage(content=user),
                        ]),
                        timeout=90,
                    )
                    return resp.content or ""
                except Exception as e:
                    logger.warning(f"LLM call attempt {attempt+1} failed: {e}")
                    if attempt < 2:
                        await asyncio.sleep(2)
            return "(LLM调用失败，跳过此步骤)"

        # ---- Node: captain_decompose ----
        async def captain_decompose(state: DebateState) -> dict:
            prompt = CAPTAIN_DECOMPOSE_PROMPT.format(query=state["query"])
            raw = await _llm("你是研究团队的队长。", prompt)

            # Parse JSON
            try:
                start, end = raw.find("{"), raw.rfind("}")
                data = json.loads(raw[start:end + 1]) if start >= 0 else {}
            except Exception:
                data = {}

            complexity = data.get("complexity", "complex")
            sub_tasks = data.get("sub_tasks", [state["query"]])
            active = data.get("active_agents", ["harper", "benjamin", "lucas"])

            return {
                "complexity": complexity,
                "sub_tasks": sub_tasks,
                "active_agents": active,
                "status_updates": [
                    f"[🎯 Captain: 复杂度={complexity}, 激活代理={','.join(active)}]",
                    f"[📋 子任务: {'; '.join(sub_tasks[:3])}]",
                ],
            }

        # ---- Node: harper_research ----
        async def harper_research(state: DebateState) -> dict:
            if "harper" not in state["active_agents"]:
                return {"harper_output": "(Harper未激活)", "status_updates": []}

            import asyncio

            search_data_parts = []
            external_urls = []

            async def _safe(coro, label, timeout_s=15):
                try:
                    return await asyncio.wait_for(coro, timeout=timeout_s)
                except Exception as e:
                    logger.warning(f"Harper {label} failed: {e}")
                    return None

            try:
                from app.services.ai.tools.search_tools import create_search_tools
                search_tools = create_search_tools(user_id)
                search_user = search_tools[0]
                web_search_tool = search_tools[2]

                for task in state["sub_tasks"][:2]:
                    es_raw = await _safe(search_user.ainvoke({"query": task, "limit": 3}), f"ES:{task[:20]}")
                    if es_raw:
                        es_data = json.loads(es_raw) if isinstance(es_raw, str) else es_raw
                        for r in es_data.get("results", []):
                            search_data_parts.append(f"[内部] {r.get('title', '')} - {r.get('url', '')}: {r.get('description', '')[:100]}")

                    web_raw = await _safe(web_search_tool.ainvoke({"query": task, "max_results": 5}), f"Web:{task[:20]}")
                    if web_raw:
                        web_data = json.loads(web_raw) if isinstance(web_raw, str) else web_raw
                        for r in web_data.get("results", []):
                            search_data_parts.append(f"[外部] {r.get('title', '')} - {r.get('url', '')}: {r.get('description', '')[:100]}")
                            if r.get("url"):
                                external_urls.append({"title": r.get("title", ""), "url": r["url"]})
            except Exception as e:
                logger.warning(f"Harper search init failed: {e}")

            search_data = "\n".join(search_data_parts) or "(无搜索结果)"

            # Deep read: use light mode (skip Phase 2 LLM), parallel, pick best URLs
            deep_read_parts = []
            if external_urls:
                try:
                    from app.services.ai.agents.deep_research_agent import _scrape_light

                    # Simple relevance: prefer URLs whose title contains query keywords
                    query_chars = set(state["query"])
                    scored = sorted(external_urls, key=lambda u: sum(1 for c in query_chars if c in u["title"]), reverse=True)
                    top_urls = [u["url"] for u in scored[:2]]

                    tasks = [_scrape_light(url, timeout_s=60) for url in top_urls]
                    results = await asyncio.gather(*tasks, return_exceptions=True)

                    for url, result in zip(top_urls, results):
                        if isinstance(result, Exception) or not result:
                            continue
                        content = result.get("content", "")
                        if content:
                            deep_read_parts.append(
                                f"=== {result.get('title', url)} ===\n{content[:3000]}"
                            )
                except Exception as e:
                    logger.warning(f"Harper deep read failed: {e}")

            full_search_data = search_data
            if deep_read_parts:
                full_search_data += "\n\n--- 网页详细内容 ---\n" + "\n\n".join(deep_read_parts)

            custom = state.get("custom_system_prompt") or ""

            prompt = HARPER_PROMPT.format(
                query=state["query"],
                sub_tasks="; ".join(state["sub_tasks"]),
                search_data=full_search_data,
                custom_prompt=custom,
            )
            output = await _llm("你是Harper，研究团队的事实与信息专家。", prompt)

            return {
                "harper_output": output,
                "status_updates": [
                    f"[Harper: 搜集了 {len(search_data_parts)} 条信息]",
                    *(
                        [f"[Harper: 深度阅读了 {len(deep_read_parts)} 个网页 (light mode)]"]
                        if deep_read_parts else []
                    ),
                ],
            }

        # ---- Node: benjamin_analyze ----
        async def benjamin_analyze(state: DebateState) -> dict:
            if "benjamin" not in state["active_agents"]:
                return {"benjamin_output": "(Benjamin未激活)", "status_updates": []}

            custom = state.get("custom_system_prompt") or ""
            prompt = BENJAMIN_PROMPT.format(
                query=state["query"],
                sub_tasks="; ".join(state["sub_tasks"]),
                harper_output=state["harper_output"],
                custom_prompt=custom,
            )
            output = await _llm("你是Benjamin，研究团队的逻辑与分析专家。", prompt)

            return {
                "benjamin_output": output,
                "status_updates": ["[🧠 Benjamin: 逻辑分析完成]"],
            }

        # ---- Node: lucas_challenge ----
        async def lucas_challenge(state: DebateState) -> dict:
            if "lucas" not in state["active_agents"]:
                return {"lucas_output": "(Lucas未激活)", "status_updates": []}

            custom = state.get("custom_system_prompt") or ""
            prompt = LUCAS_PROMPT.format(
                query=state["query"],
                sub_tasks="; ".join(state["sub_tasks"]),
                harper_output=state["harper_output"],
                benjamin_output=state["benjamin_output"],
                custom_prompt=custom,
            )
            output = await _llm("你是Lucas，研究团队的创意思考者与质疑者。", prompt)

            return {
                "lucas_output": output,
                "status_updates": ["[💡 Lucas: 批判性视角完成]"],
            }

        # ---- Node: debate_round ----
        async def debate_round(state: DebateState) -> dict:
            """Cross-verification: each agent reviews others' work."""
            rebuttals = {}

            agents_config = [
                ("harper", state["harper_output"], f"Benjamin: {state['benjamin_output']}\nLucas: {state['lucas_output']}"),
                ("benjamin", state["benjamin_output"], f"Harper: {state['harper_output']}\nLucas: {state['lucas_output']}"),
                ("lucas", state["lucas_output"], f"Harper: {state['harper_output']}\nBenjamin: {state['benjamin_output']}"),
            ]

            for agent_name, own, others in agents_config:
                if agent_name not in state["active_agents"]:
                    rebuttals[f"{agent_name}_rebuttal"] = ""
                    continue

                prompt = DEBATE_PROMPT.format(
                    agent_name=agent_name.capitalize(),
                    own_output=own,
                    other_outputs=others,
                )
                rebuttal = await _llm(f"你是{agent_name.capitalize()}，正在进行团队辩论。", prompt)
                rebuttals[f"{agent_name}_rebuttal"] = rebuttal

            return {
                **rebuttals,
                "status_updates": ["[⚔️ 辩论轮: 代理间交叉校验完成]"],
            }

        # ---- Node: captain_synthesize ----
        async def captain_synthesize(state: DebateState) -> dict:
            custom = state.get("custom_system_prompt") or ""
            prompt = CAPTAIN_SYNTHESIZE_PROMPT.format(
                query=state["query"],
                harper_output=state["harper_output"],
                harper_rebuttal=state.get("harper_rebuttal", ""),
                benjamin_output=state["benjamin_output"],
                benjamin_rebuttal=state.get("benjamin_rebuttal", ""),
                lucas_output=state["lucas_output"],
                lucas_rebuttal=state.get("lucas_rebuttal", ""),
                custom_prompt=custom,
            )
            report = await _llm("你是研究团队的队长，负责最终合成。", prompt)

            return {
                "final_report": report,
                "status_updates": ["[✅ Captain: 最终报告合成完成]"],
            }

        # ---- Routing ----
        def should_debate(state: DebateState) -> Literal["debate_round", "captain_synthesize"]:
            if state["complexity"] == "complex":
                return "debate_round"
            return "captain_synthesize"

        # ---- Build Graph ----
        builder = StateGraph(DebateState)

        builder.add_node("captain_decompose", captain_decompose)
        builder.add_node("harper_research", harper_research)
        builder.add_node("benjamin_analyze", benjamin_analyze)
        builder.add_node("lucas_challenge", lucas_challenge)
        builder.add_node("debate_round", debate_round)
        builder.add_node("captain_synthesize", captain_synthesize)

        # Flow: captain → harper → benjamin → lucas → (debate?) → synthesize
        builder.add_edge(START, "captain_decompose")
        builder.add_edge("captain_decompose", "harper_research")
        builder.add_edge("harper_research", "benjamin_analyze")
        builder.add_edge("benjamin_analyze", "lucas_challenge")
        builder.add_conditional_edges("lucas_challenge", should_debate, ["debate_round", "captain_synthesize"])
        builder.add_edge("debate_round", "captain_synthesize")
        builder.add_edge("captain_synthesize", END)

        return builder.compile()

    async def run(
        self,
        query: str,
        user_id: str,
        system_prompt: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """Run the multi-agent debate and stream progress + final report."""
        t0 = time.monotonic()

        graph = self._build_graph(user_id)
        if graph is None:
            yield "AI 助手暂不可用，请先配置 OPENAI_API_KEY。"
            return

        initial: DebateState = {
            "query": query,
            "user_id": user_id,
            "custom_system_prompt": system_prompt,
            "complexity": "complex",
            "sub_tasks": [],
            "active_agents": [],
            "harper_output": "",
            "benjamin_output": "",
            "lucas_output": "",
            "harper_rebuttal": "",
            "benjamin_rebuttal": "",
            "lucas_rebuttal": "",
            "final_report": "",
            "confidence": "",
            "sources": [],
            "status_updates": [],
        }

        try:
            async for event in graph.astream(initial, stream_mode="updates"):
                for node_name, node_output in event.items():
                    for status in node_output.get("status_updates", []):
                        yield status + "\n"

                    if node_name == "captain_synthesize" and node_output.get("final_report"):
                        yield "\n---\n\n"
                        yield node_output["final_report"]

            await self.audit.log(
                user_id=user_id,
                action="multi_agent_debate",
                input_summary=query[:200],
                output_summary="debate completed",
                model=settings.agent_model,
                latency_ms=int((time.monotonic() - t0) * 1000),
            )

        except Exception as e:
            logger.error(f"Multi-agent debate failed: {e}")
            yield f"\n抱歉，研究过程中发生错误：{str(e)}"
            await self.audit.log(
                user_id=user_id,
                action="multi_agent_debate",
                input_summary=query[:200],
                model=settings.agent_model,
                latency_ms=int((time.monotonic() - t0) * 1000),
                error=str(e),
            )
