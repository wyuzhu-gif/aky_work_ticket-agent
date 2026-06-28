"""
Chat router: 内嵌 SmartQuery NL2SQL，不再代理 SQLAgent
提供流式 SSE 对话接口 + 会话历史管理 API
"""
import uuid
import json
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
from smart_query.streaming import generate_chat_stream, generate_safety_stream, generate_casual_stream
from smart_query.intent_classifier import classify_intent

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
    - {"type": "intent", "intent": "database_query|safety_knowledge|casual_chat"}  ← 新增 (2026-06-23)
    - {"type": "step", "action": "...", "status": "preparing|running|completed"}
    - {"type": "data", "data": [...], "columns": [...], "sql": "..."}
    - {"type": "answer", "content": "...", "done": false}
    - {"type": "chart_config", "config": {...}}
    - {"type": "done", "session_id": "..."}
    - {"type": "error", "message": "..."}

    意图分流 (2026-06-23):
    - database_query: 走 LangChain Agent + Vanna → SQL → llm-wiki (hermes 查法规)
    - safety_knowledge: 只走 hermes 查 llm-wiki (不动数据库)
    - casual_chat: 走 hermes 友好回复 (统一入口)
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

    # ========== 意图分流 (2026-06-23) ==========
    intent = classify_intent(req.question)
    logger.info(f"[Chat] 意图识别: '{req.question[:30]}' → {intent}")

    # ─── 分支 1: 安全知识 → 只走 hermes (不动数据库) ───
    if intent == "safety_knowledge":
        return StreamingResponse(
            _stream_with_intent_event(generate_safety_stream, req.question, sid, intent),
            media_type="text/event-stream",
        )

    # ─── 分支 2: 闲聊 → 走 hermes 友好回复 ───
    if intent == "casual_chat":
        return StreamingResponse(
            _stream_with_intent_event(generate_casual_stream, req.question, sid, intent),
            media_type="text/event-stream",
        )

    # ─── 分支 3: 数据库查询 → 走完整 NL2SQL 链路 ───
    # 构建带历史上下文的消息列表
    # ⚠️ 只取最近 2 条 (user + assistant), 避免 LLM 看到前几轮的"幻觉"答案继续 hallucination
    # 之前取全部 history 会导致 LLM 被自己之前的"我将为您进行..."假回答污染
    history = get_session_history(sid)

    # 清理污染: 如果最近 assistant 消息是"半截答案"(如"SQL验证通过" / "我将为您...") 且 < 50 字符
    # 这种是前次失败留下的假答案, 不能传给 LLM 当 history
    # 解决: 直接清空 history 里这种"半截"消息
    cleaned_history = []
    for msg in history:
        content = msg.get('content', '')
        if msg.get('role') == 'assistant' and len(content) < 80 and any(
            kw in content for kw in ['SQL验证', '语法检查', '我将为您', '我来帮您', '让我', '首先', '了解']
        ):
            # 跳过污染消息
            logger.info(f"[Chat] 跳过污染历史 assistant msg: {content[:50]!r}")
            continue
        cleaned_history.append(msg)

    # ⚠️ 只取最近 2 条 (1 user + 1 assistant), 避免 LLM 看到前几轮
    recent_history = cleaned_history[-2:] if len(cleaned_history) > 2 else cleaned_history
    messages_payload = [{"role": msg["role"], "content": msg["content"]} for msg in recent_history]

    # 获取 Vanna 客户端（训练决策需要）
    vanna_client = None
    if req.enable_training:
        try:
            vanna_client = get_vanna()
        except RuntimeError:
            pass

    from config.config import settings

    # 数据库查询分支: 先推 intent 事件, 再走原有 generate_chat_stream
    return StreamingResponse(
        _stream_with_intent_event_db(
            generate_chat_stream,
            agent=agent,
            question=req.question,
            session_id=sid,
            messages_payload=messages_payload,
            enable_training=req.enable_training,
            vanna_client=vanna_client,
            recursion_limit=settings.sq_agent_recursion_limit,
            intent=intent,
        ),
        media_type="text/event-stream",
    )


async def _stream_with_intent_event(stream_fn, question: str, sid: str, intent: str):
    """
    给 safety / casual 分支包装: 先推一个 intent 事件让前端知道走哪条路,
    再走实际的 stream generator.
    """
    import json as _json
    intent_event = f"data: {_json.dumps({'type': 'intent', 'intent': intent}, ensure_ascii=False)}\n\n"
    yield intent_event

    # stream_fn 是 sync generator, FastAPI 会自动用 thread pool
    for chunk in stream_fn(question=question, session_id=sid):
        yield chunk


async def _stream_with_intent_event_db(stream_fn, *, intent: str, **kwargs):
    """
    给 database_query 分支包装: 先推 intent 事件, 再调 generate_chat_stream (参数不同).
    """
    import json as _json
    intent_event = f"data: {_json.dumps({'type': 'intent', 'intent': intent}, ensure_ascii=False)}\n\n"
    yield intent_event

    for chunk in stream_fn(**kwargs):
        yield chunk


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
        from smart_query.clients import get_last_query_result, get_last_query_sql, clear_last_query_result
        from smart_query.streaming import generate_final_report

        import json as _json
        import re as _re

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
        fallback_answer = "无法生成回答"
        ui_events = None

        for msg in reversed(messages):
            if getattr(msg, 'type', '') == 'ai':
                content = getattr(msg, 'content', '').strip()
                if content and len(content) > 10:
                    fallback_answer = content
                    additional_kwargs = getattr(msg, 'additional_kwargs', {})
                    ui_events = additional_kwargs.get('ui_events')
                    break

        # 2026-06-24: 走统一的 generate_final_report() 收尾逻辑
        # 之前 chat_non_stream 直接返回 agent.stream 的 final answer (LLM 强停时输出截断)
        # 现在跟 SSE 端点 (generate_chat_stream) 行为一致:
        #   1. 拿 query_data (来自 execute_sql 缓存)
        #   2. 调内层 hermes + llm-wiki 拿法规依据
        #   3. 调 report_llm 合成最终报告
        #   4. 解析 ```chartconfig``` 块
        df = get_last_query_result()
        query_data = df.to_dict('records') if df is not None else None
        sql_query = get_last_query_sql()

        answer, chart_config = generate_final_report(
            question=req.question,
            query_data=query_data,
            sql_query=sql_query,
            fallback_answer=fallback_answer,
        )

        elapsed = time.time() - start_time

        return {
            "question": req.question,
            "answer": answer,
            "execution_time": elapsed,
            "timestamp": time.strftime('%Y-%m-%d %H:%M:%S'),
            "ui_events": ui_events,
            "chart_config": chart_config,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"对话处理失败: {str(e)}")
