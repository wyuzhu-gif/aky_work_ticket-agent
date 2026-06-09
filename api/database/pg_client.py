"""
[已废弃] PostgreSQL 异步客户端 — 项目已全面迁移到 MySQL.

⚠️ 此文件保留仅为向后兼容 (2026-06 之前可能有外部脚本引用).
⚠️ 未来请直接 import database.mysql_client.MysqlClient.

替代: MysqlClient (database/mysql_client.py),基于 aiomysql.
迁移差异:
  - asyncpg.Pool → aiomysql.Pool
  - 占位符 $1/$2 → %s
  - INSERT/UPDATE 不支持 RETURNING *, 用 lastrowid 两段式
  - 'DELETE 1' → 'ROWCOUNT 1' (execute 返回值)
"""

# Re-export MysqlClient as PgClient for back-compat
from database.mysql_client import MysqlClient as PgClient  # noqa: F401