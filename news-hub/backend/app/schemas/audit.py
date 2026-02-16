"""
AI Audit Log Schema

Request and response models for audit logging and user feedback.
"""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class TokenUsage(BaseModel):
    """Token usage breakdown for an AI action."""

    prompt: int = 0
    completion: int = 0


class QualitySignals(BaseModel):
    """Quality and governance signals for an AI action."""

    user_feedback: Optional[Literal["positive", "negative"]] = None
    fallback_used: bool = False
    error: Optional[str] = None


class AuditLogResponse(BaseModel):
    """Audit log entry returned in API responses."""

    id: str
    action: str
    input_summary: str = ""
    output_summary: str = ""
    model: str = ""
    latency_ms: int = 0
    token_usage: TokenUsage = Field(default_factory=TokenUsage)
    quality_signals: QualitySignals = Field(default_factory=QualitySignals)
    created_at: datetime


class AuditFeedback(BaseModel):
    """User feedback on an AI action."""

    feedback: Literal["positive", "negative"] = Field(
        ..., description="User feedback: positive or negative"
    )
