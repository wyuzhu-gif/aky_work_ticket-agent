"""
SmartQuery 配置持久化存储
使用 SQLite 存储 DB/LLM/Agent 配置，启动时覆盖 .env 默认值
支持运行时热切换（保存后立即生效，无需重启）
"""

import json
import sqlite3
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# 使用主应用的 app.db（位于 app/api/app/data/app.db）
_DB_PATH = Path(__file__).resolve().parent.parent / "app" / "data" / "app.db"

# ─── 表结构 ───

_INIT_SQL = """
CREATE TABLE IF NOT EXISTS sq_config (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT DEFAULT (datetime('now', 'localtime'))
);
"""

# ─── 字段映射 ───
# 前端字段 -> 内部 settings 字段
DB_FIELD_MAP = {
    "host":     "db_host",
    "port":     "db_port",
    "dbname":   "db_database",
    "username": "db_user",
    "password": "db_password",
}

LLM_FIELD_MAP = {
    "api_key":    "llm_api_key",
    "base_url":   "llm_base_url",
    "model_name": "sq_llm_model",
    "temperature":"sq_llm_temperature",
    "max_tokens": "sq_llm_max_tokens",
}


def _get_conn() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH))
    conn.execute(_INIT_SQL)
    conn.commit()
    return conn


# ─── 通用读写 ───

def get_all() -> dict:
    """读取所有持久化配置"""
    conn = _get_conn()
    try:
        rows = conn.execute("SELECT key, value FROM sq_config").fetchall()
        result = {}
        for k, v in rows:
            # 尝试解析 JSON（数字/布尔等）
            try:
                result[k] = json.loads(v)
            except (json.JSONDecodeError, TypeError):
                result[k] = v
        return result
    finally:
        conn.close()


# ─── DB 配置 ───

def get_db_config() -> dict:
    """获取持久化的数据库配置（前端字段名）"""
    stored = get_all()
    result = {}
    for frontend_key, settings_key in DB_FIELD_MAP.items():
        if settings_key in stored:
            result[frontend_key] = stored[settings_key]
    return result


def save_db_config(frontend_data: dict) -> dict:
    """保存数据库配置（前端字段名 -> settings 字段名），返回内部存储的键值"""
    kv = {}
    for frontend_key, settings_key in DB_FIELD_MAP.items():
        if frontend_key in frontend_data:
            kv[settings_key] = frontend_data[frontend_key]
    set_many(kv)
    return kv


# ─── LLM 配置 ───

def get_llm_config() -> dict:
    """获取持久化的 LLM 配置（前端字段名）"""
    stored = get_all()
    result = {}
    for frontend_key, settings_key in LLM_FIELD_MAP.items():
        if settings_key in stored:
            # api_key 脱敏
            if frontend_key == "api_key" and isinstance(stored[settings_key], str) and len(stored[settings_key]) > 8:
                result[frontend_key] = "******"
            else:
                result[frontend_key] = stored[settings_key]
    return result


def save_llm_config(frontend_data: dict) -> dict:
    """保存 LLM 配置，返回内部键值"""
    kv = {}
    for frontend_key, settings_key in LLM_FIELD_MAP.items():
        if frontend_key in frontend_data:
            val = frontend_data[frontend_key]
            # api_key 为 "******" 或空时不覆盖
            if frontend_key == "api_key" and (val == "******" or not val):
                continue
            kv[settings_key] = val
    set_many(kv)
    return kv


# ─── 启动时覆盖 settings ───

def apply_to_settings(settings) -> None:
    """将 SQLite 中的持久化配置覆盖到 Settings 对象"""
    stored = get_all()
    applied = []
    for settings_key, value in stored.items():
        if hasattr(settings, settings_key):
            old = getattr(settings, settings_key)
            if old != value:
                setattr(settings, settings_key, value)
                applied.append(f"{settings_key}={value}")
    if applied:
        logger.info(f"SmartQuery config from SQLite: {', '.join(applied)}")
