"""
客户端封装模块
提供 Vanna + Embedding 客户端封装和全局上下文管理
"""

import logging
logger = logging.getLogger(__name__)

from .vanna_client import create_vanna_client, MyVanna
from .embedding_providers import (
    EmbeddingBase,
    JinaEmbedding,
    QwenEmbedding,
    BGEEmbedding,
    create_embedding_client,
)
from .context import (
    set_vanna_client,
    get_vanna_client,
    set_api_key,
    get_api_key,
    set_llm_instance,
    get_llm_instance,
    set_last_query_result,
    get_last_query_result,
    get_last_query_sql,  # 2026-06-10 跟 df 配对的 SQL
    clear_last_query_result,
)

__all__ = [
    'create_vanna_client',
    'MyVanna',
    'EmbeddingBase',
    'JinaEmbedding',
    'QwenEmbedding',
    'BGEEmbedding',
    'create_embedding_client',
    'set_vanna_client',
    'get_vanna_client',
    'set_api_key',
    'get_api_key',
    'set_llm_instance',
    'get_llm_instance',
    'set_last_query_result',
    'get_last_query_result',
    'get_last_query_sql',
    'clear_last_query_result',
]
