# AI Agent 自主工具调用实现方案

## 可行性分析

### ✅ 完全可行！

你想要的功能类似于我（Claude Code）的工作方式，这在技术上是**完全可以实现**的。

## 实现方案

### 1. Function Calling / Tool Use

OpenAI API（以及你使用的兼容 API）支持 Function Calling，可以让 AI 自主调用工具。

#### 架构设计

```
用户提问
    ↓
AI 分析需求
    ↓
AI 决定调用哪些工具
    ↓
系统执行工具调用
    ↓
AI 分析结果
    ↓
返回答案给用户
```

### 2. 可以实现的工具

#### A. 数据获取工具

```python
tools = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "搜索网络获取最新信息",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词"},
                    "max_results": {"type": "integer", "default": 5}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_rss",
            "description": "抓取 RSS 源的最新文章",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "RSS 源 URL"},
                    "limit": {"type": "integer", "default": 10}
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "scrape_webpage",
            "description": "抓取网页内容",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "网页 URL"}
                },
                "required": ["url"]
            }
        }
    }
]
```

#### B. 数据库操作工具

```python
{
    "type": "function",
    "function": {
        "name": "search_user_news",
        "description": "搜索用户的新闻库",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "default": 10}
            }
        }
    }
},
{
    "type": "function",
    "function": {
        "name": "get_recent_news",
        "description": "获取用户最近的新闻",
        "parameters": {
            "type": "object",
            "properties": {
                "hours": {"type": "integer", "default": 24},
                "limit": {"type": "integer", "default": 20}
            }
        }
    }
},
{
    "type": "function",
    "function": {
        "name": "save_news",
        "description": "保存新闻到用户库",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "url": {"type": "string"},
                "content": {"type": "string"},
                "source": {"type": "string"}
            },
            "required": ["title", "url"]
        }
    }
}
```

#### C. 代码操作工具（高级）

```python
{
    "type": "function",
    "function": {
        "name": "read_file",
        "description": "读取项目文件",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string"}
            },
            "required": ["file_path"]
        }
    }
},
{
    "type": "function",
    "function": {
        "name": "edit_file",
        "description": "修改项目文件",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string"},
                "old_content": {"type": "string"},
                "new_content": {"type": "string"}
            },
            "required": ["file_path", "old_content", "new_content"]
        }
    }
},
{
    "type": "function",
    "function": {
        "name": "execute_python",
        "description": "执行 Python 代码",
        "parameters": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "要执行的 Python 代码"}
            },
            "required": ["code"]
        }
    }
}
```

### 3. 实现示例

#### 基础版：AI Agent with Tools

```python
class AgentAssistant:
    def __init__(self):
        self.client = get_llm_client()
        self.tools = self._define_tools()
        self.tool_handlers = self._register_handlers()

    def _define_tools(self):
        return [
            {
                "type": "function",
                "function": {
                    "name": "web_search",
                    "description": "搜索网络获取最新信息",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string"}
                        },
                        "required": ["query"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "search_user_news",
                    "description": "搜索用户的新闻库",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string"}
                        },
                        "required": ["query"]
                    }
                }
            }
        ]

    def _register_handlers(self):
        return {
            "web_search": self._handle_web_search,
            "search_user_news": self._handle_search_user_news,
        }

    async def _handle_web_search(self, query: str):
        """执行网络搜索"""
        from app.services.ai.web_search import WebSearchClient
        client = WebSearchClient()
        results = await client.search(query, max_results=5)
        return {
            "results": results,
            "count": len(results)
        }

    async def _handle_search_user_news(self, query: str, user_id: str):
        """搜索用户新闻"""
        from app.services.search import SearchService
        from app.db.es import es_client

        service = SearchService(es_client.client)
        response = await service.search(
            user_id=user_id,
            query=query,
            search_type="hybrid",
            page_size=10
        )
        return {
            "results": [
                {"title": r.title, "url": r.url, "description": r.description}
                for r in response.results
            ],
            "total": response.total
        }

    async def chat_with_tools(
        self,
        messages: List[dict],
        user_id: str,
        max_iterations: int = 5
    ):
        """支持工具调用的聊天"""
        conversation = messages.copy()

        for iteration in range(max_iterations):
            # 调用 LLM
            response = await self.client.chat.completions.create(
                model=settings.openai_model,
                messages=conversation,
                tools=self.tools,
                tool_choice="auto"  # 让 AI 自己决定是否调用工具
            )

            message = response.choices[0].message

            # 如果 AI 不需要调用工具，直接返回
            if not message.tool_calls:
                return message.content

            # AI 决定调用工具
            conversation.append(message)

            # 执行所有工具调用
            for tool_call in message.tool_calls:
                function_name = tool_call.function.name
                function_args = json.loads(tool_call.function.arguments)

                # 执行工具
                handler = self.tool_handlers.get(function_name)
                if handler:
                    result = await handler(**function_args, user_id=user_id)
                else:
                    result = {"error": f"Unknown tool: {function_name}"}

                # 将工具结果添加到对话
                conversation.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(result, ensure_ascii=False)
                })

        # 达到最大迭代次数
        return "抱歉，处理超时。"
```

### 4. 使用场景示例

#### 场景 1：动态搜索新闻

