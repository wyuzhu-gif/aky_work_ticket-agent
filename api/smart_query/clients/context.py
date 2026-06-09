"""
全局上下文管理
所有模块共享的 Vanna 客户端、API Key 和 LLM 实例

迁移自 SQLAgent-dev: backend/vanna/src/Improve/shared/context.py
简化版：去掉多租户（project_registry）相关功能，本系统为单项目部署
"""

import logging
import threading
logger = logging.getLogger(__name__)
from typing import Optional

# ==================== 全局单例变量 ====================
_vanna_client: Optional[any] = None
_api_key: Optional[str] = None
_llm_instance: Optional[any] = None

# 查询结果缓存 — 使用模块级全局变量 + 线程锁
# （ContextVar 无法跨 LangGraph 内部线程池同步，改用全局变量）
_last_query_result = None
_last_query_lock = threading.Lock()


# ==================== Vanna 客户端管理 ====================

def set_vanna_client(vn):
    global _vanna_client
    _vanna_client = vn


def get_vanna_client():
    global _vanna_client
    if _vanna_client is None:
        raise RuntimeError("Vanna client not initialized. Call set_vanna_client() first.")
    return _vanna_client


# ==================== API Key 管理 ====================

def set_api_key(key: str):
    global _api_key
    _api_key = key


def get_api_key() -> str:
    global _api_key
    if _api_key is None:
        raise RuntimeError("API key not initialized. Call set_api_key() first.")
    return _api_key


# ==================== LLM 实例管理 ====================

def set_llm_instance(llm):
    global _llm_instance
    _llm_instance = llm


def get_llm_instance():
    global _llm_instance
    return _llm_instance


# ==================== 查询结果缓存 ====================

def set_last_query_result(df):
    """缓存查询结果 DataFrame（线程安全）"""
    global _last_query_result
    with _last_query_lock:
        _last_query_result = df


def get_last_query_result():
    """获取缓存的查询结果（线程安全）"""
    with _last_query_lock:
        return _last_query_result


def clear_last_query_result():
    """清除缓存的查询结果（线程安全）"""
    global _last_query_result
    with _last_query_lock:
        _last_query_result = None
