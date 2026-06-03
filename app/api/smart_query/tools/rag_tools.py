"""
RAG 检索工具

1. get_table_schema — 从 Milvus 向量库检索 DDL/文档/历史 SQL 训练数据
2. wiki_search_tool — 从 LLM Wiki 检索法规知识（如需要）
"""

import logging
logger = logging.getLogger(__name__)
from langchain.tools import tool  # type: ignore


def _get_vanna():
    """延迟导入 vanna 客户端"""
    from ..clients import get_vanna_client
    return get_vanna_client()


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
        parts = []

        # 1. 检索相关 DDL
        try:
            related_ddl = vn.get_related_ddl(question)
            if related_ddl:
                parts.append("=== 相关表结构 (DDL) ===")
                for i, ddl in enumerate(related_ddl[:3], 1):
                    # 截断过长的 DDL
                    if len(ddl) > 2000:
                        ddl = ddl[:2000] + "\n...(截断)"
                    parts.append(f"\n[DDL {i}]\n{ddl}")
        except Exception as e:
            logger.warning(f"DDL retrieval failed: {e}")

        # 2. 检索相关文档
        try:
            related_doc = vn.get_related_documentation(question)
            if related_doc:
                parts.append("\n=== 相关业务说明 ===")
                for i, doc in enumerate(related_doc[:2], 1):
                    if len(doc) > 1500:
                        doc = doc[:1500] + "\n...(截断)"
                    parts.append(f"\n[文档 {i}]\n{doc}")
        except Exception as e:
            logger.warning(f"Documentation retrieval failed: {e}")

        # 3. 检索相关历史 SQL
        try:
            related_sql = vn.get_similar_question_sql(question)
            if related_sql:
                parts.append("\n=== 参考SQL（类似问题的历史查询）===")
                for i, item in enumerate(related_sql[:3], 1):
                    q = item.get("question", "")
                    s = item.get("sql", "")
                    parts.append(f"\n[参考 {i}] 问题: {q}\nSQL: {s}")
        except Exception as e:
            logger.warning(f"SQL retrieval failed: {e}")

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
