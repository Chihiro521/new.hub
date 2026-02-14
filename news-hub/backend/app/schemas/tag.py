"""
Tag Rule Schema Definitions

Pydantic models for auto-tagging rule configuration.
"""

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class MatchMode(str, Enum):
    """Keyword matching mode."""

    ANY = "any"  # Match if any keyword is found
    ALL = "all"  # Match only if all keywords are found


class TagRuleBase(BaseModel):
    """Base tag rule fields."""

    tag_name: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Tag name to apply when rule matches",
    )
    keywords: List[str] = Field(
        ..., min_length=1, description="Keywords to match in content"
    )
    match_mode: MatchMode = Field(
        default=MatchMode.ANY, description="How to combine keywords"
    )
    case_sensitive: bool = Field(default=False, description="Case-sensitive matching")
    match_title: bool = Field(default=True, description="Match in title")
    match_description: bool = Field(default=True, description="Match in description")
    match_content: bool = Field(default=False, description="Match in full content")
    priority: int = Field(
        default=0, ge=0, le=100, description="Rule priority (higher = applied first)"
    )


class TagRuleCreate(TagRuleBase):
    """Schema for creating a tag rule."""

    pass


class TagRuleUpdate(BaseModel):
    """Schema for updating a tag rule."""

    tag_name: Optional[str] = None
    keywords: Optional[List[str]] = None
    match_mode: Optional[MatchMode] = None
    case_sensitive: Optional[bool] = None
    match_title: Optional[bool] = None
    match_description: Optional[bool] = None
    match_content: Optional[bool] = None
    priority: Optional[int] = Field(default=None, ge=0, le=100)
    is_active: Optional[bool] = None


class TagRuleInDB(TagRuleBase):
    """Tag rule as stored in database."""

    id: str = Field(..., alias="_id", description="Rule ID")
    user_id: str = Field(..., description="Owner user ID")
    is_active: bool = Field(default=True)
    match_count: int = Field(
        default=0, description="Number of items matched by this rule"
    )
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True


class TagRuleResponse(TagRuleBase):
    """Tag rule returned in API responses."""

    id: str
    user_id: str
    is_active: bool
    match_count: int
    created_at: datetime

    class Config:
        from_attributes = True
