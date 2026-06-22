"""
2026-06-22 新增: 作业票草稿仓 (前端 "暂存" / "保存到本地" 用)
- 用现有 app.db SQLite, 不引入新依赖
- 一行存一张草稿, permit_code 为主键 (无票号的临时草稿用 _draft_<timestamp>)
- permit / gas / safety / review 全部 JSON 序列化进 TEXT 列
"""
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import aiosqlite

from common.logger import get_logger
from database.db_client import SQLiteClient

logging = get_logger(__name__)


class DraftsRepository:
    def __init__(self, db_client: SQLiteClient) -> None:
        self.db_client = db_client

    async def init(self) -> None:
        await self.db_client.init_db()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    async def upsert_draft(
        self,
        permit_code: str,
        permit_type: str,
        permit: Dict[str, Any],
        gas_analyses: Optional[List[Dict[str, Any]]] = None,
        safety_checks: Optional[List[Dict[str, Any]]] = None,
        review_results: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        新增或覆盖一张草稿 (用 permit_code 当主键)
        """
        gas_analyses = gas_analyses if gas_analyses is not None else []
        safety_checks = safety_checks if safety_checks is not None else []
        review_results = review_results if review_results is not None else []

        existing = await self._fetch_by_code(permit_code)
        now = self._now()
        row = {
            "permit_code": permit_code,
            "permit_type": permit_type,
            "permit_json": json.dumps(permit, ensure_ascii=False),
            "gas_json": json.dumps(gas_analyses, ensure_ascii=False),
            "safety_json": json.dumps(safety_checks, ensure_ascii=False),
            "review_json": json.dumps(review_results, ensure_ascii=False),
            "has_review": 1 if review_results else 0,
            "created_at": existing["created_at"] if existing else now,
            "updated_at": now,
        }
        await self.db_client.store_item("permit_drafts", row)
        logging.info(
            f"upsert_draft permit_code={permit_code} type={permit_type} "
            f"gas={len(gas_analyses)} safety={len(safety_checks)} review={len(review_results)}"
        )
        return row

    async def _fetch_by_code(self, permit_code: str) -> Optional[Dict[str, Any]]:
        """permit_drafts 用 permit_code 当主键, 不走通用 retrieve_item_by_id (那个硬编码 id 列)"""
        rows = await self.db_client.execute_query(
            "SELECT * FROM permit_drafts WHERE permit_code = ?",
            (permit_code,),
        )
        return rows[0] if rows else None

    async def get_draft(self, permit_code: str) -> Optional[Dict[str, Any]]:
        row = await self._fetch_by_code(permit_code)
        if not row:
            return None
        return self._deserialize_draft(row)

    async def list_drafts(self, permit_type: Optional[str] = None) -> List[Dict[str, Any]]:
        filters: Dict[str, Any] = {}
        if permit_type:
            filters["permit_type"] = permit_type
        rows = await self.db_client.retrieve_items_by_values("permit_drafts", filters)
        # 新的在前面
        rows.sort(key=lambda r: r.get("updated_at", ""), reverse=True)
        return [self._deserialize_summary(r) for r in rows]

    async def delete_draft(self, permit_code: str) -> bool:
        existing = await self._fetch_by_code(permit_code)
        if not existing:
            return False
        async with aiosqlite.connect(self.db_client.db_path) as db:
            await db.execute(
                "DELETE FROM permit_drafts WHERE permit_code = ?",
                (permit_code,),
            )
            await db.commit()
        logging.info(f"delete_draft permit_code={permit_code}")
        return True

    # ---- serialize / deserialize helpers ----
    @staticmethod
    def _safe_loads(text: Optional[str], default):
        if not text:
            return default
        try:
            return json.loads(text)
        except Exception:
            return default

    def _deserialize_draft(self, row: Dict[str, Any]) -> Dict[str, Any]:
        """完整草稿 (加载用): 包含 permit/gas/safety/review 解析后对象"""
        return {
            "permit_code": row["permit_code"],
            "permit_type": row["permit_type"],
            "permit": self._safe_loads(row.get("permit_json"), {}),
            "gas_analyses": self._safe_loads(row.get("gas_json"), []),
            "safety_checks": self._safe_loads(row.get("safety_json"), []),
            "review_results": self._safe_loads(row.get("review_json"), []),
            "has_review": bool(row.get("has_review", 0)),
            "created_at": row.get("created_at"),
            "updated_at": row.get("updated_at"),
        }

    def _deserialize_summary(self, row: Dict[str, Any]) -> Dict[str, Any]:
        """列表用: 不解析大 JSON, 只给元信息 (permit 内取少量展示字段)"""
        permit = self._safe_loads(row.get("permit_json"), {})
        gas_count = len(self._safe_loads(row.get("gas_json"), []))
        safety_count = len(self._safe_loads(row.get("safety_json"), []))
        return {
            "permit_code": row["permit_code"],
            "permit_type": row["permit_type"],
            "permit_unit": permit.get("work_unit") or permit.get("applicant_unit") or "",
            "permit_location": permit.get("work_location") or "",
            "permit_job": permit.get("job_content") or permit.get("work_content") or "",
            "gas_count": gas_count,
            "safety_count": safety_count,
            "has_review": bool(row.get("has_review", 0)),
            "review_count": len(self._safe_loads(row.get("review_json"), [])),
            "created_at": row.get("created_at"),
            "updated_at": row.get("updated_at"),
        }
