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
        model = body.get("model_name", "qwen3.6:35b")  # 默认本地 ollama 模型, 内网部署不用 qwen-flash (云端)

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
        # ⚠️ 兼容 content 列可能不存在 (FallbackVanna / 旧版) 的场景
        if 'training_data_type' in df.columns and 'content' in df.columns:
            mask = df['training_data_type'] == 'sql'
            if 'sql' not in df.columns:
                df['sql'] = None
            sel = mask & df['content'].notna() & df['sql'].isna()
            df.loc[sel, 'sql'] = df.loc[sel, 'content']

        if training_type:
            # 兼容两种 id 风格:
            #   - uuid-{sql|ddl|doc}  (add_question_sql/add_ddl/add_documentation)
            #   - {md5_hash}-hash     (add_question_sql/_get_content_hash dedup 后的批量)
            suffix_map = {
                'sql': ['-sql', '-hash'],       # hash 后缀的也是 SQL (跟 ddl/doc 同源)
                'ddl': ['-ddl', '-hash'],
                'doc': ['-doc', '-hash'],
                'documentation': ['-doc', '-hash'],
            }
            suffixes = suffix_map.get(training_type.lower())
            if suffixes:
                mask = df['id'].astype(str).str.endswith(tuple(suffixes))
                df = df[mask]

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

# ============================================================
# Phase 1: Raw Query 接口 (2026-06-25)
# 数据驱动架构: SQL → rows → (返回给上层 LLM/Hermes)
# 禁止: Report LLM / markdown / summary / chartconfig LLM / prompt 结构设计
# 允许: SQL 执行 + DataFrame→JSON + infer_chart(rows) + stats aggregation
# ============================================================

from pydantic import BaseModel, Field


class RawQueryRequest(BaseModel):
    question: str = Field(..., description="用户自然语言问题")
    auto_train: bool = Field(default=False, description="成功后是否自动训练 (默认 False, raw 接口只读)")


def _compute_numeric_stats(rows: list) -> dict:
    """对每列是数字的列, 自动算 min/max/avg/sum"""
    if not rows:
        return {}
    cols = list(rows[0].keys())
    stats = {}
    for col in cols:
        nums = []
        for r in rows:
            v = r.get(col)
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                nums.append(float(v))
        if nums:
            stats[col] = {
                "min": min(nums),
                "max": max(nums),
                "avg": round(sum(nums) / len(nums), 4),
                "sum": round(sum(nums), 4),
            }
    return stats


