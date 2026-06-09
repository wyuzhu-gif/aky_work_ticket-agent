"""
RAG 检索工具
智能问数 NL2SQL agent 的 RAG 工具 - 从 Milvus 向量库检索 DDL/文档/历史 SQL 训练数据
"""

import logging
from concurrent.futures import ThreadPoolExecutor
logger = logging.getLogger(__name__)
from langchain.tools import tool  # type: ignore


def _get_vanna():
    """延迟导入 vanna 客户端"""
    from ..clients import get_vanna_client
    return get_vanna_client()


# 共享 ThreadPoolExecutor, 用于并发 3 个 Milvus 检索 (避免 LangGraph middleware 缺 async hook 问题)
_RAG_EXECUTOR = ThreadPoolExecutor(max_workers=3, thread_name_prefix="rag-retrieve")


# ==================== Milvus 向量检索工具 ====================

@tool
def get_table_schema(question: str) -> str:
    """从训练数据中检索与问题相关的表结构（DDL）、文档说明和历史SQL

    当需要了解数据库表结构、字段含义、业务规则或参考历史查询时使用此工具。
    检索内容包括：
    - DDL：建表语句，包含字段类型和注释
    - 文档：业务说明、字段取值范围、重要业务规则
    - 历史SQL：类似问题的参考查询

    Args:
        question: 用户的自然语言问题
    Returns:
        相关的表结构、业务说明和参考SQL
    """
    try:
        vn = _get_vanna()

        # 并发执行 3 个 Milvus 检索 (用 ThreadPoolExecutor 把同步 pymilvus 推到独立线程)
        # 原串行 ~6s → 并发 ~2s
        def _safe_ddl():
            try:
                return vn.get_related_ddl(question)
            except Exception as e:
                logger.warning(f"DDL retrieval failed: {e}")
                return []

        def _safe_doc():
            try:
                return vn.get_related_documentation(question)
            except Exception as e:
                logger.warning(f"Documentation retrieval failed: {e}")
                return []

        def _safe_sql():
            try:
                return vn.get_similar_question_sql(question)
            except Exception as e:
                logger.warning(f"SQL retrieval failed: {e}")
                return []

        future_ddl = _RAG_EXECUTOR.submit(_safe_ddl)
        future_doc = _RAG_EXECUTOR.submit(_safe_doc)
        future_sql = _RAG_EXECUTOR.submit(_safe_sql)
        related_ddl = future_ddl.result()
        related_doc = future_doc.result()
        related_sql = future_sql.result()

        parts = []
        if related_ddl:
            parts.append("=== 相关表结构 (DDL) ===")
            for i, ddl in enumerate(related_ddl[:3], 1):
                if len(ddl) > 2000:
                    ddl = ddl[:2000] + "\n...(截断)"
                parts.append(f"\n[DDL {i}]\n{ddl}")

        if related_doc:
            parts.append("\n=== 相关业务说明 ===")
            for i, doc in enumerate(related_doc[:2], 1):
                if len(doc) > 1500:
                    doc = doc[:1500] + "\n...(截断)"
                parts.append(f"\n[文档 {i}]\n{doc}")

        if related_sql:
            parts.append("\n=== 参考SQL（类似问题的历史查询）===")
            for i, item in enumerate(related_sql[:3], 1):
                q = item.get("question", "")
                s = item.get("sql", "")
                parts.append(f"\n[参考 {i}] 问题: {q}\nSQL: {s}")

        if not parts:
            return (
                "未在训练数据中找到相关信息。\n"
                "提示：请使用 get_all_tables_info 工具直接查询数据库获取表结构。"
            )

        return "\n".join(parts)

    except Exception as e:
        logger.warning(f"Training data search failed: {e}")
        return (
            f"训练数据检索失败: {str(e)}\n"
            "请改用 get_all_tables_info 工具获取数据库表结构。"
        )
