"""
User Schema Definitions

Pydantic models for user-related API contracts.
"""

from datetime import datetime
from typing import Optional
import re

from pydantic import BaseModel, Field, field_validator


class UserBase(BaseModel):
    """Base user fields shared across schemas."""

    username: str = Field(
        ...,
        min_length=3,
        max_length=32,
        pattern=r"^[a-zA-Z0-9_-]+$",
        description="Username (alphanumeric, underscore, hyphen only)",
    )
    email: str = Field(..., description="User email address")

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        value = (v or "").strip()
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", value):
            raise ValueError("Invalid email format")
        return value.lower()


class UserCreate(UserBase):
    """Schema for user registration request."""

    password: str = Field(
        ...,
        min_length=6,
        max_length=128,
        description="User password (min 6 characters)",
    )

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        """Ensure password has minimum complexity."""
        if len(v) < 6:
            raise ValueError("Password must be at least 6 characters")
        return v


class UserLogin(BaseModel):
    """Schema for user login request."""

    username: str = Field(..., description="Username or email")
    password: str = Field(..., description="User password")


class UserUpdate(BaseModel):
    """Schema for user profile update."""

    email: Optional[str] = None
    avatar_url: Optional[str] = None
    settings: Optional[dict] = None

    @field_validator("email")
    @classmethod
    def validate_optional_email(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        value = v.strip()
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", value):
            raise ValueError("Invalid email format")
        return value.lower()


class UserInDB(UserBase):
    """User model as stored in database."""

    id: str = Field(..., alias="_id", description="User ID")
    hashed_password: str = Field(..., description="Bcrypt hashed password")
    avatar_url: Optional[str] = None
    settings: dict = Field(default_factory=dict, description="User preferences")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    is_active: bool = Field(default=True, description="Account active status")

    class Config:
        populate_by_name = True


class UserResponse(UserBase):
    """User data returned in API responses (excludes sensitive fields)."""

    id: str = Field(..., description="User ID")
    avatar_url: Optional[str] = None
    settings: dict = Field(default_factory=dict)
    created_at: datetime

    class Config:
        from_attributes = True


class Token(BaseModel):
    """JWT token response."""

    access_token: str = Field(..., description="JWT access token")
    token_type: str = Field(default="bearer", description="Token type")
    expires_in: int = Field(..., description="Token expiration in seconds")


class TokenPayload(BaseModel):
    """JWT token payload structure."""

    sub: str = Field(..., description="Subject (user_id)")
    exp: int = Field(..., description="Expiration timestamp")
    iat: int = Field(..., description="Issued at timestamp")
