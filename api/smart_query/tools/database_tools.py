"""
数据库相关工具模块
包含：数据库连接、表结构查询、SQL 执行、语法校验等

迁移自 SQLAgent-dev: backend/vanna/src/Improve/tools/database_tools.py
改动：import 路径从 ..shared 改为 ..clients（适配 smart_query 包结构）
"""

import logging
logger = logging.getLogger(__name__)
import threading
import time
import re
import pandas as pd
from langchain.tools import tool  # type: ignore

# 导入共享上下文（统一管理）
from ..clients import get_vanna_client, set_last_query_result


# 全局互斥锁，防止并发执行 SQL
_sql_execution_lock = threading.Lock()


@tool
def get_all_tables_info() -> str:
    """直接从PostgreSQL数据库获取所有表及其列信息
    
    Returns:
        所有表的结构信息（表名、列名、数据类型、注释）
    """

    vn = get_vanna_client()
    try:
        # 获取当前数据库名
        # MySQL 8.0 用 DATABASE() 替代 PG 的 current_database()
        db_query = "SELECT DATABASE()"
        db_result = vn.run_sql(db_query)
        db_name = db_result.iloc[0, 0] or "(未选库)"

        # 查询所有表的详细信息 (MySQL 信息架构)
        #   * table_schema 用 DATABASE() (PG 用 'public')
        #   * 表注释用 information_schema.tables.TABLE_COMMENT (PG 用 obj_description())
        tables_query = """
        SELECT
            t.table_name,
            t.table_comment
        FROM information_schema.tables t
        WHERE t.table_schema = DATABASE()
        ORDER BY t.table_name
        """

        tables_df = vn.run_sql(tables_query)

        if tables_df.empty:
            return f"Database {db_name} has no tables"

        result_parts = [f"数据库: {db_name}"]
        result_parts.append(f"表数量: {len(tables_df)}\n")

        # 遍历每个表，获取列信息
        for _, table_row in tables_df.iterrows():
            table_name = table_row['table_name']
            table_comment = table_row['table_comment'] or '无描述'

            # 获取表的列信息 (MySQL 信息架构)
            #   * 列注释用 information_schema.columns.COLUMN_COMMENT (PG 用 col_description())
            #   * ordinal_position 列在 MySQL 8.0 才有
            columns_query = f"""
            SELECT
                column_name,
                data_type,
                is_nullable,
                column_default,
                column_comment
            FROM information_schema.columns
            WHERE table_schema = DATABASE()
              AND table_name = '{table_name}'
            ORDER BY ordinal_position
            """
            columns_df = vn.run_sql(columns_query)
            
            result_parts.append(f"\n{'='*60}")
            result_parts.append(f"表名: {table_name}")
            result_parts.append(f"说明: {table_comment}")
            result_parts.append(f"列数: {len(columns_df)}")
            result_parts.append("-" * 60)
            
            # 格式化列信息
            for _, col in columns_df.iterrows():
                col_info = f"  • {col['column_name']}"
                col_info += f" ({col['data_type']})"
                
                if col['is_nullable'] == 'NO':
                    col_info += " [NOT NULL]"
                
                if pd.notna(col['column_default']):
                    col_info += f" [默认: {col['column_default']}]"
                
                if col['column_comment']:
                    col_info += f"\n    说明: {col['column_comment']}"
                
                result_parts.append(col_info)
        
        return "\n".join(result_parts)
        
    except Exception as e:
        return f"Failed to get table information: {str(e)}"


# ==================== SQL 执行工具（核心）====================

@tool
def execute_sql(sql: str) -> str:
    """执行 SQL 查询并返回结果
    
    重要: 一次只能执行一个SQL，不要并发调用此工具！
    技术保障: 内部使用互斥锁强制串行执行
    自动分割: 如果传入多条SQL（用分号分隔），会自动逐条执行
    
    Args:
        sql: SQL 查询语句（支持单条或多条，用分号分隔）
        
    Returns:
        查询结果摘要
    """
    # 使用互斥锁强制串行执行，防止并发破坏数据库连接
    with _sql_execution_lock:
        vn = get_vanna_client()
        
        # ==================== 智能分割多条 SQL ====================
        # 移除注释并按分号分割
        
        # 移除单行注释（-- 开头）
        sql_no_comments = re.sub(r'--[^\n]*', '', sql)
        
        # 按分号分割（忽略空白语句）
        sql_statements = [
            stmt.strip() 
            for stmt in sql_no_comments.split(';') 
            if stmt.strip()
        ]
        
        # 如果检测到多条 SQL，给出警告并逐条执行
        if len(sql_statements) > 1:
            logger.warning(f"Detected {len(sql_statements)} SQL statements, will execute one by one...")
            
            all_results = []
            for i, stmt in enumerate(sql_statements, 1):
                logger.info(f"\nExecuting {i}/{len(sql_statements)} SQL...")
                result = _execute_single_sql(vn, stmt, max_retries=3)
                all_results.append(f"=== 查询 {i} ===\n{result}")
            
            return "\n\n".join(all_results)
        else:
            # 单条 SQL，直接执行
            return _execute_single_sql(vn, sql_statements[0] if sql_statements else sql, max_retries=3)


