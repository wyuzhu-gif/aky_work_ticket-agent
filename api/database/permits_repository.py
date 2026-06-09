"""
作业票数据访问层 (PostgreSQL)。
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from database.pg_client import PgClient
from common.permit_models import (
    HotWorkPermit,
    HotWorkGasAnalysis,
    SafetyCheckItem,
    WorkSafetyCheck,
)
from common.logger import get_logger

logger = get_logger(__name__)

# ── 可空字段列表（insert 时排除 None） ──

_PERMIT_COLUMNS = [
    "permit_code", "work_id", "apply_unit", "apply_time",
    "work_content", "work_location", "work_level", "work_method",
    "fire_worker_info", "work_unit", "work_owner_name", "work_owner_phone",
    "gas_analysis_time", "gas_analyst_name", "gas_analysis_result",
    "related_permit_ids", "risk_identification",
    "start_time", "end_time",
    "safety_disclosure_person", "safety_disclosure_time",
    "accept_person", "accept_time", "attendant",
    "approval_owner_opinion", "approval_owner_sign", "approval_owner_time",
    "approval_unit_opinion", "approval_unit_sign", "approval_unit_time",
    "approval_safety_opinion", "approval_safety_sign", "approval_safety_time",
    "approval_fire_leader_opinion", "approval_fire_leader_sign", "approval_fire_leader_time",
    "shift_leader_check_result", "shift_leader_sign", "shift_leader_time",
    "completion_acceptance_result", "completion_acceptance_sign", "completion_acceptance_time",
    "status",
]

# Columns that are timestamp type in PG - need datetime objects
_TIMESTAMP_COLUMNS = {
    "apply_time", "gas_analysis_time", "start_time", "end_time",
    "safety_disclosure_time", "accept_time",
    "approval_owner_time", "approval_unit_time", "approval_safety_time",
    "approval_fire_leader_time", "shift_leader_time",
    "completion_acceptance_time", "create_time",
}

_GAS_COLUMNS = [
    "permit_id", "analysis_round", "sample_time",
    "representative_gas", "analysis_result", "analyst_name",
]


class PermitsRepository:
    def __init__(self, pg: PgClient):
        self._pg = pg

    # ─────────────── Permits ───────────────

    async def insert_permit(self, p: HotWorkPermit) -> HotWorkPermit:
        cols, vals = self._permit_cols_vals(p)
        placeholders = ", ".join(f"${i+1}" for i in range(len(cols)))
        col_names = ", ".join(cols)
        sql = f"INSERT INTO hot_work_permits ({col_names}) VALUES ({placeholders}) RETURNING *"
        row = await self._pg.fetchrow(sql, *vals)
        return self._row_to_permit(row)

    async def get_permit(self, permit_id: int) -> HotWorkPermit | None:
        row = await self._pg.fetchrow("SELECT * FROM hot_work_permits WHERE id = $1", permit_id)
        return self._row_to_permit(row) if row else None

    async def list_permits(self) -> list[HotWorkPermit]:
        rows = await self._pg.fetch("SELECT * FROM hot_work_permits ORDER BY create_time DESC")
        return [self._row_to_permit(r) for r in rows]

    async def delete_permit(self, permit_id: int) -> bool:
        result = await self._pg.execute("DELETE FROM hot_work_permits WHERE id = $1", permit_id)
        return "DELETE 1" in result

    async def update_permit(self, p: HotWorkPermit) -> HotWorkPermit:
        cols, vals = self._permit_cols_vals(p)
        if not p.id:
            raise ValueError("update_permit requires permit.id")
        sets = ", ".join(f"{c} = ${i+1}" for i, c in enumerate(cols))
        vals.append(p.id)
        sql = f"UPDATE hot_work_permits SET {sets} WHERE id = ${len(vals)} RETURNING *"
        row = await self._pg.fetchrow(sql, *vals)
        return self._row_to_permit(row)

    # ─────────────── Gas Analysis ───────────────

    async def insert_gas_analysis(self, g: HotWorkGasAnalysis) -> HotWorkGasAnalysis:
        cols, vals = [], []
        for c in _GAS_COLUMNS:
            v = getattr(g, c, None)
            if v is not None:
                if c in ("sample_time", "create_time"):
                    v = self._parse_ts(v)
                cols.append(c)
                vals.append(v)
        placeholders = ", ".join(f"${i+1}" for i in range(len(cols)))
        col_names = ", ".join(cols)
        sql = f"INSERT INTO hot_work_gas_analysis ({col_names}) VALUES ({placeholders}) RETURNING *"
        row = await self._pg.fetchrow(sql, *vals)
        return self._row_to_gas(row)

    async def get_gas_analyses(self, permit_id: int) -> list[HotWorkGasAnalysis]:
        rows = await self._pg.fetch(
            "SELECT * FROM hot_work_gas_analysis WHERE permit_id = $1 ORDER BY analysis_round",
            permit_id,
        )
        return [self._row_to_gas(r) for r in rows]

    async def delete_gas_analyses(self, permit_id: int) -> None:
        await self._pg.execute("DELETE FROM hot_work_gas_analysis WHERE permit_id = $1", permit_id)

    # ─────────────── Safety Check Items ───────────────

    async def list_safety_check_items(self) -> list[SafetyCheckItem]:
        rows = await self._pg.fetch("SELECT * FROM safety_check_items ORDER BY code")
        return [SafetyCheckItem(
            id=r["id"],
            code=r["code"],
            description=r["description"],
            applicable_to=list(r["applicable_to"]),
        ) for r in rows]


    # ─────────────── Safety Checks ───────────────

    async def insert_safety_check(self, permit_id: int, permit_type: str, check_item_id: int, is_confirmed: bool, confirmed_by: str | None = None) -> None:
        await self._pg.execute(
            "INSERT INTO work_safety_checks (permit_id, permit_type, check_item_id, is_confirmed, confirmed_by) VALUES ($1, $2, $3, $4, $5)",
            permit_id, permit_type, check_item_id, is_confirmed, confirmed_by,
        )

    async def delete_safety_checks(self, permit_id: int) -> None:
        await self._pg.execute("DELETE FROM work_safety_checks WHERE permit_id = $1 AND permit_type = 'HOT_WORK'", permit_id)

    async def get_safety_checks(self, permit_id: int) -> list[dict]:
        rows = await self._pg.fetch(
            "SELECT sc.*, s.code, s.description FROM work_safety_checks sc JOIN safety_check_items s ON sc.check_item_id = s.id WHERE sc.permit_id = $1 AND sc.permit_type = 'HOT_WORK'",
            permit_id,
        )
        return [dict(r) for r in rows]


    # ─────────────── Generic multi-type CRUD ───────────────

    async def generic_insert(self, table: str, data: dict) -> dict:
        """Insert a row into any table, return the row as dict."""
        cols = [k for k, v in data.items() if v is not None]
        vals = [self._convert_ts(table, k, v) for k, v in data.items() if v is not None]
        placeholders = ", ".join(f"${i+1}" for i in range(len(cols)))
        col_names = ", ".join(cols)
        sql = f"INSERT INTO {table} ({col_names}) VALUES ({placeholders}) RETURNING *"
        row = await self._pg.fetchrow(sql, *vals)
        return self._row_to_dict(row)

    async def generic_update(self, table: str, row_id: int, data: dict) -> dict:
        """Update a row in any table by id, return the row as dict."""
        cols = [k for k, v in data.items() if v is not None and k != 'id']
        vals = [self._convert_ts(table, k, v) for k, v in data.items() if v is not None and k != 'id']
        sets = ", ".join(f"{c} = ${i+1}" for i, c in enumerate(cols))
        vals.append(row_id)
        sql = f"UPDATE {table} SET {sets} WHERE id = ${len(vals)} RETURNING *"
        row = await self._pg.fetchrow(sql, *vals)
        return self._row_to_dict(row)

    async def generic_get(self, table: str, row_id: int) -> dict | None:
        """Get a single row from any table by id."""
        row = await self._pg.fetchrow(f"SELECT * FROM {table} WHERE id = $1", row_id)
        return self._row_to_dict(row) if row else None

    async def generic_list(self, table: str) -> list[dict]:
        """List all rows from a table, newest first."""
        rows = await self._pg.fetch(f"SELECT * FROM {table} ORDER BY create_time DESC NULLS LAST, id DESC")
        return [self._row_to_dict(r) for r in rows]

    async def generic_delete(self, table: str, row_id: int) -> bool:
        """Delete a row from any table by id."""
        result = await self._pg.execute(f"DELETE FROM {table} WHERE id = $1", row_id)
        return "DELETE 1" in result

    async def generic_insert_gas(self, gas_table: str, data: dict) -> dict:
        """Insert a gas analysis row."""
        return await self.generic_insert(gas_table, data)

    async def generic_list_gas(self, gas_table: str, permit_id: int) -> list[dict]:
        """List gas analyses for a permit."""
        rows = await self._pg.fetch(
            f"SELECT * FROM {gas_table} WHERE permit_id = $1 ORDER BY analysis_round, sample_time",
            permit_id,
        )
        return [self._row_to_dict(r) for r in rows]

    async def generic_delete_gas(self, gas_table: str, permit_id: int) -> None:
        """Delete all gas analyses for a permit."""
        await self._pg.execute(f"DELETE FROM {gas_table} WHERE permit_id = $1", permit_id)

    # ─────────────── Type-aware helpers ───────────────

    # Known timestamp columns per table
    _TS_COLS = {
        "hot_work_permits": {
            "apply_time", "gas_analysis_time", "start_time", "end_time",
            "safety_disclosure_time", "accept_time",
            "approval_owner_time", "approval_unit_time", "approval_safety_time",
            "approval_fire_leader_time", "shift_leader_time",
            "completion_acceptance_time", "create_time",
        },
        "hot_work_gas_analysis": {"sample_time", "create_time"},
        "confined_space_permits": {
            "apply_time", "last_gas_analysis_time", "start_time", "end_time",
            "disclosure_time", "approval_owner_time", "approval_unit_time",
            "completion_acceptance_time", "create_time",
        },
        "confined_space_gas_analysis": {"sample_time", "create_time"},
        "permit_blind_plate": {
            "start_time", "leader_sign_time", "unit_sign_time",
            "completion_time", "created_at", "updated_at", "create_date",
        },
    }

    def _convert_ts(self, table: str, col: str, val: Any) -> Any:
        """Convert string to datetime if column is a known timestamp."""
        if val is None or not isinstance(val, str):
            return val
        ts_cols = self._TS_COLS.get(table, set())
        if col in ts_cols:
            return self._parse_ts(val)
        return val

    @staticmethod
    def _row_to_dict(r) -> dict:
        """Convert a DB row to a plain dict, serializing non-basic types."""
        d = dict(r)
        for k, v in d.items():
            if v is not None and not isinstance(v, (str, int, float, bool)):
                d[k] = str(v)
        return d

    # ─────────────── helpers ───────────────

    @staticmethod
    def _parse_ts(v: Any) -> Any:
        """Convert string to datetime for timestamp columns."""
        if isinstance(v, str) and v:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
                try:
                    return datetime.strptime(v, fmt)
                except ValueError:
                    continue
        return v

    @staticmethod
    def _permit_cols_vals(p: HotWorkPermit) -> tuple[list[str], list[Any]]:
        cols, vals = [], []
        for c in _PERMIT_COLUMNS:
            v = getattr(p, c, None)
            if v is not None:
                if c in _TIMESTAMP_COLUMNS:
                    v = PermitsRepository._parse_ts(v)
                cols.append(c)
                vals.append(v)
        return cols, vals

    @staticmethod
    def _row_to_permit(r: asyncpg.Record) -> HotWorkPermit:  # type: ignore[name-defined]
        d = dict(r)
        for k, v in d.items():
            if v is not None and not isinstance(v, (str, int, float, bool)):
                d[k] = str(v)
        return HotWorkPermit(**{k: v for k, v in d.items() if v is not None})

    @staticmethod
    def _row_to_gas(r: asyncpg.Record) -> HotWorkGasAnalysis:  # type: ignore[name-defined]
        d = dict(r)
        for k, v in d.items():
            if v is not None and not isinstance(v, (str, int, float, bool)):
                d[k] = str(v)
        return HotWorkGasAnalysis(**{k: v for k, v in d.items() if v is not None})
