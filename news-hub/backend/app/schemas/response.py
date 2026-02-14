"""
Unified Response Schema

Provides standardized API response format for all endpoints.
Format: {code, message, data}
"""

from typing import Any, Generic, List, Optional, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ResponseBase(BaseModel, Generic[T]):
    """
    Unified API response structure.

    Attributes:
        code: HTTP-like status code (200=success, 400=client error, 500=server error)
        message: Human-readable status message
        data: Response payload (type varies by endpoint)
    """

    code: int = Field(default=200, description="Status code")
    message: str = Field(default="success", description="Status message")
    data: Optional[T] = Field(default=None, description="Response payload")


class PaginatedData(BaseModel, Generic[T]):
    """
    Paginated list response data structure.

    Attributes:
        items: List of items for current page
        total: Total number of items across all pages
        page: Current page number (1-indexed)
        page_size: Number of items per page
        has_more: Whether more pages exist
    """

    items: List[T] = Field(default_factory=list, description="List of items")
    total: int = Field(default=0, description="Total count")
    page: int = Field(default=1, ge=1, description="Current page")
    page_size: int = Field(default=20, ge=1, le=100, description="Items per page")
    has_more: bool = Field(default=False, description="Has more pages")


class PaginatedResponse(ResponseBase[PaginatedData[T]], Generic[T]):
    """Paginated list response."""

    pass


# === Convenience Response Factories ===


def success_response(data: Any = None, message: str = "success") -> ResponseBase:
    """Create a success response."""
    return ResponseBase(code=200, message=message, data=data)


def error_response(message: str, code: int = 400, data: Any = None) -> ResponseBase:
    """Create an error response."""
    return ResponseBase(code=code, message=message, data=data)


def paginated_response(
    items: List[Any],
    total: int,
    page: int = 1,
    page_size: int = 20,
    message: str = "success",
) -> ResponseBase:
    """Create a paginated response."""
    has_more = (page * page_size) < total
    return ResponseBase(
        code=200,
        message=message,
        data=PaginatedData(
            items=items, total=total, page=page, page_size=page_size, has_more=has_more
        ),
    )