def _execute_single_sql(vn, sql: str, max_retries: int = 3) -> str:
    """执行单条 SQL（内部函数）"""
    retry_delay = 1  # 秒
    
    for attempt in range(max_retries):
        try:
            df = vn.run_sql(sql)
            
            # 检查返回值是否为 None
            if df is None:
                return f"""SQL执行失败: 查询返回 None

可能原因:
1. SQL中包含注释被过滤后变成空语句
2. 数据库连接返回空结果
3. vanna.run_sql() 内部错误

原始SQL:
{sql[:500]}...

建议: 移除SQL中的注释（--），只保留纯SQL语句"""
            
            row_count = len(df)

            # 缓存 DataFrame 到全局变量（供 API 层提取）
            set_last_query_result(df)
            logger.info(f"[execute_sql] 已缓存查询结果 DataFrame，行数: {row_count}")

            # 构建结果摘要
            result_summary = f"查询成功\n"
            result_summary += f"返回行数: {row_count}\n"
            result_summary += f"列名: {', '.join(df.columns.tolist())}\n"

            if row_count > 0:
                numeric_cols = df.select_dtypes(include=['number']).columns.tolist()
                all_cols = df.columns.tolist()
                # 自动推断分类列（字符串、对象类型）
                category_cols = df.select_dtypes(include=['object', 'string', 'category']).columns.tolist()

                # ---- 统计摘要（LLM 直接引用，禁止自行计数）----
                result_summary += "\n=== 统计摘要（请直接引用以下数据，不要自行计数或计算百分比）===\n"

                # 数值列统计
                if numeric_cols:
                    result_summary += "\n[数值列统计]\n"
                    for col in numeric_cols:
                        try:
                            total = df[col].sum()
                            avg = df[col].mean()
                            mx = df[col].max()
                            mn = df[col].min()
                            result_summary += f"  {col}: 总计={total}, 平均={avg:.2f}, 最大={mx}, 最小={mn}\n"
                        except Exception:
                            pass

                # 分类列分布
                if category_cols:
                    result_summary += "\n[分类列分布]\n"
                    for col in category_cols:
                        try:
                            vc = df[col].value_counts()
                            result_summary += f"  {col} 分布（共{len(vc)}类）:\n"
                            for val, cnt in vc.items():
                                pct = cnt / row_count * 100
                                result_summary += f"    {val}: {cnt}条 ({pct:.1f}%)\n"
                        except Exception:
                            pass

                # 简单场景自动算百分比（一个分类列 + 一个数值列）
                if len(numeric_cols) == 1 and len(category_cols) >= 1:
                    cat_col = category_cols[0]
                    num_col = numeric_cols[0]
                    total = df[num_col].sum()
                    if total and total > 0:
                        result_summary += f"\n[{cat_col} 按 {num_col} 占比]\n"
                        for _, row in df.iterrows():
                            val = row[cat_col]
                            num = row[num_col]
                            pct = num / total * 100
                            result_summary += f"  {val}: {num} ({pct:.1f}%)\n"

                result_summary += f"\n=== 原始数据（前5行）===\n{df.head(5).to_string()}\n"
            else:
                result_summary += "查询结果为空\n\n"
                result_summary += "⚠️ 查询结果为空！可能原因及建议：\n"
                result_summary += "1. WHERE 条件中的值不存在（如猜测了不存在的区域名）→ 先用 SELECT DISTINCT 查看该列的实际值\n"
                result_summary += "2. LIKE 模式不匹配 → 改用更宽泛的条件或先查看实际数据\n"
                result_summary += "3. 表中确实没有数据 → 换一张表查询\n\n"
                result_summary += "重要：如果连续2次查询结果为空，请停止修改SQL并直接告诉用户\"查询结果为空，可能该分类维度在数据中不存在\"。不要继续重试！"

            # 成功执行，返回结果
            return result_summary
            
        except Exception as e:
            error_msg = str(e)
            
            # 特殊处理：'NoneType' object is not iterable（df 为 None）
            if "'NoneType' object is not iterable" in error_msg or "NoneType" in error_msg:
                return f"""SQL执行失败: vn.run_sql() 返回 None

错误信息: {error_msg}

可能原因:
1. SQL 包含注释（--）导致解析失败
2. 数据库查询返回空但 vanna 未正确处理
3. 数据库连接状态异常

原始SQL（含注释）:
{sql[:500]}...

解决方案: 移除 SQL 中的注释，只保留纯 SQL 语句
例如: 
  -- 这是注释 SELECT * FROM table;
  SELECT * FROM table;"""
            
            # 其他错误
            else:
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    continue  # 重试
                else:
                    return f"""SQL执行失败: {error_msg}

SQL语句:
{sql[:200]}...

已尝试 {max_retries} 次执行，仍然失败。

请检查:
1. SQL语法是否正确
2. 表名、列名是否存在
3. 数据类型是否匹配
4. JOIN条件是否正确"""
    
    # 理论上不会到达这里（循环中已包含所有返回情况）
    return "SQL执行失败: 未知错误"


