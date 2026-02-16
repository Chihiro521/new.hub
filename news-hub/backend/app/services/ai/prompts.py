"""Prompt templates for AI assistant tasks."""

SYSTEM_CHAT = (
    "你是 News Hub 的中文新闻分析助手。"
    "请基于用户提供的新闻上下文给出准确、简洁、可执行的回答。"
    "不要编造事实；如果信息不足请明确说明。"
)

SUMMARIZE_TEMPLATE = """
请阅读以下新闻并输出三句话中文摘要。

标题：{title}
来源：{source}
正文：{content}

要求：
1. 只输出三句话。
2. 使用客观中立语气。
3. 不要加入未在原文出现的事实。
""".strip()

CLASSIFY_TEMPLATE = """
你是新闻标签分类助手。请根据标题和正文，从候选标签中选择最相关标签。

标题：{title}
正文：{content}
候选标签：{available_tags}

请仅返回 JSON 数组字符串，例如：["科技", "AI"]。
若没有合适标签，返回 []。
""".strip()

DISCOVER_SOURCES_TEMPLATE = """
请为以下主题推荐新闻源，返回 JSON 数组。

主题：{topic}

每个元素为对象，格式：
{{"name": "源名称", "url": "https://...", "type": "rss", "description": "简述"}}

要求：
1. 优先推荐可信、长期更新的来源。
2. type 仅使用 rss、api、html 之一。
3. 仅输出 JSON 数组，不要输出其他文本。
""".strip()
