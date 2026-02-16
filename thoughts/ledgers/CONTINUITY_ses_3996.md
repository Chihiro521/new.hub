---
session: ses_3996
updated: 2026-02-16T16:30:46.065Z
---

# Session Summary

## Goal
Implement the remaining 3 components (Quality & Governance, Virtual Source Manager, Search Augmentation Engine) of the News Hub AI Assistant feature, following the design doc at `docs/2026-02-16-ai-assistant-design.md`. The first 3 components (Summary, Classification, Source Discovery + full chat UI) were completed in a prior session.

## Constraints & Preferences
- **User isolation is a hard constraint**: all data flows filter by `user_id`
- **News requires `source_id`**: external search results use a "virtual source" strategy
- **Async stack**: FastAPI + Motor + AsyncElasticsearch — new code must not break the main collection pipeline
- **Existing search stays**: BM25 + vector hybrid via ES; AI layer sits above, does not replace
- **Backend conventions**: `APIRouter` with `prefix`/`tags`, `ResponseBase[T]` + `success_response()`, `Depends(get_current_user)`, `loguru` logging, class-based services, `pydantic-settings` config, docstrings on all public functions
- **Frontend conventions**: `apiClient` (axios) with `ApiResponse<T>`, Pinia setup-function stores (`ref`, `computed`, async actions), `<script setup lang="ts">`, scoped CSS using `tokens.css` design tokens, nav duplicated in each view header (no shared component)
- **SSE only** — no WebSocket, no sse-starlette (use FastAPI `StreamingResponse`)
- **No Jinja2 for prompts** — simple `{variable}` f-string templates
- **Graceful degradation**: fall back to extractive/rule-based when LLM unavailable
- **Implementation order**: Component 6 → 5 → 3 (agreed upon with user)

## Progress
### Done
- [x] **Phase 1 (prior session)** — Components 1 (Summary), 2 (Classification), 4 (Source Discovery) fully implemented:
  - Backend: `services/ai/` (`llm_client.py`, `prompts.py`, `assistant_service.py` with `chat()`, `summarize()`, `classify()`, `discover_sources()`), `api/v1/assistant.py` (4 endpoints), `schemas/assistant.py`, config additions in `config.py` + `.env`, `openai>=1.0` in `requirements.txt`
  - Frontend: `api/assistant.ts` (SSE via fetch), `stores/assistant.ts` (Pinia), `views/AssistantView.vue` (509 lines), route + nav links in all 7 views
  - Both `python -m compileall` and `vite build` pass
- [x] **Phase 2 planning** — Analyzed all 3 remaining components, identified exact files to create/modify, designed data flows, chose Tavily as external search API
- [x] **Codebase analysis for Phase 2**: Read source model (`SourceType` enum: `rss`/`api`/`html`), collector factory (`_collectors` dict), `CollectedItem` dataclass, `NewsPipeline.process()`, `SearchService._hybrid_search()` (BM25 boost 1.0 + semantic boost 2.0 via `script_score`), per-user ES indices (`news_hub_news_{user_id}`), `NewsItemInDB` schema (requires `source_id`, `source_name`, `source_type`)
- [x] **TODO list created** — 12 tasks across 3 components

### In Progress
- [ ] Component 6 (Quality & Governance) — about to start implementation

### Blocked
- (none)

## Key Decisions
- **Implementation order `6 → 5 → 3`**: Component 6 (audit) is independent; Component 5 (virtual source) is independent but Component 3 depends on it; Component 3 (augmented search) depends on both
- **Tavily for external search**: Best balance of free tier (1000 req/month), Chinese content quality, and async compatibility (httpx). Only 1 new env var: `TAVILY_API_KEY`
- **RRF (Reciprocal Rank Fusion) for score merging**: Internal ES scores and external Tavily scores are on different scales — RRF uses rank positions only, avoiding score normalization issues
- **Virtual sources are auto-created per user+provider**: No manual setup; system creates `source_type: "virtual"` docs as needed; virtual sources skip scheduled collection
- **Audit logs are non-blocking**: `AuditLogger.log()` catches all exceptions and only warns, never raises — main AI features are never blocked by audit failures
- **External results default to "cache first, persist on user action"**: Augmented search results marked `is_persisted: false` until user explicitly saves them
- **MongoDB collection `ai_audit_logs`**: Stores action, input/output summaries, model, latency, token usage, user feedback, fallback status

## Next Steps
1. **Component 6 — Quality & Governance**:
   - Create `backend/app/schemas/audit.py` — `AuditLogCreate`, `AuditLogInDB`, `AuditLogResponse`, `AuditFeedback`
   - Create `backend/app/services/ai/audit.py` — `AuditLogger` class with `log()`, `get_logs()`, `record_feedback()`
   - Modify `backend/app/services/ai/assistant_service.py` — integrate audit logging into `chat()`, `summarize()`, `classify()`, `discover_sources()`
   - Modify `backend/app/api/v1/assistant.py` — add `GET /assistant/audit-logs` and `POST /assistant/audit-logs/{log_id}/feedback`
