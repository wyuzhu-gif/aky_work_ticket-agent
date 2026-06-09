"""
SmartQuery 管理路由：LLM 配置、DB 配置、训练数据管理
不再代理 SQLAgent，直接操作内嵌 SmartQuery
支持配置持久化到 SQLite + 运行时热切换
"""
import logging
from fastapi import APIRouter, HTTPException, Request
from typing import Optional

from smart_query.service import get_vanna, is_initialized

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/sqlagent", tags=["sqlagent-admin"])


# ──────────────── LLM Config ────────────────

@router.get("/llm-config")
async def get_llm_config():
    """获取当前 LLM 配置（优先从 SQLite 读取，脱敏 api_key）"""
    from smart_query.config_store import get_llm_config as _get_llm
    from config.config import settings

    # 先看 SQLite 有没有持久化配置
    stored = _get_llm()
    if stored and stored.get("base_url"):
        return {"configured": True, **stored}

    # 回退到 settings
    return {
        "configured": bool(settings.llm_base_url),
        "api_key": "******" if settings.llm_api_key else "",
        "base_url": settings.llm_base_url,
        "model_name": settings.sq_llm_model,
        "temperature": settings.sq_llm_temperature,
        "max_tokens": settings.sq_llm_max_tokens,
    }


@router.put("/llm-config")
async def set_llm_config(request: Request):
    """更新 LLM 配置：保存到 SQLite + 热切换"""
    body = await request.json()
    logger.info(f"LLM config update: model={body.get('model_name')}")

    from smart_query.config_store import save_llm_config
    from config.config import settings

    # 1. 持久化到 SQLite
    kv = save_llm_config(body)

    # 2. 更新运行时 settings
    for settings_key, value in kv.items():
        setattr(settings, settings_key, value)

    # 3. 热切换 LLM（仅当已初始化时）
    if is_initialized():
        try:
            from smart_query.service import reconnect_llm
            reconnect_llm(
                api_key=settings.llm_api_key,
                base_url=settings.llm_base_url,
                model=settings.sq_llm_model,
                temperature=settings.sq_llm_temperature,
                max_tokens=settings.sq_llm_max_tokens,
            )
        except Exception as e:
            logger.error(f"LLM hot-swap failed: {e}")
            # 不抛异常，配置已保存，下次启动生效

    return {"configured": True, **_mask_api_key(kv)}


@router.post("/llm-test")
async def test_llm(request: Request):
    """测试 LLM 连接"""
    body = await request.json()
    try:
        from langchain_openai import ChatOpenAI
        api_key = body.get("api_key", "")
        base_url = body.get("base_url", "")
        model = body.get("model_name", "qwen-flash")

        # 如果 api_key 是脱敏的，用当前 settings 的
        if not api_key or api_key == "******":
            from config.config import settings
            api_key = settings.llm_api_key
            if not base_url:
                base_url = settings.llm_base_url

        llm = ChatOpenAI(
            model=model,
            openai_api_key=api_key,
            openai_api_base=base_url,
            max_tokens=10,
        )
        result = llm.invoke("Hi")
        return {"success": True, "message": "LLM 连接正常", "response_length": len(result.content)}
    except Exception as e:
        return {"success": False, "message": f"LLM 测试失败: {str(e)}"}


# ──────────────── DB Config ────────────────

@router.get("/db-config")
async def get_db_config():
    """获取当前数据库配置（优先从 SQLite 读取，脱敏密码）"""
    from smart_query.config_store import get_db_config as _get_db
    from config.config import settings

    # 先看 SQLite
    stored = _get_db()
    if stored and stored.get("host"):
        return {"configured": True, **_mask_password(stored)}

    # 回退到 settings
    return {
        "configured": bool(settings.db_host and settings.db_host != "localhost"),
        "db_type": "mysql",
        "host": settings.db_host,
        "port": settings.db_port,
        "dbname": settings.db_database,
        "username": settings.db_user,
        "password": "******" if settings.db_password else "",
    }


@router.put("/db-config")
async def set_db_config(request: Request):
    """更新数据库配置：保存到 SQLite + 热重连"""
    body = await request.json()
    logger.info(f"DB config update: {body.get('host')}:{body.get('port')}/{body.get('dbname')}")

    from smart_query.config_store import save_db_config
    from config.config import settings

    # 1. 持久化到 SQLite
    kv = save_db_config(body)

    # 2. 更新运行时 settings
    for settings_key, value in kv.items():
        setattr(settings, settings_key, value)

    # 3. 热重连（仅当已初始化时）
    if is_initialized():
        try:
            from smart_query.service import reconnect_db
            reconnect_db(
                pg_host=settings.db_host,
                pg_port=settings.db_port,
                pg_database=settings.db_database,
                pg_user=settings.db_user,
                pg_password=settings.db_password,
            )
        except Exception as e:
            logger.error(f"DB hot-reconnect failed: {e}")
            return {"configured": True, "reconnected": False, "error": str(e)}

    return {"configured": True, "reconnected": True}


@router.post("/db-test")
async def test_db(request: Request):
    """测试数据库连接（使用前端提交的参数）"""
    body = await request.json()
    try:
        import pymysql
        from config.config import settings

        host = body.get("host") or settings.db_host
        port = body.get("port") or settings.db_port
        user = body.get("username") or settings.db_user
        password = body.get("password") or settings.db_password
        dbname = body.get("dbname") or settings.db_database

        # 密码脱敏时回退到 settings
        if password == "******":
            password = settings.db_password

        connection = pymysql.connect(
            host=host, port=int(port),
            user=user, password=password,
            db=dbname,
            charset="utf8mb4",
            connect_timeout=5,
        )
        connection.close()
        return {"success": True, "message": "数据库连接正常"}
    except Exception as e:
        return {"success": False, "message": f"数据库连接失败: {str(e)}"}


