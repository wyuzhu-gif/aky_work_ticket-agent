"""
SmartQuery 服务层
负责系统初始化（Vanna 客户端、LLM、Agent 创建）和单例管理
替代 SQLAgent 独立服务，将 NL2SQL 功能内嵌到主后端

迁移自 SQLAgent-dev: api_server.py 的 initialize_system() + 全局变量管理
"""

import os
import logging
from typing import Optional
from langchain_openai import ChatOpenAI  # type: ignore

logger = logging.getLogger(__name__)

# ==================== 全局单例 ====================

_vn = None  # Vanna 客户端
_agent = None  # Agent 实例
_llm = None  # LLM 实例
_initialized = False


def is_initialized() -> bool:
    return _initialized


def get_agent():
    """获取 Agent 实例"""
    if not _initialized or _agent is None:
        raise RuntimeError("SmartQuery 系统未初始化，请先调用 initialize_smartquery()")
    return _agent


def get_vanna():
    """获取 Vanna 客户端实例"""
    if not _initialized or _vn is None:
        raise RuntimeError("SmartQuery 系统未初始化")
    return _vn


def get_llm():
    """获取 LLM 实例"""
    return _llm


def initialize_smartquery(settings) -> None:
    """
    初始化 SmartQuery NL2SQL 系统
    
    Args:
        settings: config.config.Settings 实例，包含所有配置项
    """
    global _vn, _agent, _llm, _initialized

    if _initialized:
        logger.info("SmartQuery already initialized, skipping")
        return

    # SQLite 持久化配置覆盖 .env 默认值
    from .config_store import apply_to_settings
    apply_to_settings(settings)

    # 禁用代理
    for proxy_var in ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"]:
        os.environ.pop(proxy_var, None)
    os.environ["LANGCHAIN_DEBUG"] = "false"

    # 从 settings 读取配置
    api_key = settings.llm_api_key
    base_url = settings.llm_base_url
    llm_model = settings.sq_llm_model
    milvus_uri = settings.sq_milvus_uri
    embedding_api_url = settings.sq_embedding_api_url
    embedding_provider = settings.sq_embedding_provider
    embedding_api_key = settings.sq_embedding_api_key or settings.llm_api_key
    embedding_model_name = settings.sq_embedding_model_name
    metric_type = settings.sq_milvus_metric_type
    pg_host = settings.pg_host
    pg_port = settings.pg_port
    pg_database = settings.pg_database
    pg_user = settings.pg_user
    pg_password = settings.pg_password
    llm_temperature = settings.sq_llm_temperature
    llm_max_tokens = settings.sq_llm_max_tokens

    # 验证必填参数
    required = {
        'LLM_API_KEY (or llm_api_key)': api_key,
        'LLM_BASE_URL (or llm_base_url)': base_url,
        'SQ_MILVUS_URI': milvus_uri,
        'SQ_EMBEDDING_API_URL': embedding_api_url,
        'PG_HOST': pg_host,
        'PG_DATABASE': pg_database,
        'PG_USER': pg_user,
        'PG_PASSWORD': pg_password,
    }
    missing = [k for k, v in required.items() if not v]
    if missing:
        raise RuntimeError(f"SmartQuery 缺少必要配置: {', '.join(missing)}")

    logger.info("Initializing SmartQuery NL2SQL system...")

    # 导入并创建 Vanna 客户端
    from .clients import create_vanna_client, set_vanna_client, set_api_key, set_llm_instance

    try:
        _vn = create_vanna_client(
            openai_api_key=api_key,
            openai_base_url=base_url,
            model=llm_model,
            max_tokens=llm_max_tokens,
            milvus_uri=milvus_uri,
            embedding_api_url=embedding_api_url,
            embedding_provider=embedding_provider,
            embedding_api_key=embedding_api_key,
            embedding_model_name=embedding_model_name,
            metric_type=metric_type,
        )

        # 连接数据库
        _vn.connect_to_postgres(
            host=pg_host,
            dbname=pg_database,
            user=pg_user,
            password=pg_password,
            port=pg_port,
        )
        logger.info("SmartQuery: PostgreSQL connected via Vanna (Milvus mode)")
    except Exception as e:
        logger.warning(f"Vanna/Milvus initialization failed: {e}")
        logger.info("SmartQuery: falling back to direct PG connection (no Milvus)")
        # 创建一个轻量级的 PG 连接，供 database_tools 使用
        import pandas as pd
        import sqlalchemy
        pg_url = f"postgresql+psycopg2://{pg_user}:{pg_password}@{pg_host}:{pg_port}/{pg_database}"
        engine = sqlalchemy.create_engine(pg_url)

        class _FallbackVanna:
            """Minimal Vanna-like interface that only provides run_sql via direct PG"""
            def run_sql(self, sql: str):
                try:
                    return pd.read_sql(sql, engine)
                except Exception as ex:
                    logger.error(f"FallbackVanna run_sql failed: {ex}")
                    return pd.DataFrame()

        _vn = _FallbackVanna()

    # 设置全局上下文
    set_vanna_client(_vn)
    set_api_key(api_key)

    # 创建 LLM
    _llm = ChatOpenAI(
        model=llm_model,
        temperature=llm_temperature,
        openai_api_key=api_key,
        openai_api_base=base_url,
    )
    set_llm_instance(_llm)

    # 创建 Agent
    from .agent import create_nl2sql_agent
    _agent = create_nl2sql_agent(
        _llm,
        enable_middleware=True,
        enable_ui_events=True,
    )

    _initialized = True
    logger.info("SmartQuery system initialized successfully")


