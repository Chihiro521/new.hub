"""AI Assistant API routes with streaming chat support."""

import json
from typing import AsyncGenerator, List

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from app.core.deps import get_current_user
from app.db.mongo import mongodb
from app.schemas.assistant import (
    ChatRequest,
    ChatResponseData,
    ClassifyRequest,
    ClassifyResponseData,
    DiscoverSourcesRequest,
    DiscoverSourcesResponseData,
    SummarizeRequest,
    SummarizeResponseData,
)
from app.schemas.response import ResponseBase, success_response
from app.schemas.user import UserInDB
from app.services.ai.assistant_service import AssistantService

router = APIRouter(prefix="/assistant", tags=["AI Assistant"])


def _service_error_to_http(error: ValueError) -> HTTPException:
    """Map service-level ValueError to HTTPException."""
    message = str(error)
    if "not found" in message.lower():
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=message,
        )
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=message,
    )


@router.post("/chat", response_model=ResponseBase[ChatResponseData])
async def chat_with_assistant(
    request: ChatRequest,
    current_user: UserInDB = Depends(get_current_user),
):
    """Chat with AI assistant, with SSE streaming by default."""
    service = AssistantService()
    messages: List[dict] = [m.model_dump() for m in request.messages]

    if not request.stream:
        chunks = []
        async for chunk in service.chat(messages=messages, user_id=current_user.id):
            chunks.append(chunk)
        return success_response(data=ChatResponseData(reply="".join(chunks)))

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            async for delta in service.chat(messages=messages, user_id=current_user.id):
                payload = json.dumps({"type": "delta", "content": delta})
                yield f"data: {payload}\n\n"
            yield 'data: {"type": "done"}\n\n'
        except Exception as e:
            error_payload = json.dumps({"type": "error", "content": str(e)})
            yield f"data: {error_payload}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/summarize", response_model=ResponseBase[SummarizeResponseData])
async def summarize_news(
    request: SummarizeRequest,
    current_user: UserInDB = Depends(get_current_user),
):
    """Summarize a news article with AI/fallback mode."""
    service = AssistantService()
    try:
        data = await service.summarize(news_id=request.news_id, user_id=current_user.id)
        return success_response(data=data)
    except ValueError as e:
        raise _service_error_to_http(e)


@router.post("/classify", response_model=ResponseBase[ClassifyResponseData])
async def classify_news(
    request: ClassifyRequest,
    current_user: UserInDB = Depends(get_current_user),
):
    """Classify a news article to suggested tags."""
    service = AssistantService()

    rules = await mongodb.db.tag_rules.find(
        {"user_id": current_user.id, "is_active": True}
    ).to_list(length=1000)
    available_tags = sorted(
        {
            str(rule.get("tag_name", "")).strip()
            for rule in rules
            if str(rule.get("tag_name", "")).strip()
        }
    )

    try:
        data = await service.classify(
            news_id=request.news_id,
            user_id=current_user.id,
            available_tags=available_tags,
        )
        return success_response(data=data)
    except ValueError as e:
        raise _service_error_to_http(e)


@router.post(
    "/discover-sources",
    response_model=ResponseBase[DiscoverSourcesResponseData],
)
async def discover_sources(
    request: DiscoverSourcesRequest,
    current_user: UserInDB = Depends(get_current_user),
):
    """Discover source suggestions for a topic."""
    service = AssistantService()
    data = await service.discover_sources(topic=request.topic)
    return success_response(data=data)