# ──────────────── Training Data ────────────────

@router.get("/training")
async def get_training(training_type: Optional[str] = None):
    """获取训练数据"""
    if not is_initialized():
        raise HTTPException(status_code=503, detail="SmartQuery 未初始化")

    try:
        import pandas as pd
        vn = get_vanna()
        df = vn.get_training_data()

        # 类型推断：优先用 id 后缀，比内容启发式更可靠
        def extract_data_type(row):
            rid = str(row.get('id', ''))
            if rid.endswith('-sql'):
                return 'sql'
            elif rid.endswith('-ddl'):
                return 'ddl'
            elif rid.endswith('-doc'):
                return 'documentation'
            # fallback：内容启发式
            if 'question' in row.index and pd.notna(row.get('question')) and row['question']:
                return 'sql'
            elif 'content' in row.index and pd.notna(row.get('content')) and 'CREATE TABLE' in str(row['content']).upper():
                return 'ddl'
            elif 'content' in row.index and pd.notna(row.get('content')):
                return 'documentation'
            else:
                return 'unknown'

        df['training_data_type'] = df.apply(extract_data_type, axis=1)

        # 为 SQL 类型数据补充 sql 字段（Milvus 返回的 content 即 SQL 语句）
        if 'training_data_type' in df.columns:
            mask = df['training_data_type'] == 'sql'
            if 'sql' not in df.columns:
                df['sql'] = None
            df.loc[mask & df['content'].notna() & df['sql'].isna(), 'sql'] = df.loc[mask & df['content'].notna() & df['sql'].isna(), 'content']

        if training_type:
            suffix_map = {
                'sql': '-sql',
                'ddl': '-ddl',
                'doc': '-doc',
                'documentation': '-doc',
            }
            suffix = suffix_map.get(training_type.lower())
            if suffix:
                df = df[df['id'].astype(str).str.endswith(suffix)]

        # 返回前端期望的字段：training_data_type, question, content, sql
        out_cols = ['id', 'training_data_type', 'question', 'content', 'sql']
        available_cols = [c for c in out_cols if c in df.columns]
        df_out = df[available_cols]

        return {
            "success": True,
            "total": len(df_out),
            "data": df_out.to_dict(orient='records'),
        }

    except Exception as e:
        logger.error(f"Get training data error: {e}")
        raise HTTPException(status_code=500, detail=f"获取训练数据失败: {str(e)}")


@router.post("/training/add")
async def add_training(request: Request):
    """添加训练数据"""
    if not is_initialized():
        raise HTTPException(status_code=503, detail="SmartQuery 未初始化")

    try:
        body = await request.json()
        data_type = body.get("data_type") or body.get("training_type")
        content = body.get("content") or body.get("sql")  # 兼容 content 和 sql 字段
        question = body.get("question")
        sql = body.get("sql")  # SQL 类型专用

        vn = get_vanna()
        ids = None

        if data_type == "sql":
            if not question:
                raise HTTPException(status_code=400, detail="SQL 类型需要 question 参数")
            sql_text = sql or content  # 优先用 sql 字段，兼容 content
            if not sql_text:
                raise HTTPException(status_code=400, detail="SQL 类型需要 sql 或 content 参数")
            ids = [vn.add_question_sql(question=question, sql=sql_text)]
        elif data_type == "ddl":
            ids = vn.add_ddl(content)
            if isinstance(ids, str):
                ids = [ids]
        elif data_type == "documentation":
            ids = vn.add_documentation(content)
            if isinstance(ids, str):
                ids = [ids]
        else:
            raise HTTPException(status_code=400, detail="无效的 data_type，必须是 sql/ddl/documentation")

        return {
            "success": True,
            "message": f"成功添加 {len(ids)} 条 {data_type} 训练数据",
            "ids": ids,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Add training data error: {e}")
        raise HTTPException(status_code=500, detail=f"添加训练数据失败: {str(e)}")


@router.delete("/training/{item_id}")
async def delete_training(item_id: str):
    """删除训练数据"""
    if not is_initialized():
        raise HTTPException(status_code=503, detail="SmartQuery 未初始化")

    try:
        vn = get_vanna()
        success = vn.remove_training_data(item_id)

        if success:
            return {"success": True, "message": f"已删除训练数据: {item_id}"}
        else:
            return {"success": False, "message": f"删除失败: ID 不存在或格式无效: {item_id}"}

    except Exception as e:
        logger.error(f"Delete training data error: {e}")
        raise HTTPException(status_code=500, detail=f"删除训练数据失败: {str(e)}")


# ──────────────── Agent Config ────────────────

@router.get("/agent-config")
async def get_agent_config():
    """获取 Agent 配置"""
    from config.config import settings
    return {
        "recursion_limit": settings.sq_agent_recursion_limit,
        "dialect": settings.sq_dialect,
        "language": settings.sq_language,
    }


@router.put("/agent-config")
async def set_agent_config(request: Request):
    """更新 Agent 配置"""
    body = await request.json()
    logger.info(f"Agent config update requested: {body}")
    return await get_agent_config()


# ──────────────── Helpers ────────────────

def _mask_api_key(kv: dict) -> dict:
    """api_key 脱敏"""
    result = {}
    for k, v in kv.items():
        if "api_key" in k and isinstance(v, str) and len(v) > 8:
            result[k] = "******"
        else:
            result[k] = v
    return result


def _mask_password(d: dict) -> dict:
    """密码脱敏"""
    result = dict(d)
    if "password" in result and isinstance(result["password"], str) and len(result["password"]) > 3:
        result["password"] = "******"
    return result