def reconnect_db(pg_host: str, pg_port: int, pg_database: str,
                 pg_user: str, pg_password: str) -> None:
    """热重连数据库：断开旧连接，建立新连接"""
    global _vn

    logger.info(f"SmartQuery: reconnecting DB to {pg_host}:{pg_port}/{pg_database}")

    # 关闭旧连接（如有）
    if _vn is not None:
        try:
            if hasattr(_vn, 'pg_conn') and _vn.pg_conn:
                _vn.pg_conn.close()
            if hasattr(_vn, 'engine') and _vn.engine:
                _vn.engine.dispose()
        except Exception:
            pass

    # 尝试用 Vanna 重新连接
    from .clients import set_vanna_client
    try:
        from .clients import create_vanna_client, set_api_key, set_llm_instance
        from config.config import settings

        _vn = create_vanna_client(
            openai_api_key=settings.llm_api_key,
            openai_base_url=settings.llm_base_url,
            model=settings.sq_llm_model,
            max_tokens=settings.sq_llm_max_tokens,
            milvus_uri=settings.sq_milvus_uri,
            embedding_api_url=settings.sq_embedding_api_url,
            embedding_provider=settings.sq_embedding_provider,
            embedding_api_key=settings.sq_embedding_api_key or settings.llm_api_key,
            embedding_model_name=settings.sq_embedding_model_name,
            metric_type=settings.sq_milvus_metric_type,
        )
        _vn.connect_to_postgres(
            host=pg_host, dbname=pg_database,
            user=pg_user, password=pg_password, port=pg_port,
        )
        set_vanna_client(_vn)
        logger.info("SmartQuery: DB reconnected via Vanna (Milvus mode)")
    except Exception as e:
        logger.warning(f"Vanna/Milvus reconnection failed: {e}")
        # Fallback：直接 PG 连接
        import pandas as pd
        import sqlalchemy
        pg_url = f"postgresql+psycopg2://{pg_user}:{pg_password}@{pg_host}:{pg_port}/{pg_database}"
        engine = sqlalchemy.create_engine(pg_url)

        class _FallbackVanna:
            def run_sql(self, sql: str):
                try:
                    return pd.read_sql(sql, engine)
                except Exception as ex:
                    logger.error(f"FallbackVanna run_sql failed: {ex}")
                    return pd.DataFrame()

        _vn = _FallbackVanna()
        set_vanna_client(_vn)
        logger.info("SmartQuery: DB reconnected via fallback PG")


def reconnect_llm(api_key: str, base_url: str, model: str,
                  temperature: float, max_tokens: int) -> None:
    """热切换 LLM"""
    global _llm

    logger.info(f"SmartQuery: switching LLM to {model}")

    from .clients import set_api_key, set_llm_instance

    _llm = ChatOpenAI(
        model=model,
        temperature=temperature,
        openai_api_key=api_key,
        openai_api_base=base_url,
    )
    set_api_key(api_key)
    set_llm_instance(_llm)
    logger.info("SmartQuery: LLM switched successfully")
