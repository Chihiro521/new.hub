# Progress Report #004 - Slice 3 Complete: Collection Pipeline

## Date: 2026-01-25

## Summary

Completed Slice 3 (Collection Pipeline) - full news collection system with RSS/API fetchers, processing pipeline, background scheduler, and news viewing UI.

---

## Completed Work

### Backend

| Component | Status | Location |
|-----------|--------|----------|
| Base Collector Interface | Done | `backend/app/services/collector/base.py` |
| RSS Collector | Done | `backend/app/services/collector/rss_collector.py` |
| API Collector | Done | `backend/app/services/collector/api_collector.py` |
| Collector Factory | Done | `backend/app/services/collector/factory.py` |
| News Pipeline | Done | `backend/app/services/pipeline/processor.py` |
| Task Scheduler | Done | `backend/app/services/scheduler.py` |
| News API | Done | `backend/app/api/v1/news.py` |

#### News API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/news` | List news with filters |
| GET | `/api/v1/news/count` | Get news count |
| GET | `/api/v1/news/stats` | Get stats (total/unread/starred) |
| GET | `/api/v1/news/{id}` | Get single news item |
| PATCH | `/api/v1/news/{id}` | Update read/starred state |
| POST | `/api/v1/news/mark-all-read` | Mark all as read |
| DELETE | `/api/v1/news/{id}` | Delete news item |

#### Collector Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     CollectorFactory                        │
│                          │                                  │
│        ┌─────────────────┼─────────────────┐               │
│        ▼                 ▼                 ▼               │
│  RSSCollector     APICollector      (HTMLCollector)        │
│        │                 │              (future)           │
│        └────────────┬────┘                                 │
│                     ▼                                      │
│             CollectionResult                               │
│          (success, items, error)                           │
└─────────────────────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│                    NewsPipeline                             │
│  - Deduplicate by URL                                       │
│  - Store to MongoDB                                         │
│  - Update source stats                                      │
└─────────────────────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│                   TaskScheduler                             │
│  - APScheduler AsyncIO                                      │
│  - Every 5 min: collect due sources                         │
│  - Manual trigger via API                                   │
└─────────────────────────────────────────────────────────────┘
```

### Frontend

| Component | Status | Location |
|-----------|--------|----------|
| News API Client | Done | `frontend/src/api/news.ts` |
| News Store (Pinia) | Done | `frontend/src/stores/news.ts` |
| News List View | Done | `frontend/src/views/NewsView.vue` |
| Router Update | Done | `frontend/src/router/index.ts` |

---

## User Flow

1. User adds a news source (Slice 2)
2. User clicks "Refresh" on source card
3. Backend fetches RSS/API, deduplicates, stores news
4. User navigates to News page (home)
5. Sees list of collected articles with filters
6. Can mark as read, star, filter by source
7. Background scheduler auto-refreshes sources every 5 minutes

---

## Collection Types

| Type | Collector | Status |
|------|-----------|--------|
| RSS/Atom | RSSCollector | Implemented |
| JSON API | APICollector | Implemented |
| HTML/Scrapy | HTMLCollector | Slice 7 (future) |

---

## Files Created/Modified

### Backend (New)
```
backend/app/services/collector/base.py           # Base collector interface
backend/app/services/collector/rss_collector.py  # RSS/Atom fetcher
backend/app/services/collector/api_collector.py  # JSON API fetcher
backend/app/services/collector/factory.py        # Collector factory
backend/app/services/collector/__init__.py       # Package exports
backend/app/services/pipeline/processor.py       # News pipeline
backend/app/services/pipeline/__init__.py        # Package exports
backend/app/services/scheduler.py                # APScheduler service
backend/app/api/v1/news.py                       # News API endpoints
```

### Backend (Modified)
```
backend/app/main.py                              # Added scheduler + news router
backend/app/api/v1/sources.py                    # Refresh now triggers collection
backend/app/db/mongo.py                          # Added client property + get_database
backend/requirements-core.txt                    # Added feedparser, bs4, APScheduler
```

### Frontend (New)
```
frontend/src/api/news.ts                         # News API client
frontend/src/stores/news.ts                      # News Pinia store
frontend/src/views/NewsView.vue                  # News list page
```

### Frontend (Modified)
```
frontend/src/api/index.ts                        # Export news API
frontend/src/stores/index.ts                     # Export news store
frontend/src/router/index.ts                     # Added /news route, home -> NewsView
```

---

## UI Features

### News List Page
- Stats bar (total, unread, starred)
- Filters: source, read status, starred
- News cards with:
  - Thumbnail image
  - Source badge
  - Title (truncated)
  - Description (truncated)
  - Published date (relative)
  - Tags
  - Star button
- Click to open original article
- Infinite scroll / Load more
- Mark all as read

### Design
- Consistent glassmorphism style
- Pink/purple gradient accents
- Floating background circles
- Responsive layout

---

## Dependencies Added

```
feedparser==6.0.11      # RSS/Atom parsing
beautifulsoup4==4.12.3  # HTML parsing
lxml==5.3.0             # Fast XML/HTML parser
APScheduler==3.10.4     # Background task scheduler
```

---

## Next Steps (Slice 4: Search System)

1. Backend:
   - Elasticsearch index per user
   - Keyword search API
   - Vector embedding with Sentence-Transformers
   - Semantic search API
   - Auto-complete suggestions

2. Frontend:
   - Search bar component
   - Search results page
   - Search filters

---

## Known Limitations

1. **HTML sources**: Not yet implemented (requires Scrapy integration)
2. **Pagination**: API only returns up to 100 items per request
3. **Image proxy**: Not implemented (direct URLs may fail CORS)
4. **Error recovery**: Failed sources retry on next scheduler cycle

---

## API Examples

### List News
```bash
curl http://localhost:8000/api/v1/news \
  -H "Authorization: Bearer $TOKEN"
```

### Refresh Source and Collect
```bash
curl -X POST http://localhost:8000/api/v1/sources/{source_id}/refresh \
  -H "Authorization: Bearer $TOKEN"
```

### Mark as Read
```bash
curl -X PATCH http://localhost:8000/api/v1/news/{news_id} \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"is_read": true}'
```

### Toggle Star
```bash
curl -X PATCH http://localhost:8000/api/v1/news/{news_id} \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"is_starred": true}'
```
