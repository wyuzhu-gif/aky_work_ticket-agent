"""
PostgreSQL 异步客户端（asyncpg）。

表已在外部创建，此模块只负责连接池管理。
"""

from __future__ import annotations

from typing import Any

import asyncpg

from common.logger import get_logger

logger = get_logger(__name__)


class PgClient:
    """PostgreSQL async client backed by an asyncpg connection pool."""

    def __init__(self, dsn: str):
        self._dsn = dsn
        self._pool: asyncpg.Pool | None = None

    async def init(self) -> None:
        self._pool = await asyncpg.create_pool(self._dsn, min_size=2, max_size=10, ssl=False)
        logger.info("PostgreSQL connection pool created.")

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()

    async def execute(self, query: str, *args: Any) -> str:
        async with self._pool.acquire() as conn:
            return await conn.execute(query, *args)

    async def fetch(self, query: str, *args: Any) -> list[asyncpg.Record]:
        async with self._pool.acquire() as conn:
            return await conn.fetch(query, *args)

    async def fetchrow(self, query: str, *args: Any) -> asyncpg.Record | None:
        async with self._pool.acquire() as conn:
            return await conn.fetchrow(query, *args)

    async def fetchval(self, query: str, *args: Any) -> Any:
        async with self._pool.acquire() as conn:
            return await conn.fetchval(query, *args)
