"""
audit_router.py
迅援(xunyuan)客户接入：POST /api/v1/audit/permit
- 入参：WorkPermitRequest (Pydantic 强校验)
- 出参：AuditReport
- 不写库、不写审计日志（用户拍板）

端点对照：
- POST /api/v1/audit/permit  → 同步审查 + 返回完整报告（422 Pydantic 透传原样 detail）
- GET  /api/v1/audit/health  → 健康检查（不依赖 LLM）
- GET  /api/v1/audit/permit-types → 列出支持的 8 类票种
"""
import time
from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from common.logger import get_logger
from common.xunyuan_permit_schema import (
    PermitType,
    WorkPermitRequest,
)
from services.json_audit_service import get_json_audit_service

logger = get_logger(__name__)

router = APIRouter(tags=["xunyuan-audit"])


# ───────── 健康检查（不调 LLM） ─────────
@router.get("/api/v1/audit/health")
async def health() -> Dict[str, Any]:
    return {
        "status": "ok",
        "service": "xunyuan-audit",
        "supportedPermitTypes": [pt.value for pt in PermitType],
    }


# ───────── 列出支持的 8 类票种 ─────────
@router.get("/api/v1/audit/permit-types")
async def list_permit_types() -> Dict[str, Any]:
    """前端初始化时调，渲染票种下拉框"""
    return {
        "permitTypes": [
            {"value": pt.value, "label": _zh_label(pt)}
            for pt in PermitType
        ]
    }


# ───────── 主端点：审查作业票 ─────────
# 注：直接用 WorkPermitRequest 作为参数类型，FastAPI 会自动 Pydantic 校验
#     并 raise RequestValidationError。main.py 的 handler 会把 detail 数组透传
@router.post("/api/v1/audit/permit", response_model=None)
async def audit_permit(request: WorkPermitRequest) -> Dict[str, Any]:
    """
    迅援 JSON 审查主端点。

    入参: WorkPermitRequest (Pydantic 强校验)
    出参: AuditReport
    """
    t0 = time.time()
    permit_no = request.permitNo
    logger.info(f"[audit-permit] receive: permitNo={permit_no}")

    # 调核心服务（不需要 try/except: 500 走默认 general_exception_handler）
    service = get_json_audit_service()
    report = await service.audit(request)

    logger.info(
        f"[audit-permit] done: permitNo={permit_no} "
        f"status={report['overallStatus']} "
        f"duration={int((time.time() - t0) * 1000)}ms"
    )
    return report


def _zh_label(p: PermitType) -> str:
    """8 类作业票中文名（与 json_audit_service._permit_type_zh 一致）"""
    return {
        PermitType.CONFINED_SPACE: "受限空间作业",
        PermitType.HOT_WORK: "动火作业",
        PermitType.HEIGHT_WORK: "高处作业",
        PermitType.TEMP_ELECTRIC: "临时用电作业",
        PermitType.BLIND_PLATE: "盲板抽堵作业",
        PermitType.LIFTING_WORK: "起重作业",
        PermitType.EXCAVATION: "动土作业",
        PermitType.ROAD_BREAK: "断路作业",
    }.get(p, p.value)
