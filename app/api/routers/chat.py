"""Chat proxy: forward requests to SQLAgent SSE endpoint."""
import logging
import httpx
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from config.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/chat", tags=["chat"])


class ChatRequest(BaseModel):
    question: str


@router.post("/stream")
async def chat_stream(req: ChatRequest):
    """Proxy SSE stream from SQLAgent."""
    url = f"{settings.sqlagent_url.rstrip('/')}/api/v1/projects/{settings.sqlagent_project_id}/chat/stream"

    async def generate():
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                async with client.stream(
                    "POST",
                    url,
                    json={"question": req.question, "stream": True},
                    headers={"Content-Type": "application/json"},
                ) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if line.startswith("data: "):
                            yield line + "\n\n"
                        elif line.strip():
                            yield line + "\n"
        except httpx.ConnectError:
            msg = '{"type": "error", "message": "SQLAgent 服务不可用"}'
            yield f"data: {msg}\n\n"
        except Exception as e:
            logger.error(f"Chat proxy error: {e}")
            yield f'data: {{"type": "error", "message": "{str(e)}"}}\n\n'

    return StreamingResponse(generate(), media_type="text/event-stream")
