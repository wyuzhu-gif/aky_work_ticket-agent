"""
MySQL 异步客户端 (aiomysql)。

表已在外部创建，此模块只负责连接池管理。

替换: 原 PostgreSQL asyncpg 实现 (pg_client.py)。

API 兼容说明 (相对 asyncpg):
  - acquire() / fetchrow() / fetch() / execute() / fetchval() 行为一致
  - execute() 返回 "ROWCOUNT n" 字符串 (替代 PG 的 "DELETE n"),
    因为 aiomysql.cursor.execute() 不返回状态字符串
  - fetchrow 返回 dict (DictCursor), fetch 返回 list[dict]
  - 新增 insert_and_return_id(): INSERT 拿自增 ID (替代 PG 的 RETURNING id)
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse, unquote

import aiomysql

from common.logger import get_logger

logger = get_logger(__name__)


class MysqlClient:
    """MySQL async client backed by an aiomysql connection pool."""

    def __init__(self, host: str, port: int, user: str, password: str, database: str):
        """
        直接接 host/port/user/password/database, 不依赖 DSN 解析。
        (避免 urlparse 处理密码里特殊字符的坑)
        """
        self._host = host
        self._port = port
        self._user = user
        self._password = password
        self._database = database
        self._pool: aiomysql.Pool | None = None

    async def init(self) -> None:
        """创建连接池. charset 强制 utf8mb4 (中文/表情兼容)."""
        self._pool = await aiomysql.create_pool(
            host=self._host, port=self._port,
            user=self._user, password=self._password,
            db=self._database, minsize=2, maxsize=10,
            charset="utf8mb4", autocommit=True,
        )
        logger.info(
            f"MySQL connection pool created: {self._host}:{self._port}/{self._database}"
        )

    async def close(self) -> None:
        if self._pool:
            self._pool.close()
            await self._pool.wait_closed()

    # ─── 接口兼容 asyncpg ───

    async def execute(self, query: str, *args: Any) -> str:
        """
        执行 INSERT/UPDATE/DELETE, 返回 'ROWCOUNT n' 形式的字符串.
        permits_repository 里的 generic_delete 用 'DELETE 1' in result 判断;
        改为 'ROWCOUNT 1' in result 兼容.
        """
        async with self._pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(query, args)
                return f"ROWCOUNT {cur.rowcount}"

    async def fetch(self, query: str, *args: Any) -> list[dict]:
        """执行 SELECT, 返回 list[dict] (DictCursor)."""
        async with self._pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(query, args)
                rows = await cur.fetchall()
                return list(rows)

    async def fetchrow(self, query: str, *args: Any) -> dict | None:
        """执行 SELECT, 返回单行 dict 或 None."""
        async with self._pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(query, args)
                return await cur.fetchone()

    async def fetchval(self, query: str, *args: Any) -> Any:
        """执行 SELECT, 返回第一行第一列的值."""
        async with self._pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(query, args)
                row = await cur.fetchone()
                return row[0] if row else None

    # ─── MySQL 专属便捷方法 (替代 PG 的 RETURNING *) ───

    async def insert_and_return_id(self, query: str, *args: Any) -> int:
        """INSERT 后返回新行的自增 ID."""
        async with self._pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(query, args)
                return cur.lastrowid