@tool
def validate_sql_syntax(sql: str) -> str:
    """验证 SQL 语法是否正确（用 PG EXPLAIN 真实验证，不执行查询）

    Args:
        sql: SQL 查询语句

    Returns:
        语法验证结果
    """
    # 安全性检查
    dangerous_keywords = ['INSERT', 'UPDATE', 'DELETE', 'DROP', 'ALTER',
                         'TRUNCATE', 'CREATE', 'GRANT', 'REVOKE']

    sql_upper = sql.upper()
    for keyword in dangerous_keywords:
        if re.search(rf'\b{keyword}\b', sql_upper):
            return f"安全风险: SQL包含危险操作 {keyword}"

    # 基础语法检查
    if not sql.strip():
        return "SQL为空"

    if not re.search(r'\bSELECT\b', sql_upper):
        return "SQL必须以SELECT开头"

    # 括号匹配检查
    if sql.count('(') != sql.count(')'):
        return "括号不匹配"

    # === 真实验证: 用 MySQL EXPLAIN 验证语法 (不执行查询, 拿执行计划) ===
    # 直接用 pymysql 调 MySQL (不依赖 vanna, 因为 vanna 需先 connect_to_mysql)
    # 这样 LLM 就能拿到真实错误信息 (语法错/表/列不存在/聚合错)
    #
    # 权限错误降级 (1345/1142): 只读账号常无 EXPLAIN 权限,
    # 这种错应该静默降级到基础验证, 不告诉 LLM "SQL 错了",
    # 否则 LLM 会以为是 SQL 问题, 一直改 SQL 死循环.
    PERMISSION_ERRNOS = {
        1044,  # Access denied for user
        1045,  # Access denied for user (auth)
        1142,  # SHOW VIEW command denied
        1345,  # EXPLAIN/SHOW can not be issued; lacking privileges for underlying table
        2006,  # MySQL server has gone away (连接断)
    }

    try:
        # 用 ; 分割, 只验证第一条
        sql_clean = re.sub(r'--[^\n]*', '', sql)
        first_stmt = sql_clean.split(';')[0].strip()
        if not first_stmt:
            return "SQL为空 (无第一条语句)"

        # 同步用 pymysql (不依赖 vanna)
        import pymysql
        from config.config import settings
        conn = pymysql.connect(
            host=settings.db_host,
            port=settings.db_port,
            db=settings.db_database,
            user=settings.db_user,
            password=settings.db_password,
            charset="utf8mb4",
            connect_timeout=5,
        )
        try:
            with conn.cursor() as cur:
                # EXPLAIN 不真执行, 只解析 + 拿执行计划
                # MySQL 8.0 也支持 EXPLAIN <statement>
                cur.execute(f"EXPLAIN {first_stmt}")
                rows = cur.fetchall()
                plan_lines = []
                for row in rows[:5]:  # 只取前 5 行
                    plan_lines.append(str(row))
                plan_str = '\n'.join(plan_lines)
                return f"✅ 语法验证通过 (MySQL EXPLAIN 执行计划):\n{plan_str}"
        except pymysql.Error as e:
            # 关键修复: 区分"权限错"和"真 SQL 错"
            errno = e.args[0] if e.args else None
            if errno in PERMISSION_ERRNOS:
                # 静默降级 - 不告诉 LLM "SQL 错了"
                logger.info(
                    f"validate_sql_syntax: EXPLAIN 权限不足 (errno={errno}), "
                    f"静默降级到基础验证. 实际 SQL 语法需 execute_sql 时验证."
                )
                return "⚠️ EXPLAIN 权限不足 (账号无权限验证语法), 已跳过此步。请依赖 execute_sql 的真实执行结果判断 SQL 是否正确。"
            # 真错误: 返回错误信息 (MySQL 解析器报语法/表/列/聚合错)
            err_msg = str(e).strip()
            if len(err_msg) > 500:
                err_msg = err_msg[:500] + "..."
            return f"❌ 语法验证失败 (MySQL EXPLAIN 报错):\n{err_msg}\n\n请检查:\n1. SQL 语法 (全角逗号/括号/引号)\n2. 表名/列名是否正确 (参考 get_table_schema 返回的 DDL)\n3. 聚合/GROUP BY 是否完整\n4. 不要使用 -- 注释"
        finally:
            conn.close()
    except Exception as e:
        # 兜底: 如果连接失败, 走旧的"基础验证"
        logger.warning(f"EXPLAIN 验证失败, 降级到基础验证: {e}")
        return "语法检查通过（基础验证，EXPLAIN 不可用）"
