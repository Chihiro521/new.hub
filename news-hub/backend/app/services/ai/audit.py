"""
Audit logging for AI assistant actions.

All public methods catch exceptions internally and log warnings
rather than raising — audit failures must never block AI features.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from bson import ObjectId
from loguru import logger

from app.db.mongo import mongodb


class AuditLogger:
    """Non-blocking audit logger for AI actions."""

    @staticmethod
    async def log(
        user_id: str,
        action: str,
        input_summary: str = "",
        output_summary: str = "",
        model: str = "",
        latency_ms: int = 0,
        token_usage: Optional[Dict[str, int]] = None,
        fallback_used: bool = False,
        error: Optional[str] = None,
    ) -> Optional[str]:
        """Record an AI action to the audit log.

        Returns the inserted log ID, or None on failure.
        """
        try:
            doc = {
                "user_id": user_id,
                "action": action,
                "input_summary": input_summary[:500],
                "output_summary": output_summary[:500],
                "model": model,
                "latency_ms": latency_ms,
                "token_usage": token_usage or {"prompt": 0, "completion": 0},
                "quality_signals": {
                    "user_feedback": None,
                    "fallback_used": fallback_used,
                    "error": error,
                },
                "created_at": datetime.utcnow(),
            }
            result = await mongodb.db.ai_audit_logs.insert_one(doc)
            return str(result.inserted_id)
        except Exception as e:
            logger.warning(f"Audit log failed for action '{action}': {e}")
            return None

    @staticmethod
    async def get_logs(
        user_id: str,
        action: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Retrieve paginated audit logs for a user.

        Returns (logs, total_count).
        """
        query: Dict[str, Any] = {"user_id": user_id}
        if action:
            query["action"] = action

        total = await mongodb.db.ai_audit_logs.count_documents(query)
        cursor = (
            mongodb.db.ai_audit_logs.find(query)
            .sort("created_at", -1)
            .skip((page - 1) * page_size)
            .limit(page_size)
        )
        docs = await cursor.to_list(length=page_size)

        logs: List[Dict[str, Any]] = []
        for doc in docs:
            doc["_id"] = str(doc["_id"])
            logs.append(doc)

        return logs, total

    @staticmethod
    async def record_feedback(log_id: str, user_id: str, feedback: str) -> bool:
        """Record user feedback on an AI action.

        Returns True if updated, False otherwise.
        """
        try:
            oid = ObjectId(log_id)
        except Exception:
            return False

        try:
            result = await mongodb.db.ai_audit_logs.update_one(
                {"_id": oid, "user_id": user_id},
                {"$set": {"quality_signals.user_feedback": feedback}},
            )
            return result.modified_count > 0
        except Exception as e:
            logger.warning(f"Audit feedback failed for log {log_id}: {e}")
            return False