```
用户: "帮我找一下最新的 AI 新闻"

AI 思考: 用户想要最新的 AI 新闻，我应该：
1. 先搜索用户的新闻库
2. 如果不够新，再搜索网络

AI 调用: search_user_news(query="AI", limit=5)
系统返回: [3 条用户库中的 AI 新闻]

AI 调用: web_search(query="AI news 2026")
系统返回: [5 条最新的网络搜索结果]

AI 回复: "我找到了 8 条 AI 相关新闻：
- 用户库中有 3 条
- 网络上找到 5 条最新的
[列出新闻列表]
需要我保存这些新闻到你的库吗？"
```

#### 场景 2：自动抓取和保存

```
用户: "帮我订阅 TechCrunch 的最新文章"

AI 思考: 用户想订阅 TechCrunch，我需要：
1. 找到 TechCrunch 的 RSS 源
2. 抓取最新文章
3. 保存到用户库

AI 调用: web_search(query="TechCrunch RSS feed")
系统返回: [找到 RSS URL]

AI 调用: fetch_rss(url="https://techcrunch.com/feed/")
系统返回: [10 篇最新文章]

AI 调用: save_news(title="...", url="...", ...)  # 循环保存
系统返回: [保存成功]

AI 回复: "已成功订阅 TechCrunch！
- 抓取了 10 篇最新文章
- 已保存到你的新闻库
- 设置了自动更新"
```

#### 场景 3：代码修改（高级）

```
用户: "帮我在搜索页面添加一个导出功能"

AI 思考: 需要修改前端代码，我应该：
1. 读取搜索页面的代码
2. 分析代码结构
3. 添加导出功能
4. 修改代码

AI 调用: read_file(file_path="frontend/src/views/SearchView.vue")
系统返回: [文件内容]

AI 分析: 需要添加导出按钮和导出函数

AI 调用: edit_file(
    file_path="frontend/src/views/SearchView.vue",
    old_content="<button @click=\"handleSearch\">搜索</button>",
    new_content="<button @click=\"handleSearch\">搜索</button>\n<button @click=\"handleExport\">导出</button>"
)
系统返回: [修改成功]

AI 回复: "已添加导出功能！
- 在搜索栏旁边添加了导出按钮
- 实现了 CSV 导出功能
- 可以导出当前搜索结果"
```

### 5. 安全考虑

#### ⚠️ 重要的安全措施

1. **权限控制**
   - 代码修改需要用户明确授权
   - 文件操作限制在项目目录内
   - 不允许执行危险命令

2. **沙箱执行**
   - Python 代码在隔离环境中执行
   - 限制资源使用（CPU、内存、时间）
   - 禁止访问敏感文件

3. **审计日志**
   - 记录所有工具调用
   - 记录代码修改历史
   - 可以回滚操作

4. **用户确认**
   - 重要操作前询问用户
   - 显示将要执行的操作
   - 提供预览功能

### 6. 实现难度评估

| 功能 | 难度 | 时间估计 |
|------|------|----------|
| 基础 Function Calling | ⭐⭐ | 2-3 天 |
| 网络搜索工具 | ⭐ | 已实现 |
| 数据库操作工具 | ⭐ | 1 天 |
| RSS 抓取工具 | ⭐⭐ | 1-2 天 |
| 网页抓取工具 | ⭐⭐⭐ | 2-3 天 |
| 代码读取工具 | ⭐⭐ | 1 天 |
| 代码修改工具 | ⭐⭐⭐⭐ | 3-5 天 |
| 代码执行工具 | ⭐⭐⭐⭐⭐ | 5-7 天 |

### 7. 推荐实现路径

#### 阶段 1：基础工具（1 周）
- ✅ 实现 Function Calling 框架
- ✅ 添加网络搜索工具（已有）
- ✅ 添加用户新闻搜索工具
- ✅ 添加 RSS 抓取工具

#### 阶段 2：数据操作（1 周）
- ✅ 添加保存新闻工具
- ✅ 添加更新新闻工具
- ✅ 添加删除新闻工具
- ✅ 添加标签管理工具

#### 阶段 3：高级功能（2-3 周）
- ⚠️ 添加网页抓取工具
- ⚠️ 添加代码读取工具
- ⚠️ 添加代码修改工具（需要严格权限控制）

## 技术栈

### 需要的库

```python
# Function Calling
openai>=1.0.0  # 已有

# 网页抓取
beautifulsoup4
playwright  # 或 selenium

# RSS 解析
feedparser

# 代码分析
ast  # Python 内置
tree-sitter  # 可选，用于多语言支持

# 沙箱执行
RestrictedPython  # 安全的 Python 执行
docker-py  # 容器隔离
```

## 总结

**可以做！** 而且技术上完全可行。

**核心优势：**
1. 不依赖固定新闻源，AI 自己决定去哪里找数据
2. 可以动态抓取网络内容
3. 可以自动保存和管理新闻
4. 甚至可以修改项目代码（需要严格权限控制）

**类似的开源项目：**
- LangChain - Agent 框架
- AutoGPT - 自主 AI Agent
- BabyAGI - 任务驱动的 AI
- OpenInterpreter - 代码执行 Agent

**建议：**
从阶段 1 开始，先实现基础的工具调用，让 AI 能自主搜索和保存新闻。这样就能解决"不依赖固定新闻源"的问题。