2. **Component 5 — Virtual Source Manager**:
   - Modify `backend/app/schemas/source.py` — add `VIRTUAL = "virtual"` to `SourceType` enum
   - Create `backend/app/services/ai/virtual_source.py` — `VirtualSourceManager` with `get_or_create_virtual_source()` and `ingest_results()`
   - Modify scheduler/pipeline to skip `source_type == "virtual"` from collection
3. **Component 3 — Search Augmentation Engine**:
   - Modify `backend/app/core/config.py` + `backend/.env` — add `tavily_api_key`
   - Create `backend/app/services/ai/web_search.py` — async Tavily client via httpx
   - Modify `backend/app/services/ai/assistant_service.py` — add `augmented_search()` (LLM intent parsing → parallel internal+external search → RRF fusion → LLM summary)
   - Modify `backend/app/schemas/assistant.py` + `backend/app/api/v1/assistant.py` — add `POST /assistant/search`
4. **Verify** — `python -m compileall` + `vite build`

## Critical Context
- **Existing `SourceType` enum** (`backend/app/schemas/source.py` line 14-19): `RSS = "rss"`, `API = "api"`, `HTML = "html"` — needs `VIRTUAL = "virtual"` added
- **`CollectorFactory._collectors` dict** (`backend/app/services/collector/factory.py` line 23-27): maps `"rss"` → `RSSCollector`, `"api"` → `APICollector`, `"html"` is commented out — virtual sources should NOT be registered here
- **`NewsItemInDB` required fields** (`backend/app/schemas/news.py`): `source_id: str`, `source_name: str`, `source_type: str`, `user_id: str` — virtual source must provide all of these
- **`NewsPipeline.process()`** (`backend/app/services/pipeline/processor.py` line 39): takes `source_doc` + `CollectionResult` → dedup by URL → tag → insert_many → ES index — virtual source ingestion can reuse storage logic but skip collection
- **Hybrid search weights** (`search_service.py`): BM25 boost `1.0`, semantic `script_score` boost `2.0` via `cosineSimilarity + 1.0`, per-user index `news_hub_news_{user_id}`
- **`AssistantService` constructor** (`services/ai/assistant_service.py` line 30-31): `self.client = get_llm_client()` — audit logger should be added here
- **Existing assistant endpoints** (`api/v1/assistant.py`): `POST /chat`, `POST /summarize`, `POST /classify`, `POST /discover-sources` — all use `Depends(get_current_user)`
- **5 LLM config fields** in `config.py` lines 96-100: `openai_api_key`, `openai_base_url` (`https://api.openai.com/v1`), `openai_model` (`gpt-4o-mini`), `openai_timeout` (60), `openai_max_retries` (2)
- **Audit log MongoDB schema** (designed):
  ```
  { user_id, action, input, output, model, latency_ms, token_usage: {prompt, completion},
    quality_signals: {user_feedback, fallback_used, error}, created_at }
  ```
- **`vue-tsc` has 4 pre-existing errors** in `vite.config.ts`/`tsconfig.json` — unrelated to our changes, `vite build` works fine

## File Operations
### Read
- `E:\桌面\接口` (project root listing)
- `E:\桌面\接口\news-hub\docs\2026-02-16-ai-assistant-design.md` (full, 174 lines — all 6 components + data flows)
- `E:\桌面\接口\news-hub\backend\app\core\config.py` (lines 90-109 — LLM config fields)
- `E:\桌面\接口\news-hub\backend\.env` (full — LLM env vars at lines 40-43, all commented out)
- `E:\桌面\接口\news-hub\backend\app\schemas\source.py` (full, 173 lines — `SourceType` enum, `SourceCreate`, `SourceInDB`, `ParserConfig`)
- `E:\桌面\接口\news-hub\backend\app\schemas\news.py` (full, 142 lines — `NewsItemInDB` with `source_id`, `source_name`, `source_type`, `embedding`)
- `E:\桌面\接口\news-hub\backend\app\services\ai\assistant_service.py` (full, 199 lines — 4 methods + helpers)
- `E:\桌面\接口\news-hub\backend\app\services\collector\factory.py` (full, 75 lines — `_collectors` dict)
- `E:\桌面\接口\news-hub\backend\app\services\collector\base.py` (full, 151 lines — `CollectedItem`, `CollectionResult`, `BaseCollector`)
- `E:\桌面\接口\news-hub\backend\app\services\pipeline\processor.py` (lines 1-60 — `NewsPipeline.process()` signature)
- `E:\桌面\接口\news-hub\backend\app\api\v1\search.py` (structure — 4 endpoints: search, suggest, status, reindex)
- `E:\桌面\接口\news-hub\backend\app\services\search\search_service.py` (structure — `SearchService` with `search()`, `_keyword_search()`, `_semantic_search()`, `_hybrid_search()`, `suggest()`)
- `E:\桌面\接口\news-hub\frontend\src\views\AssistantView.vue` (509 lines — chat UI)
- `E:\桌面\接口\news-hub\frontend\src\views\SearchView.vue` (structure)
- `E:\桌面\接口\news-hub\frontend\src\views\SettingsView.vue` (full, 240 lines)

### Modified
- (none yet in this session — all modifications were from the prior session)
