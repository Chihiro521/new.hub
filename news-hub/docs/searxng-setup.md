# SearXNG Docker Setup

## 1) Start SearXNG

```bash
cd news-hub
docker compose -f docker-compose.searxng.yml up -d
```

Default endpoint:

- Search API: `http://localhost:8080/search`
- Config API: `http://localhost:8080/config`

## 2) Backend Environment

Update `backend/.env`:

```env
SEARXNG_BASE_URL=http://localhost:8080
EXTERNAL_SEARCH_DEFAULT_PROVIDER=auto
EXTERNAL_SEARCH_FALLBACK_PROVIDER=tavily
EXTERNAL_SEARCH_TIMEOUT=15
```

Optional Tavily fallback:

```env
TAVILY_API_KEY=your-tavily-key
```

## 3) Health Check

```bash
curl "http://localhost:8080/search?q=OpenAI&format=json"
```

Then call backend options endpoint:

```bash
curl "http://localhost:8000/api/v1/assistant/external-search/options"
```

Runtime health endpoint:

```bash
curl "http://localhost:8000/api/v1/assistant/external-search/status"
```

## 3.1 Ingestion Governance (Optional)

You can tune ingestion reliability/throttling in `backend/.env`:

```env
EXTERNAL_INGEST_MAX_CONCURRENCY=4
EXTERNAL_INGEST_RETRY_ATTEMPTS=2
EXTERNAL_INGEST_RETRY_BACKOFF_SECONDS=0.75
EXTERNAL_INGEST_DOMAIN_INTERVAL_SECONDS=0.5
EXTERNAL_INGEST_MIN_QUALITY_SCORE=0.15
```

## 4) Stop

```bash
docker compose -f docker-compose.searxng.yml down
```
