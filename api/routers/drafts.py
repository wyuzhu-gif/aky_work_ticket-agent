"""
2026-06-22 新增: 作业票草稿 API
- POST   /api/v1/drafts        新增或覆盖 (upsert)
- GET    /api/v1/drafts        列表 (元信息)
- GET    /api/v1/drafts/{code}  加载单个 (含 permit/gas/safety/review)
- DELETE /api/v1/drafts/{code}  删除

注: 草稿用 SQLite (app.db) 存, 不依赖 MySQL king 库 (那库 8 个 permit 表不全)
"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from common.logger import get_logger
from database.drafts_repository import DraftsRepository
from dependencies import get_drafts_repository

router = APIRouter(tags=["drafts"])
logging = get_logger(__name__)


class DraftSaveRequest(BaseModel):
    permit_code: str = Field(..., min_length=1, max_length=200, description="票号 (无票号前端用 _draft_<timestamp>)")
    permit_type: str = Field(..., description="hot_work / confined_space / ...")
    permit: Dict[str, Any] = Field(default_factory=dict)
    gas_analyses: List[Dict[str, Any]] = Field(default_factory=list)
    safety_checks: List[Dict[str, Any]] = Field(default_factory=list)
    review_results: List[Dict[str, Any]] = Field(default_factory=list)


class DraftSummary(BaseModel):
    permit_code: str
    permit_type: str
    permit_unit: str = ""
    permit_location: str = ""
    permit_job: str = ""
    gas_count: int = 0
    safety_count: int = 0
    has_review: bool = False
    review_count: int = 0
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class DraftDetail(BaseModel):
    permit_code: str
    permit_type: str
    permit: Dict[str, Any]
    gas_analyses: List[Dict[str, Any]]
    safety_checks: List[Dict[str, Any]]
    review_results: List[Dict[str, Any]]
    has_review: bool
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


@router.post(
    "/api/v1/drafts",
    summary="暂存 / 保存到本地 (upsert by permit_code)",
    response_model=DraftSummary,
)
async def save_draft(
    req: DraftSaveRequest,
    repo: DraftsRepository = Depends(get_drafts_repository),
):
    if not req.permit_code:
        raise HTTPException(status_code=400, detail="permit_code 必填 (无票号用 _draft_<timestamp>)")
    if not req.permit_type:
        raise HTTPException(status_code=400, detail="permit_type 必填")

    row = await repo.upsert_draft(
        permit_code=req.permit_code,
        permit_type=req.permit_type,
        permit=req.permit,
        gas_analyses=req.gas_analyses,
        safety_checks=req.safety_checks,
        review_results=req.review_results,
    )
    return repo._deserialize_summary(row)  # noqa: SLF001 (内部使用, 同进程)


@router.get(
    "/api/v1/drafts",
    summary="列草稿 (元信息, 不含大 JSON)",
    response_model=List[DraftSummary],
)
async def list_drafts(
    permit_type: Optional[str] = Query(None, description="按作业类型过滤"),
    repo: DraftsRepository = Depends(get_drafts_repository),
):
    return await repo.list_drafts(permit_type=permit_type)


@router.get(
    "/api/v1/drafts/{permit_code}",
    summary="加载单个草稿 (含完整 permit + gas + safety + review)",
    response_model=DraftDetail,
)
async def get_draft(
    permit_code: str,
    repo: DraftsRepository = Depends(get_drafts_repository),
):
    draft = await repo.get_draft(permit_code)
    if not draft:
        raise HTTPException(status_code=404, detail=f"草稿 {permit_code} 不存在")
    return draft


@router.delete(
    "/api/v1/drafts/{permit_code}",
    summary="删除草稿",
)
async def delete_draft(
    permit_code: str,
    repo: DraftsRepository = Depends(get_drafts_repository),
):
    ok = await repo.delete_draft(permit_code)
    if not ok:
        raise HTTPException(status_code=404, detail=f"草稿 {permit_code} 不存在")
    return {"deleted": permit_code}