@router.post("/query/raw")
async def query_raw(req: RawQueryRequest):
    """
    Phase 1: Raw Query 接口

    返回结构化数据 (SQL + rows + chart_config + stats), 不生成文字.
    让上层 LLM (Hermes) 一次性整合分析.

    与 /api/v1/chat 的区别:
      - /api/v1/chat: SQL + Report LLM + markdown 报告 (Presentation Plane)
      - /api/v1/sqlagent/query: SQL + rows + chart (Data Plane, 此次新增)
      - /api/v1/sqlagent/chat: (未来) 报表层, 调用 query + 加 wiki + 整合
    """
    if not is_initialized():
        raise HTTPException(status_code=503, detail="SmartQuery 未初始化")

    import time
    import json as _json
    from smart_query.clients import (
        get_last_query_result, get_last_query_sql, clear_last_query_result
    )
    from routers.agent_chat import infer_chart

    start = time.time()

    # 1) 清缓存, 避免读到上次的结果
    clear_last_query_result()

    # 2) 跑 LangChain Agent 拿 SQL + 执行结果 (复用 chat.py 的 agent 流程)
    try:
        from smart_query.service import get_agent
        agent = get_agent()
        cfg = {
            "configurable": {"thread_id": f"raw-{int(time.time()*1000)}"},
            "recursion_limit": 100,
        }
        # 触发 NL2SQL + execute_sql tool, 会写缓存
        for _ in agent.stream(
            {"messages": [{"role": "user", "content": req.question}]},
            stream_mode="values",
            config=cfg,
        ):
            pass  # 不需要中间 event, 只要触发 execute_sql 写缓存
    except Exception as e:
        return {
            "error": f"Agent 执行失败: {e}",
            "sql": None,
            "rows": [],
            "columns": [],
            "chart_config": None,
            "stats": {"row_count": 0, "numeric_summary": {}},
            "execution_time": round(time.time() - start, 3),
        }

    # 3) 从缓存拿 DataFrame + SQL
    df = get_last_query_result()
    sql = get_last_query_sql()

    if df is None or len(df) == 0:
        return {
            "error": "未取到 SQL 数据 (Agent 可能没调 execute_sql)",
            "sql": sql,
            "rows": [],
            "columns": [],
            "chart_config": None,
            "stats": {"row_count": 0, "numeric_summary": {}},
            "execution_time": round(time.time() - start, 3),
        }

    # 4) DataFrame → rows (list of dict) + columns
    try:
        rows_json = _json.loads(df.to_json(orient="records", force_ascii=False))
    except Exception as e:
        return {
            "error": f"DataFrame 序列化失败: {e}",
            "sql": sql,
            "rows": [],
            "columns": [],
            "chart_config": None,
            "stats": {"row_count": 0, "numeric_summary": {}},
            "execution_time": round(time.time() - start, 3),
        }

    columns = list(df.columns)
    stats = {
        "row_count": len(rows_json),
        "column_count": len(columns),
        "numeric_summary": _compute_numeric_stats(rows_json),
    }

    # 5) infer_chart 派生 chart_config (后端确定性, 不让 LLM 参与)
    #    rows_json 是对象数组 [{"col": val}, ...], 转成数组数组 [[val, val], ...]
    rows_positional = [[r.get(c) for c in columns] for r in rows_json]
    chart_config = infer_chart({"columns": columns, "rows": rows_positional})

    # 6) 语义提取 (Phase 4.1, 2026-06-25 用户拍板):
    #    NL2SQL 是最了解数据语义的地方 — SQL 字段天然映射到 topic
    #    让 raw API 直接返回 topics + recommended_wiki, agent 不用猜
    from routers.agent_chat_rules import analyze_rows, TOPIC_REGISTRY
    analysis = analyze_rows(rows_json, columns)
    topics = analysis["topics"]
    risk_flags = analysis["risk_flags"]
    # topic → recommended_wiki (去重)
    recommended_wiki_set = set()
    for t in topics:
        for std in TOPIC_REGISTRY.get(t, []):
            recommended_wiki_set.add(std)
    recommended_wiki = sorted(recommended_wiki_set)
    # risk_type 标记 (从 risk_flags 提取)
    risk_types = []
    if analysis["metadata"].get("has_high_danger"):
        risk_types.append("重大隐患")
    for rf in risk_flags:
        if "增长" in rf:
            risk_types.append("持续增长")
        if "高发" in rf:
            risk_types.append("集中爆发")
    semantic = {
        "topics": topics,
        "risk_types": risk_types,
        "risk_flags": risk_flags,
        "recommended_wiki": recommended_wiki,
    }
    logger.info(
        f"query_raw: topics={topics}, risk_types={risk_types}, "
        f"recommended_wiki={recommended_wiki}"
    )

    # DEBUG D-2 (2026-06-25 临时): dump 接口返回结构, 验证 Phase 1 输出
    import os as _os
    if _os.environ.get("TICKET_DEBUG_DUMP") == "1":
        try:
            with open("/tmp/ticket_query_raw_result.json", "w", encoding="utf-8") as f:
                _json.dump({
                    "error": None,
                    "sql": sql,
                    "rows_count": len(rows_json),
                    "rows_sample": rows_json[:3],
                    "columns": columns,
                    "chart_config_type": chart_config.get("type") if chart_config else None,
                    "stats": stats,
                }, f, ensure_ascii=False, indent=2)
            logger.info("D DEBUG: dumped /api/v1/sqlagent/query/raw result to /tmp/ticket_query_raw_result.json")
        except Exception as _e:
            logger.warning(f"D DEBUG dump failed: {_e}")

    return {
        "error": None,
        "sql": sql,
        "rows": rows_json,
        "columns": columns,
        "chart_config": chart_config,
        "stats": stats,
        "semantic": semantic,  # Phase 4.1: topics + risk_types + recommended_wiki
        "execution_time": round(time.time() - start, 3),
    }
