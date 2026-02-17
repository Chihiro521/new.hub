# AI 助手链路分析报告

## 问题诊断

用户反馈："AI 助手只会自己说话，问它什么都不知道"

## 根本原因

### 1. 聊天功能的设计缺陷 ❌

**当前实现：**
```python
async def chat(self, messages: List[dict], user_id: str):
    payload_messages = [{"role": "system", "content": SYSTEM_CHAT}, *messages]
    # 直接发送给 LLM，没有注入用户数据
```

**问题：**
- AI 聊天功能**没有访问用户的新闻数据**
- 只是一个普通的对话机器人
- System prompt 说"基于用户提供的新闻上下文"，但实际上没有提供任何上下文
- AI 无法回答关于用户新闻库的问题

### 2. 功能分离 ⚠️

AI 助手的功能分为两类：

**A. 有数据访问的功能（工作正常）：**
- ✅ `summarize(news_id)` - 总结特定新闻
- ✅ `classify(news_id)` - 分类特定新闻
- ✅ `augmented_search(query)` - 搜索内部+外部新闻
- ✅ `discover_sources(topic)` - 发现新闻源

**B. 无数据访问的功能（问题所在）：**
- ❌ `chat(messages)` - 普通聊天，无法访问用户数据

## 链路分析

### 正常工作的链路（以 summarize 为例）

```
用户请求 → API → AssistantService.summarize()
    ↓
获取新闻数据: await self._get_news_doc(news_id, user_id)
    ↓
构建 prompt: SUMMARIZE_TEMPLATE.format(title, source, content)
    ↓
调用 LLM: client.chat.completions.create()
    ↓
返回结果 ✅
```

### 有问题的链路（chat）

```
用户请求 → API → AssistantService.chat()
    ↓
直接发送消息: payload_messages = [system_prompt, *messages]
    ↓
调用 LLM: client.chat.completions.create()
    ↓
返回结果 ❌ (AI 不知道用户有什么新闻)
```

## 测试结果

### ✅ 工作的功能

1. **发现新闻源**
```bash
POST /api/v1/assistant/discover-sources
{"topic": "tech news"}
```
返回：10 个科技新闻源建议（Reuters, AP News, The Verge 等）

2. **增强搜索**
```bash
POST /api/v1/assistant/search
{"query": "AI", "include_external": true}
```
返回：
- 内部搜索：0 个结果（因为没有数据）
- 外部搜索：5 个 Web 结果
- AI 摘要：已生成

### ❌ 有问题的功能

**聊天功能**
- 用户问："我有哪些新闻？"
- AI 回答：无法回答，因为它没有访问用户的新闻数据
- 用户问："总结一下最近的科技新闻"
- AI 回答：无法回答，因为它不知道用户订阅了什么

## 设计问题

### 当前 System Prompt

```python
SYSTEM_CHAT = (
    "你是 News Hub 的中文新闻分析助手。"
    "请基于用户提供的新闻上下文给出准确、简洁、可执行的回答。"
    "不要编造事实；如果信息不足请明确说明。"
)
```

**问题：**
- Prompt 说"基于用户提供的新闻上下文"
- 但实际上没有提供任何上下文
- 这是一个**承诺与实现不匹配**的问题

## 解决方案建议

### 方案 1：RAG（检索增强生成）

在聊天时自动检索相关新闻：

```python
async def chat(self, messages: List[dict], user_id: str):
    # 1. 提取用户最后一条消息
    user_query = messages[-1]["content"]

    # 2. 搜索相关新闻
    relevant_news = await self._search_user_news(user_id, user_query, limit=5)

    # 3. 构建增强的 system prompt
    context = self._build_context(relevant_news)
    enhanced_system = f"{SYSTEM_CHAT}\n\n当前用户新闻库上下文：\n{context}"

    # 4. 发送给 LLM
    payload_messages = [{"role": "system", "content": enhanced_system}, *messages]
    ...
```

### 方案 2：Function Calling

让 AI 主动调用工具：

```python
tools = [
    {
        "type": "function",
        "function": {
            "name": "search_user_news",
            "description": "搜索用户的新闻库",
            "parameters": {...}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_recent_news",
            "description": "获取用户最近的新闻",
            "parameters": {...}
        }
    }
]
```

### 方案 3：明确功能分离

在 UI 中明确告知用户：
- "通用聊天" - 不访问新闻数据
- "新闻助手" - 可以访问和分析新闻

## 配置状态

### ✅ 已配置
- `OPENAI_API_KEY`: 已配置（自定义 endpoint）
- `OPENAI_BASE_URL`: https://right.codes/codex/v1
- `OPENAI_MODEL`: gpt-5.2
- `TAVILY_API_KEY`: 已配置

### ⚠️ 注意
- 使用的是自定义 OpenAI endpoint
- 模型名称是 "gpt-5.2"（可能是自定义模型）
- 需要确认这个 endpoint 是否支持标准的 OpenAI API

## 总结

**问题本质：**
AI 助手的聊天功能是一个**孤立的对话机器人**，没有与用户的新闻数据集成。

**工作的功能：**
- 发现新闻源 ✅
- 增强搜索（内部+外部）✅
- 总结特定新闻 ✅
- 分类特定新闻 ✅

**不工作的功能：**
- 通用聊天（无法访问用户数据）❌

**建议：**
1. 实现 RAG 让聊天功能能访问新闻数据
2. 或者在 UI 中明确说明聊天功能的限制
3. 添加 Function Calling 让 AI 能主动查询数据
