from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # General
    debug: bool = False
    serve_static: bool = True
    log_level: str = "INFO"
    log_to_file: bool = True

    # Placeholder auth (kept for compatibility with swagger config)
    aad_client_id: str = ""
    aad_tenant_id: str = ""
    aad_user_impersonation_scope_id: str = ""

    # Local storage / DB
    local_docs_dir: str = "./app/data/documents"
    sqlite_path: str = "./app/data/app.db"

    # MinerU
    mineru_base_url: str = "https://mineru.net"
    mineru_api_key: str = ""
    mineru_model_version: str = "vlm"
    mineru_poll_interval_sec: float = 1.0
    mineru_max_wait_sec: float = 300.0
    mineru_cache_artifacts: bool = True
    mineru_cache_dir: str = "./app/data/mineru"
    mineru_local_url: str = ""  # local MinerU API, e.g. http://192.168.16.85:38030
    # MinerU bbox coordinate assumptions
    # Most MinerU JSON outputs use image-like coordinates with origin at top-left.
    mineru_bbox_origin: str = "top-left"  # "top-left" or "bottom-left"
    mineru_bbox_units: str = "auto"  # "auto", "px", "pt"
    mineru_bbox_content_coverage: float = 0.92  # used to infer full-page bbox canvas size from content extents

    # LLM (OpenAI-compatible, e.g. Qwen/DashScope)
    # LLM_PROVIDER selects which backend set to use:
    #   "vllm"     -> local vLLM server (LLM_BASE_URL=http://localhost:8001/v1)
    #   "ollama"   -> local ollama server (LLM_BASE_URL=http://localhost:11434/v1)
    #   "dashscope"-> Aliyun DashScope (LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1)
    # All other fields (LLM_MODEL, LLM_VISION_MODEL, SQ_LLM_MODEL, LLM_API_KEY) are read as-is,
    # so switching providers is just a matter of editing LLM_PROVIDER + the relevant fields.
    llm_provider: str = "vllm"
    llm_api_key: str = ""
    llm_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    llm_model: str = "qwen3.5-flash"
    llm_vision_model: str = "qwen-vl-plus"
    # Wiki knowledge base (replaces Milvus RAG + hardcoded gb_standard_path)
    wiki_path: str = "./wiki"  # path to LLM Wiki directory
    wiki_search_limit: int = 3  # max pages to return per search

    # Streaming / batching
    pagination: int = 32

    # Rule documents
    rule_docs_dir: str = "./app/data/rule_docs"
    rule_context_max_chars: int = 3000

    
    # MySQL 数据库 (替换原 PostgreSQL 配置, 项目已全面迁移 MySQL 8.0)
    # 兼容旧名: pg_host/pg_port 等仍可读 (pydantic-settings 自动从 .env 读)
    db_type: str = "mysql"  # 仅 "mysql" 保留
    db_host: str = "127.0.0.1"
    db_port: int = 3306
    db_database: str = "special_operations"
    db_user: str = "root"
    db_password: str = ""

    # 兼容别名 (旧 .env 里可能还有 PG_HOST 等, 自动 fallback)
    # 用 property 让旧字段名也能读, 但写入仍用 db_*

    # SmartQuery (NL2SQL 智能问数，内嵌版，原 SQLAgent 已迁移集成)
    sq_llm_model: str = "qwen-flash"  # 智能问数使用的 LLM 模型
    sq_llm_temperature: float = 0.2
    sq_llm_max_tokens: int = 14000
    sq_embedding_provider: str = "jina"  # jina | qwen | bge
    sq_embedding_api_url: str = "http://10.8.0.100:38898/v1/embeddings"
    sq_embedding_api_key: str = ""
    sq_embedding_model_name: str = ""
    sq_milvus_uri: str = "http://10.8.0.100:39530"
    sq_milvus_metric_type: str = "COSINE"
    sq_agent_recursion_limit: int = 500
    sq_dialect: str = "PostgreSQL"
    sq_language: str = "zh-CN"

    # CORS
    cors_origins: str = "*"  # comma-separated, e.g. "http://localhost:35173,http://192.168.1.100:35173"

    # Settings 配置 - 必须在 Settings class 内部才生效
    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parent.parent / ".env"),
        case_sensitive=False,
        extra="ignore",
    )


# pydantic-settings 2.5.2: 显式传 _env_file 触发 .env 加载 (model_config 里的 env_file 经常被忽略)
settings = Settings(_env_file=str(Path(__file__).resolve().parent.parent / ".env"))
