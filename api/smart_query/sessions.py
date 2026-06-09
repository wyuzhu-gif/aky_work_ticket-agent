"""
会话管理模块 — SQLite 持久化存储

支持对话历史、查询结果、图表配置等富数据持久化
重启服务不丢失历史记录
"""

import json
import sqlite3
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime as dt

logger = logging.getLogger(__name__)

# 使用主应用的 app.db（与 config_store 共享）
_DB_PATH = Path(__file__).resolve().parent.parent / "app" / "data" / "app.db"

# ─── 建表 SQL ───

_INIT_SQL = """
CREATE TABLE IF NOT EXISTS sq_sessions (
    id TEXT PRIMARY KEY,
    title TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now','localtime')),
    updated_at TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS sq_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT DEFAULT '',
    query_data TEXT,
    chart_config TEXT,
    thinking_steps TEXT,
    created_at TEXT DEFAULT (datetime('now','localtime')),
    FOREIGN KEY (session_id) REFERENCES sq_sessions(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_sq_messages_session ON sq_messages(session_id);
"""


def _get_conn() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH))
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    for stmt in _INIT_SQL.strip().split(";"):
        stmt = stmt.strip()
        if stmt:
            conn.execute(stmt)
    conn.commit()
    return conn


# ─── 会话 CRUD ───

def create_session(session_id: Optional[str] = None, title: str = "") -> Dict[str, Any]:
    """创建新会话，返回会话信息"""
    if not session_id:
        import uuid
        session_id = str(uuid.uuid4())
    conn = _get_conn()
    try:
        conn.execute(
            "INSERT INTO sq_sessions(id, title) VALUES(?, ?)",
            (session_id, title),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM sq_sessions WHERE id=?", (session_id,)).fetchone()
        return dict(row)
    finally:
        conn.close()


def get_or_create_session(session_id: str) -> Dict[str, Any]:
    """获取或创建会话（兼容旧接口）"""
    conn = _get_conn()
    try:
        row = conn.execute("SELECT * FROM sq_sessions WHERE id=?", (session_id,)).fetchone()
        if row:
            return dict(row)
    finally:
        conn.close()
    return create_session(session_id=session_id)


def list_sessions(limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
    """列出所有会话，按更新时间倒序"""
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT s.*, (SELECT COUNT(*) FROM sq_messages WHERE session_id=s.id) AS msg_count "
            "FROM sq_sessions s ORDER BY s.updated_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_session(session_id: str) -> Optional[Dict[str, Any]]:
    """获取单个会话信息"""
    conn = _get_conn()
    try:
        row = conn.execute("SELECT * FROM sq_sessions WHERE id=?", (session_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def delete_session(session_id: str) -> bool:
    """删除会话及其所有消息"""
    conn = _get_conn()
    try:
        cur = conn.execute("DELETE FROM sq_sessions WHERE id=?", (session_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def update_session_title(session_id: str, title: str):
    """更新会话标题"""
    conn = _get_conn()
    try:
        conn.execute(
            "UPDATE sq_sessions SET title=?, updated_at=datetime('now','localtime') WHERE id=?",
            (title, session_id),
        )
        conn.commit()
    finally:
        conn.close()


# ─── 消息 CRUD ───

def add_message(
    session_id: str,
    role: str,
    content: str = "",
    query_data: Optional[Dict] = None,
    chart_config: Optional[Dict] = None,
    thinking_steps: Optional[List[Dict]] = None,
) -> int:
    """添加消息到会话，返回消息 ID"""
    conn = _get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO sq_messages(session_id, role, content, query_data, chart_config, thinking_steps) "
            "VALUES(?, ?, ?, ?, ?, ?)",
            (
                session_id,
                role,
                content,
                json.dumps(query_data, ensure_ascii=False) if query_data else None,
                json.dumps(chart_config, ensure_ascii=False) if chart_config else None,
                json.dumps(thinking_steps, ensure_ascii=False) if thinking_steps else None,
            ),
        )
        msg_id = cur.lastrowid or 0
        # 更新会话的 updated_at
        conn.execute(
            "UPDATE sq_sessions SET updated_at=datetime('now','localtime') WHERE id=?",
            (session_id,),
        )
        conn.commit()
        return msg_id
    finally:
        conn.close()


def add_message_to_session(session_id: str, role: str, content: str):
    """添加消息到会话（兼容旧接口，只存纯文本）"""
    # 确保会话存在
    get_or_create_session(session_id)
    add_message(session_id=session_id, role=role, content=content)


def get_session_messages(session_id: str) -> List[Dict[str, Any]]:
    """获取会话的所有消息（含富数据）"""
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM sq_messages WHERE session_id=? ORDER BY id ASC",
            (session_id,),
        ).fetchall()
        result = []
        for r in rows:
            msg = {
                "id": r["id"],
                "session_id": r["session_id"],
                "role": r["role"],
                "content": r["content"] or "",
                "queryData": json.loads(r["query_data"]) if r["query_data"] else None,
                "chartConfig": json.loads(r["chart_config"]) if r["chart_config"] else None,
                "thinkingSteps": json.loads(r["thinking_steps"]) if r["thinking_steps"] else None,
                "created_at": r["created_at"],
            }
            result.append(msg)
        return result
    finally:
        conn.close()


def get_session_history(session_id: str) -> List[Dict[str, str]]:
    """获取会话历史（兼容旧接口，只返回 role+content）"""
    messages = get_session_messages(session_id)
    return [{"role": m["role"], "content": m["content"]} for m in messages]
