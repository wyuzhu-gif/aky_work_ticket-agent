"""
Chat router: 内嵌 SmartQuery NL2SQL，不再代理 SQLAgent
提供流式 SSE 对话接口 + 会话历史管理 API
"""
import uuid
import logging
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional

from smart_query.service import get_agent, get_vanna, is_initialized
from smart_query.sessions import (
    get_or_create_session, add_message_to_session, get_session_history,
    create_session, list_sessions, get_session, delete_session,
    get_session_messages, update_session_title,
)
from smart_query.streaming import generate_chat_stream

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/chat", tags=["chat"])


class ChatRequest(BaseModel):
    """对话请求"""
    question: str = Field(..., description="用户问题")
    stream: bool = Field(default=True, description="是否流式返回")
    session_id: Optional[str] = Field(default=None, description="会话ID")
    enable_training: bool = Field(default=False, description="是否启用训练决策")


# ─── 会话管理 API ───

@router.get("/sessions")
async def api_list_sessions(limit: int = 50, offset: int = 0):
    """列出所有会话"""
    sessions = list_sessions(limit=limit, offset=offset)
    return {"data": sessions, "total": len(sessions)}


class CreateSessionRequest(BaseModel):
    title: str = Field(default="", description="会话标题")


@router.post("/sessions")
async def api_create_session(req: CreateSessionRequest):
    """创建新会话"""
    session = create_session(title=req.title)
    return {"data": session}


@router.get("/sessions/{session_id}")
async def api_get_session(session_id: str):
    """获取会话详情（含所有消息）"""
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    messages = get_session_messages(session_id)
    return {"data": {"session": session, "messages": messages}}


@router.delete("/sessions/{session_id}")
async def api_delete_session(session_id: str):
    """删除会话"""
    ok = delete_session(session_id)
    if not ok:
        raise HTTPException(status_code=404, detail="会话不存在")
    return {"data": {"deleted": True}}


class UpdateSessionRequest(BaseModel):
    title: str = Field(..., description="新标题")


@router.patch("/sessions/{session_id}")
async def api_update_session(session_id: str, req: UpdateSessionRequest):
    """更新会话标题"""
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    update_session_title(session_id, req.title)
    return {"data": {"updated": True}}


# ─── 对话 API ───

@router.post("/stream")
async def chat_stream(req: ChatRequest):
    """
    流式对话接口 - 内嵌 SmartQuery NL2SQL
    
    SSE 事件格式：
    - {"type": "step", "action": "...", "status": "preparing|running|completed"}
    - {"type": "data", "data": [...], "columns": [...], "sql": "..."}
    - {"type": "answer", "content": "...", "done": false}
    - {"type": "chart_config", "config": {...}}
    - {"type": "done", "session_id": "..."}
    - {"type": "error", "message": "..."}
    """
    if not is_initialized():
        raise HTTPException(status_code=503, detail="SmartQuery 系统未初始化")

    agent = get_agent()
    sid = req.session_id or str(uuid.uuid4())

    # 确保会话存在（新会话自动创建）
    get_or_create_session(sid)

    # 如果是新会话且没有标题，用首条问题做标题
    session = get_session(sid)
    if session and not session.get("title"):
        title = req.question[:50] + ("..." if len(req.question) > 50 else "")
        update_session_title(sid, title)

    # 保存用户消息到会话历史
    add_message_to_session(sid, "user", req.question)

    # 构建带历史上下文的消息列表
    history = get_session_history(sid)
    messages_payload = [{"role": msg["role"], "content": msg["content"]} for msg in history]

    # 获取 Vanna 客户端（训练决策需要）
    vanna_client = None
    if req.enable_training:
        try:
            vanna_client = get_vanna()
        except RuntimeError:
            pass

    from config.config import settings

    return StreamingResponse(
        generate_chat_stream(
            agent=agent,
            question=req.question,
            session_id=sid,
            messages_payload=messages_payload,
            enable_training=req.enable_training,
            vanna_client=vanna_client,
            recursion_limit=settings.sq_agent_recursion_limit,
        ),
        media_type="text/event-stream",
    )


@router.post("")
async def chat_non_stream(req: ChatRequest):
    """非流式对话接口"""
    if not is_initialized():
        raise HTTPException(status_code=503, detail="SmartQuery 系统未初始化")

    import time
    import os

    agent = get_agent()
    start_time = time.time()

    try:
        cfg = {
            "configurable": {"thread_id": f"api-{int(time.time())}"},
            "recursion_limit": 100,
        }

        final_event = None
        for event in agent.stream(
            {"messages": [{"role": "user", "content": req.question}]},
            stream_mode="values",
            config=cfg,
        ):
            final_event = event

        if not final_event:
            raise HTTPException(status_code=500, detail="Agent 执行失败")

        messages = final_event.get("messages", [])
        answer = "无法生成回答"
        ui_events = None

        for msg in reversed(messages):
            if getattr(msg, 'type', '') == 'ai':
                content = getattr(msg, 'content', '').strip()
                if content and len(content) > 10:
                    answer = content
                    additional_kwargs = getattr(msg, 'additional_kwargs', {})
                    ui_events = additional_kwargs.get('ui_events')
                    break

        elapsed = time.time() - start_time

        return {
            "question": req.question,
            "answer": answer,
            "execution_time": elapsed,
            "timestamp": time.strftime('%Y-%m-%d %H:%M:%S'),
            "ui_events": ui_events,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"对话处理失败: {str(e)}")
