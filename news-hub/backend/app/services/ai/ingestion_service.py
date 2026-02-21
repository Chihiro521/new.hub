"""Session and ingestion workflow for external search results."""

from __future__ import annotations

import asyncio
import time
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from bson import ObjectId
from loguru import logger

from app.core.config import settings
from app.db.mongo import mongodb
from app.services.ai.virtual_source import VirtualSourceManager
from app.services.collector.webpage_extractor import WebpageExtractor


class ExternalIngestionService:
    """Manages external-search sessions and async ingestion jobs."""

    def __init__(self):
        self.extractor = WebpageExtractor()
        self._semaphore = asyncio.Semaphore(
            max(1, settings.external_ingest_max_concurrency)
        )
        self._domain_registry_lock = asyncio.Lock()
        self._domain_locks: Dict[str, asyncio.Lock] = {}
        self._domain_last_request_at: Dict[str, float] = {}

    async def create_search_session(
        self,
        user_id: str,
        query: str,
        provider_used: str,
        results: List[Dict[str, Any]],
    ) -> str:
        now = datetime.utcnow()
        doc = {
            "user_id": user_id,
            "query": query,
            "provider_used": provider_used,
            "results": results,
            "created_at": now,
            "updated_at": now,
        }
        result = await mongodb.db.external_search_sessions.insert_one(doc)
        return str(result.inserted_id)

    async def queue_ingest_job(
        self,
        user_id: str,
        session_id: str,
        selected_urls: Optional[List[str]] = None,
        persist_mode: str = "enriched",
    ) -> Dict[str, Any]:
        session = await self._get_session(user_id, session_id)
        if not session:
            raise ValueError("Search session not found")

        session_results = session.get("results", [])
        selected = self._select_results(session_results, selected_urls)
        if not selected:
            raise ValueError("No selectable results found")

        now = datetime.utcnow()
        job_doc = {
            "user_id": user_id,
            "session_id": session_id,
            "provider": session.get("provider_used", "external"),
            "status": "queued",
            "persist_mode": persist_mode,
            "total_items": len(selected),
            "processed_items": 0,
            "stored_items": 0,
            "failed_items": 0,
            "retry_count": 0,
            "average_quality_score": 0.0,
            "failed_urls": [],
            "error_message": None,
            "selected_results": selected,
            "created_at": now,
            "updated_at": now,
        }
        result = await mongodb.db.ingest_jobs.insert_one(job_doc)
        job_id = str(result.inserted_id)
        asyncio.create_task(self._run_ingest_job(job_id))

        return {
            "job_id": job_id,
            "status": "queued",
            "queued_count": len(selected),
            "persist_mode": persist_mode,
        }

    async def get_ingest_job(self, user_id: str, job_id: str) -> Optional[Dict[str, Any]]:
        try:
            oid = ObjectId(job_id)
        except Exception:
            return None
        return await mongodb.db.ingest_jobs.find_one({"_id": oid, "user_id": user_id})

    async def _get_session(self, user_id: str, session_id: str) -> Optional[Dict[str, Any]]:
        try:
            oid = ObjectId(session_id)
        except Exception:
            return None
        return await mongodb.db.external_search_sessions.find_one(
            {"_id": oid, "user_id": user_id}
        )

    def _select_results(
        self, results: List[Dict[str, Any]], selected_urls: Optional[List[str]]
    ) -> List[Dict[str, Any]]:
        if not selected_urls:
            return results
        selected_set = {url.strip() for url in selected_urls if url and url.strip()}
        return [item for item in results if item.get("url") in selected_set]

    async def _run_ingest_job(self, job_id: str) -> None:
        try:
            oid = ObjectId(job_id)
        except Exception:
            return

        job = await mongodb.db.ingest_jobs.find_one({"_id": oid})
        if not job:
            return

        now = datetime.utcnow()
        await mongodb.db.ingest_jobs.update_one(
            {"_id": oid},
            {"$set": {"status": "running", "updated_at": now}},
        )

        provider = str(job.get("provider") or "external")
        persist_mode = str(job.get("persist_mode") or "enriched")
        results = job.get("selected_results", [])

        processed = 0
        stored = 0
        failed = 0
        retry_count = 0
        quality_sum = 0.0
        quality_count = 0
        failed_urls: List[str] = []

        try:
            if persist_mode == "enriched" and len(results) > 1:
                # Use batch crawling for efficiency
                urls = [str(item.get("url") or "") for item in results]
                url_to_item = {str(item.get("url") or ""): item for item in results}

                batch_results = await self.extractor.batch_extract(
                    [u for u in urls if u]
                )
                url_to_enriched = {url: data for url, data in batch_results}

                for item in results:
                    url = str(item.get("url") or "")
                    enriched = url_to_enriched.get(url, {})
                    ingest_item = item.copy()

                    if enriched:
                        ingest_item.update(
                            {
                                "title": enriched.get("title") or ingest_item.get("title"),
                                "description": enriched.get("description")
                                or ingest_item.get("description", ""),
                                "content": enriched.get("content")
                                or ingest_item.get("content", ""),
                                "image_url": enriched.get("image_url")
                                or ingest_item.get("image_url"),
                                "author": enriched.get("author")
                                or ingest_item.get("author"),
                                "published_at": enriched.get("published_at")
                                or ingest_item.get("published_at"),
                            }
                        )
                        meta = ingest_item.setdefault("metadata", {})
                        meta["canonical_url"] = enriched.get("canonical_url")
                        meta["url_hash"] = enriched.get("url_hash")
                        qs = float(enriched.get("quality_score") or 0.0)
                        meta["quality_score"] = qs
                        quality_sum += qs
                        quality_count += 1
                    else:
                        failed += 1
                        if url and len(failed_urls) < 100:
                            failed_urls.append(url)
                        processed += 1
                        continue

                    try:
                        inserted = await VirtualSourceManager.ingest_results(
                            user_id=job["user_id"],
                            provider=provider,
                            items=[ingest_item],
                        )
                        stored += int(inserted)
                    except Exception as e:
                        logger.warning(f"Ingest item failed ({url}): {e}")
                        failed += 1
                        if url and len(failed_urls) < 100:
                            failed_urls.append(url)

                    processed += 1
                    avg_quality_score = (
                        round(quality_sum / quality_count, 3) if quality_count > 0 else 0.0
                    )
                    await mongodb.db.ingest_jobs.update_one(
                        {"_id": oid},
                        {
                            "$set": {
                                "processed_items": processed,
                                "stored_items": stored,
                                "failed_items": failed,
                                "retry_count": retry_count,
                                "average_quality_score": avg_quality_score,
                                "failed_urls": failed_urls,
                                "updated_at": datetime.utcnow(),
                            }
                        },
                    )
            else:
                # Original per-item processing (snippet mode or single item)
                tasks = [
                    asyncio.create_task(
                        self._process_single_item(
                            user_id=job["user_id"],
                            provider=provider,
                            persist_mode=persist_mode,
                            item=item,
                        )
                    )
                    for item in results
                ]

                for task in asyncio.as_completed(tasks):
                    try:
                        item_result = await task
                    except Exception as e:
                        logger.warning(f"Ingest worker task failed: {e}")
                        item_result = {
                            "stored": 0,
                            "failed": 1,
                            "retry_count": 0,
                            "quality_score": None,
                            "failed_url": None,
                        }

                    processed += 1
                    stored += int(item_result.get("stored", 0))
                    failed += int(item_result.get("failed", 0))
                    retry_count += int(item_result.get("retry_count", 0))

                    quality_score = item_result.get("quality_score")
                    if quality_score is not None:
                        quality_sum += float(quality_score)
                        quality_count += 1

                    failed_url = item_result.get("failed_url")
                    if failed_url and len(failed_urls) < 100:
                        failed_urls.append(str(failed_url))

                    avg_quality_score = (
                        round(quality_sum / quality_count, 3) if quality_count > 0 else 0.0
                    )
                    await mongodb.db.ingest_jobs.update_one(
                        {"_id": oid},
                        {
                            "$set": {
                                "processed_items": processed,
                                "stored_items": stored,
                                "failed_items": failed,
                                "retry_count": retry_count,
                                "average_quality_score": avg_quality_score,
                                "failed_urls": failed_urls,
                                "updated_at": datetime.utcnow(),
                            }
                        },
                    )

            avg_quality_score = (
                round(quality_sum / quality_count, 3) if quality_count > 0 else 0.0
            )

            await mongodb.db.ingest_jobs.update_one(
                {"_id": oid},
                {
                    "$set": {
                        "status": "completed",
                        "processed_items": processed,
                        "stored_items": stored,
                        "failed_items": failed,
                        "retry_count": retry_count,
                        "average_quality_score": avg_quality_score,
                        "failed_urls": failed_urls,
                        "updated_at": datetime.utcnow(),
                    }
                },
            )
        except Exception as e:
            logger.error(f"Ingest job failed ({job_id}): {e}")
            await mongodb.db.ingest_jobs.update_one(
                {"_id": oid},
                {
                    "$set": {
                        "status": "failed",
                        "error_message": str(e),
                        "processed_items": processed,
                        "stored_items": stored,
                        "failed_items": failed,
                        "retry_count": retry_count,
                        "average_quality_score": (
                            round(quality_sum / quality_count, 3)
                            if quality_count > 0
                            else 0.0
                        ),
                        "failed_urls": failed_urls,
                        "updated_at": datetime.utcnow(),
                    }
                },
            )

    async def _process_single_item(
        self,
        user_id: str,
        provider: str,
        persist_mode: str,
        item: Dict[str, Any],
    ) -> Dict[str, Any]:
        async with self._semaphore:
            ingest_item = item.copy()
            retry_count = 0
            quality_score: Optional[float] = None
            url = str(item.get("url") or "")

            try:
                if persist_mode == "enriched":
                    enriched, retry_count = await self._extract_with_retry(url)
                    if enriched:
                        ingest_item.update(
                            {
                                "title": enriched.get("title") or ingest_item.get("title"),
                                "description": enriched.get("description")
                                or ingest_item.get("description", ""),
                                "content": enriched.get("content")
                                or ingest_item.get("content", ""),
                                "image_url": enriched.get("image_url")
                                or ingest_item.get("image_url"),
                                "author": enriched.get("author")
                                or ingest_item.get("author"),
                                "published_at": enriched.get("published_at")
                                or ingest_item.get("published_at"),
                            }
                        )
                        meta = ingest_item.setdefault("metadata", {})
                        meta["canonical_url"] = enriched.get("canonical_url")
                        meta["url_hash"] = enriched.get("url_hash")
                        quality_score = float(enriched.get("quality_score") or 0.0)
                        meta["quality_score"] = quality_score
                    else:
                        quality_score = 0.0

                inserted = await VirtualSourceManager.ingest_results(
                    user_id=user_id,
                    provider=provider,
                    items=[ingest_item],
                )

                return {
                    "stored": int(inserted),
                    "failed": 0,
                    "retry_count": retry_count,
                    "quality_score": quality_score,
                    "failed_url": None,
                }
            except Exception as e:
                logger.warning(f"Ingest item failed ({url}): {e}")
                return {
                    "stored": 0,
                    "failed": 1,
                    "retry_count": retry_count,
                    "quality_score": quality_score,
                    "failed_url": url or None,
                }

    async def _extract_with_retry(self, url: str) -> tuple[Dict[str, Any], int]:
        if not url:
            return {}, 0

        attempts = max(1, settings.external_ingest_retry_attempts)
        backoff_base = max(0.0, settings.external_ingest_retry_backoff_seconds)
        min_quality = max(0.0, min(settings.external_ingest_min_quality_score, 1.0))

        retries = 0
        for attempt in range(1, attempts + 1):
            await self._respect_domain_rate_limit(url)
            enriched = await self.extractor.extract(url)
            quality_score = float(enriched.get("quality_score") or 0.0) if enriched else 0.0

            if enriched and quality_score >= min_quality:
                return enriched, retries

            if attempt < attempts:
                retries += 1
                sleep_for = backoff_base * attempt
                if sleep_for > 0:
                    await asyncio.sleep(sleep_for)

        return {}, retries

    async def _respect_domain_rate_limit(self, url: str) -> None:
        interval = max(0.0, settings.external_ingest_domain_interval_seconds)
        if interval <= 0:
            return

        domain = urlparse(url).netloc.lower()
        if not domain:
            return

        domain_lock = await self._get_domain_lock(domain)
        async with domain_lock:
            now = time.monotonic()
            last = self._domain_last_request_at.get(domain, 0.0)
            wait_seconds = interval - (now - last)
            if wait_seconds > 0:
                await asyncio.sleep(wait_seconds)
            self._domain_last_request_at[domain] = time.monotonic()

    async def _get_domain_lock(self, domain: str) -> asyncio.Lock:
        async with self._domain_registry_lock:
            if domain not in self._domain_locks:
                self._domain_locks[domain] = asyncio.Lock()
            return self._domain_locks[domain]
