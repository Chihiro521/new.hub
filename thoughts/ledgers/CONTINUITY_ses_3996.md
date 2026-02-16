---
session: ses_3996
updated: 2026-02-16T13:48:45.408Z
---

# Session Summary

## Goal
Implement an AI assistant feature for the News Hub project based on `docs/2026-02-16-ai-assistant-design.md`, covering 4 capability domains (AI summarization, AI classification, enhanced search, source discovery) with full backend + frontend integration, strictly following existing codebase conventions.

## Constraints & Preferences
- **User isolation is a hard constraint**: all data flows must filter by `user_id`
- **News requires `source_id`**: external search results use a "virtual source" strategy
- **Async stack**: FastAPI + Motor + AsyncElasticsearch — new code must not break the main collection pipeline
- **Existing search stays**: BM25 + vector hybrid via ES; AI layer sits above, does not replace
- **Backend conventions**: `APIRouter` with `prefix`/`tags`, `ResponseBase[T]` + `success_response()` wrapping, `Depends(get_current_user)` for auth, `loguru` for logging, class-based services, `pydantic-settings` for config, docstrings on all public functions
- **Frontend conventions**: `apiClient` (axios) with `ApiResponse<T>` typing, Pinia setup-function stores (`ref`, `computed`, async actions with `loading`/`error`), `<script setup lang="ts">`, scoped CSS using design tokens from `tokens.css`, navigation duplicated in each view's `<header class="header glass">`
- **SSE only** — no WebSocket, no sse-starlette (use FastAPI's built-in `StreamingResponse`)
- **No Jinja2 for prompts** — simple f-string compatible `{variable}` templates
- **Graceful degradation**: fall back to extractive/rule-based when LLM unavailable

## Progress
### Done
- [x] Read and analyzed the design document (`docs/2026-02-16-ai-assistant-design.md`) — 6 components identified
- [x] Explored all backend convention files: `main.py`, `config.py`, `deps.py`, `response.py`, `search.py`, `search_service.py`, `requirements.txt`, `.env`
- [x] Explored all frontend convention files: `client.ts`, `news.ts` (API + store), `search.ts` (API), `SearchView.vue`, `LoadingSkeleton.vue`, `router/index.ts`, `tokens.css`
- [x] Mapped complete directory structures for `api/v1/`, `services/`, `schemas/`, `frontend/src/api/`, `stores/`, `views/`
- [x] Researched production LLM integration patterns (AsyncOpenAI, SSE streaming, Vue EventSource, prompt management, graceful degradation) via background agent
- [x] Identified nav link patterns across all 6 views (grep results captured — each view has different nav links, no universal nav component)
- [x] **Backend config**: Added `openai_api_key`, `openai_base_url`, `openai_model`, `openai_timeout`, `openai_max_retries` to `Settings` class in `config.py` after `media_cache_max_age_hours`
- [x] **Backend .env**: Added commented-out LLM env vars (`OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL`) at end of `.env`
- [x] **Backend requirements.txt**: Added `openai>=1.0` after `httpx` line
- [x] **Backend schemas**: Created `backend/app/schemas/assistant.py` with `ChatMessage`, `ChatRequest`, `SummarizeRequest`, `ClassifyRequest`, `DiscoverSourcesRequest`, `ChatResponseData`, `SummarizeResponseData`, `ClassifyResponseData`, `SourceSuggestion`, `DiscoverSourcesResponseData`
- [x] **Backend services**: Created `backend/app/services/ai/__init__.py`, `llm_client.py` (cached singleton `get_llm_client()`), `prompts.py` (string templates: `SYSTEM_CHAT`, `SUMMARIZE_TEMPLATE`, `CLASSIFY_TEMPLATE`, `DISCOVER_SOURCES_TEMPLATE`), `assistant_service.py` (class `AssistantService` with `chat()` async generator, `summarize()`, `classify()`, `discover_sources()` — all with graceful degradation)
- [x] **Backend API route**: Created `backend/app/api/v1/assistant.py` with `POST /assistant/chat` (SSE streaming with `delta`/`done`/`error` events + non-stream fallback), `POST /assistant/summarize`, `POST /assistant/classify` (fetches user tag rules for `available_tags`), `POST /assistant/discover-sources`
- [x] **Backend main.py**: Registered `assistant_router` after `tags_router`
- [x] **Backend verification**: LSP diagnostics clean for all 7 Python files, `python -m compileall app` passed

### In Progress
- [ ] Frontend implementation not started yet (user paused before frontend agent was dispatched)

### Blocked
- (none)

## Key Decisions
- **AI orchestration layer on top of existing services**: New `services/ai/` module sits above existing `search/`, `source/`, `tagging/` services
- **Process-cached AsyncOpenAI singleton**: `@lru_cache(maxsize=1)` pattern matching existing `get_settings()`
- **Simple string templates over Jinja2**: `{variable}` placeholders in prompt constants, avoiding extra dependency
- **SSE via StreamingResponse**: `data: {"type": "delta|done|error", "content": "..."}\n\n` format with `X-Accel-Buffering: no` header
- **Non-stream fallback**: `ChatRequest.stream=False` returns `ResponseBase[ChatResponseData]` instead of SSE
- **Extractive fallback for summarization**: First 2 sentences when LLM unavailable
- **Empty tag list fallback for classification**: Returns empty `suggested_tags` when LLM unavailable
- **MongoDB user scoping**: `mongodb.db.news.find_one({"_id": ObjectId(news_id), "user_id": user_id})` pattern

## Next Steps
1. **User review of backend implementation** — user may want to inspect the created files before continuing
2. **Frontend API**: Create `frontend/src/api/assistant.ts` with `assistantApi` object (SSE fetch helper for streaming + standard axios calls for summarize/classify/discover)
3. **Frontend store**: Create `frontend/src/stores/assistant.ts` Pinia store with `messages`, `loading`, `error`, `streamingContent` state
4. **Frontend view**: Create `frontend/src/views/AssistantView.vue` — chat UI with message list, input box, streaming text display, action buttons
5. **Frontend route**: Add `/assistant` route to `router/index.ts` with `requiresAuth: true`
6. **Frontend nav links**: Add `<router-link to="/assistant" class="nav-link">AI Assistant</router-link>` to all 6 view headers
7. **Final verification**: LSP diagnostics + build checks for both backend and frontend

## Critical Context
- **Backend service pattern**: Class-based with DI, async methods, `loguru.logger` for errors, factory function at module level (e.g., `async def get_search_service()`)
- **Backend API pattern**: Inline Pydantic models or imported schemas, all endpoints return `ResponseBase[T]`, use `success_response()` helper
- **Frontend API pattern**: Export named object `xxxApi` with async methods returning `ApiResponse<T>`, use `apiClient.get/post<ApiResponse<T>>()` and return `response.data`
- **Frontend store pattern**: Pinia setup syntax with `ref()` state, `try/catch` with `result.code === 200` check, `loading.value`/`error.value` in `finally`
- **Frontend view pattern**: Header with glass effect, `bg-decoration` circles, scoped CSS using `tokens.css` custom properties
- **Nav links vary by view** (no shared component):
  - `NewsView.vue` lines 119-122: News(active), Sources, Search, Settings
  - `SourcesView.vue` lines 103-106: Home, Sources(active), Search, Settings
  - `SearchView.vue` lines 132-134: News, Sources, Settings
  - `SettingsView.vue` lines 23-26: Home, Sources, Tags, Search
  - `TagRulesView.vue` lines 140-144: Home, Sources, Tags(active), Search, Settings
  - `HomeView.vue` lines 27-28: Home(active), Sources
- **Existing routers in main.py**: `auth_router`, `sources_router`, `news_router`, `search_router`, `tags_router`, `assistant_router`
- **Existing frontend routes**: `/`, `/news`, `/sources`, `/tags`, `/search`, `/settings`, `/login`, `/register`
- **SSE format for chat endpoint**: `data: {"type": "delta", "content": "partial text"}\n\n` → `data: {"type": "done"}\n\n`
- **Frontend SSE consumption**: Use `fetch()` with `ReadableStream` reader (not `EventSource`, since POST is needed for sending messages)

## File Operations
### Read
- `E:\桌面\接口` (project root directory listing)
- `E:\桌面\接口\news-hub\docs\2026-02-16-ai-assistant-design.md` (full design doc)
- `E:\桌面\接口\news-hub\backend\app\main.py` (full)
- `E:\桌面\接口\news-hub\backend\app\core\config.py` (full)
- `E:\桌面\接口\news-hub\backend\app\core\deps.py` (full)
- `E:\桌面\接口\news-hub\backend\app\schemas\response.py` (full)
- `E:\桌面\接口\news-hub\backend\app\api\v1\search.py` (full)
- `E:\桌面\接口\news-hub\backend\app\services\search\search_service.py` (full)
- `E:\桌面\接口\news-hub\backend\requirements.txt` (full)
- `E:\桌面\接口\news-hub\backend\.env` (full)
- `E:\桌面\接口\news-hub\backend\app\api\v1` (directory listing)
- `E:\桌面\接口\news-hub\backend\app\services` (directory listing)
- `E:\桌面\接口\news-hub\backend\app\schemas` (directory listing)
- `E:\桌面\接口\news-hub\frontend\src\api\client.ts` (full)
- `E:\桌面\接口\news-hub\frontend\src\api\search.ts` (full)
- `E:\桌面\接口\news-hub\frontend\src\api\news.ts` (full)
- `E:\桌面\接口\news-hub\frontend\src\api` (directory listing)
- `E:\桌面\接口\news-hub\frontend\src\views\SearchView.vue` (full — 610 lines)
- `E:\桌面\接口\news-hub\frontend\src\views\NewsView.vue` (first 50 lines)
- `E:\桌面\接口\news-hub\frontend\src\views\SourcesView.vue` (first 50 lines)
- `E:\桌面\接口\news-hub\frontend\src\views\SettingsView.vue` (first 50 lines)
- `E:\桌面\接口\news-hub\frontend\src\views\TagRulesView.vue` (first 50 lines)
- `E:\桌面\接口\news-hub\frontend\src\views` (directory listing)
- `E:\桌面\接口\news-hub\frontend\src\stores\news.ts` (full)
- `E:\桌面\接口\news-hub\frontend\src\stores` (directory listing)
- `E:\桌面\接口\news-hub\frontend\src\router\index.ts` (full)
- `E:\桌面\接口\news-hub\frontend\src\styles\tokens.css` (full)
- `E:\桌面\接口\news-hub\frontend\src\components\LoadingSkeleton.vue` (full)

### Modified (by background agent `bg_9137107c`)
- `E:\桌面\接口\news-hub\backend\app\core\config.py` — Added 5 LLM settings fields after `media_cache_max_age_hours`
- `E:\桌面\接口\news-hub\backend\.env` — Added commented LLM env vars at end
- `E:\桌面\接口\news-hub\backend\requirements.txt` — Added `openai>=1.0` after `httpx`
- `E:\桌面\接口\news-hub\backend\app\main.py` — Added `assistant_router` import and `include_router` registration
- `E:\桌面\接口\news-hub\backend\app\schemas\assistant.py` — Created (request/response models)
- `E:\桌面\接口\news-hub\backend\app\services\ai\__init__.py` — Created (package init)
- `E:\桌面\接口\news-hub\backend\app\services\ai\llm_client.py` — Created (cached AsyncOpenAI singleton)
- `E:\桌面\接口\news-hub\backend\app\services\ai\prompts.py` — Created (4 prompt templates)
- `E:\桌面\接口\news-hub\backend\app\services\ai\assistant_service.py` — Created (AssistantService class)
- `E:\桌面\接口\news-hub\backend\app\api\v1\assistant.py` — Created (4 endpoints with SSE streaming)
