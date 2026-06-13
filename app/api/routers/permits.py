"""
作业票 API 路由 - 支持多种作业票类型。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from pydantic import BaseModel
from pathlib import Path
from typing import Any

from dependencies import get_permits_service
from services.permits_service import PermitsService
from services.permit_types import list_permit_types, get_permit_type

router = APIRouter(tags=["permits"])


class SavePermitRequest(BaseModel):
    permit_type: str = "hot_work"
    permit: dict
    gas_analyses: list[dict] = []
    safety_checks: list[dict] = []


class ComplianceReviewRequest(BaseModel):
    permit_type: str = "hot_work"
    data: dict


@router.get("/api/v1/permit-types", summary="获取支持的作业票类型")
async def get_types():
    return list_permit_types()


@router.post(
    "/api/v1/permits/upload-and-extract",
    summary="上传 PDF 并提取结构化数据",
)
async def upload_and_extract(
    file: UploadFile = File(...),
    permit_type: str = Query("hot_work", description="作业票类型"),
    service: PermitsService = Depends(get_permits_service),
):
    ext = Path(file.filename).suffix.lower() if file.filename else ""
    if ext not in {".pdf", ".jpg", ".jpeg", ".png", ".json"}:
        raise HTTPException(status_code=400, detail="仅支持 PDF、JPG、PNG、JSON 文件")
    # Validate type
    try:
        get_permit_type(permit_type)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    file_bytes = await file.read()
    try:
        return await service.upload_and_extract(file_bytes, file.filename, permit_type)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"解析失败: {e}")


@router.post(
    "/api/v1/permits",
    summary="确认保存作业票到数据库",
)
async def save_permit(
    body: SavePermitRequest,
    service: PermitsService = Depends(get_permits_service),
):
    try:
        get_permit_type(body.permit_type)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    saved = await service.save_permit_generic(
        body.permit_type, body.permit, body.gas_analyses, body.safety_checks
    )
    code_key = "permit_code" if "permit_code" in saved else "ticket_code"
    return {"id": saved.get("id"), "code": saved.get(code_key)}


@router.post(
    "/api/v1/permits/compliance-review",
    summary="合规性审查",
)
async def compliance_review(
    body: ComplianceReviewRequest,
    service: PermitsService = Depends(get_permits_service),
):
    return await service.compliance_review(body.data, body.permit_type)


@router.get(
    "/api/v1/permits",
    summary="查询作业票列表",
)
async def list_permits(
    permit_type: str = Query("hot_work", description="作业票类型"),
    service: PermitsService = Depends(get_permits_service),
):
    try:
        get_permit_type(permit_type)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return await service.list_permits_typed(permit_type)


@router.get(
    "/api/v1/permits/{permit_id}",
    summary="获取单张作业票详情",
)
async def get_permit(
    permit_id: int,
    permit_type: str = Query("hot_work", description="作业票类型"),
    service: PermitsService = Depends(get_permits_service),
):
    try:
        get_permit_type(permit_type)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    result = await service.get_permit_typed(permit_type, permit_id)
    if not result:
        raise HTTPException(status_code=404, detail="作业票不存在")
    return result


@router.delete(
    "/api/v1/permits/{permit_id}",
    summary="删除作业票",
)
async def delete_permit(
    permit_id: int,
    permit_type: str = Query("hot_work", description="作业票类型"),
    service: PermitsService = Depends(get_permits_service),
):
    try:
        get_permit_type(permit_type)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    ok = await service.delete_permit_typed(permit_type, permit_id)
    if not ok:
        raise HTTPException(status_code=404, detail="作业票不存在")
    return {"deleted": True}
