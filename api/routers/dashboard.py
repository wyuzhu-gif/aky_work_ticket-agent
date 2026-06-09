"""
审核看板 API — 聚合统计接口。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from enum import Enum

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from typing import Any

from dependencies import get_issues_repo, get_permits_service
from database.issues_repository import IssuesRepository
from services.permits_service import PermitsService
from common.logger import get_logger

router = APIRouter(tags=["dashboard"])
logger = get_logger(__name__)


class PeriodEnum(str, Enum):
    """时间范围"""
    today = "today"
    week = "week"
    month = "month"
    all = "all"


def _period_cutoff(period: PeriodEnum) -> datetime | None:
    """返回对应时间范围的起始时间（UTC），all 返回 None"""
    now = datetime.now(timezone.utc)
    if period == PeriodEnum.today:
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == PeriodEnum.week:
        return now - timedelta(days=7)
    if period == PeriodEnum.month:
        return now - timedelta(days=30)
    return None  # all


class DashboardStats(BaseModel):
    """看板统计指标"""
    total_reviews: int = 0         # 总审核文档数
    total_issues: int = 0          # 总问题数
    accepted_issues: int = 0       # 已采纳问题数
    dismissed_issues: int = 0      # 已驳回问题数
    pending_issues: int = 0        # 待处理问题数
    high_risk_issues: int = 0      # 高风险问题数
    total_permits: int = 0         # 作业票总数


class RecentReview(BaseModel):
    """最近审核记录"""
    doc_id: str
    issue_count: int = 0
    high_risk_count: int = 0
    accepted_count: int = 0
    latest_review_time: str | None = None


class PermitTypeStat(BaseModel):
    """作业票类型统计"""
    type: str
    label: str
    count: int = 0


class RiskDistribution(BaseModel):
    """风险等级分布"""
    high: int = 0
    medium: int = 0
    low: int = 0
    info: int = 0


class DashboardResponse(BaseModel):
    """看板完整响应"""
    stats: DashboardStats
    recent_reviews: list[RecentReview]
    permit_type_stats: list[PermitTypeStat]
    risk_distribution: RiskDistribution


# 作业票类型中文标签
_PERMIT_TYPE_LABELS: dict[str, str] = {
    "hot_work": "动火作业",
    "confined_space": "受限空间",
    "blind_plate": "盲板抽堵",
}


@router.get(
    "/api/v1/dashboard",
    summary="审核看板数据",
)
async def get_dashboard(
    period: PeriodEnum = Query(PeriodEnum.all, description="时间范围：today/week/month/all"),
    issues_repo: IssuesRepository = Depends(get_issues_repo),
    permits_service: PermitsService = Depends(get_permits_service),
) -> DashboardResponse:
    """聚合返回看板所有数据，支持按时间范围过滤"""

    # ── 时间过滤 ──
    cutoff = _period_cutoff(period)

    # ── 1. Issues 统计 ──
    all_issues = await issues_repo.get_all_issues()

    # 按时间过滤
    if cutoff:
        def _issue_time(issue):
            ts = issue.review_initiated_at_UTC or issue.resolved_at_UTC or ""
            try:
                return datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                return datetime.min.replace(tzinfo=timezone.utc)

        filtered_issues = [i for i in all_issues if _issue_time(i) >= cutoff]
    else:
        filtered_issues = all_issues

    stats = DashboardStats(
        total_issues=len(filtered_issues),
        accepted_issues=sum(1 for i in filtered_issues if i.status == "accepted"),
        dismissed_issues=sum(1 for i in filtered_issues if i.status == "dismissed"),
        pending_issues=sum(1 for i in filtered_issues if i.status == "not_reviewed"),
        high_risk_issues=sum(1 for i in filtered_issues if i.risk_level == "high"),
    )

    # 按文档分组，计算每个文档的审核记录
    doc_map: dict[str, RecentReview] = {}
    for issue in filtered_issues:
        doc_id = issue.doc_id
        if doc_id not in doc_map:
            doc_map[doc_id] = RecentReview(doc_id=doc_id)
        rec = doc_map[doc_id]
        rec.issue_count += 1
        if issue.risk_level == "high":
            rec.high_risk_count += 1
        if issue.status == "accepted":
            rec.accepted_count += 1
        # 取最新的审核时间
        review_time = issue.review_initiated_at_UTC or issue.resolved_at_UTC
        if review_time and (not rec.latest_review_time or review_time > rec.latest_review_time):
            rec.latest_review_time = review_time

    stats.total_reviews = len(doc_map)

    # 按时间倒序，取最近 10 条
    recent_reviews = sorted(
        doc_map.values(),
        key=lambda r: r.latest_review_time or "",
        reverse=True,
    )[:10]

    # ── 2. 风险等级分布 ──
    risk_dist = RiskDistribution(
        high=sum(1 for i in filtered_issues if i.risk_level == "high"),
        medium=sum(1 for i in filtered_issues if i.risk_level == "medium"),
        low=sum(1 for i in filtered_issues if i.risk_level == "low"),
        info=sum(1 for i in filtered_issues if i.risk_level not in ("high", "medium", "low")),
    )

    # ── 3. 作业票类型统计 ──
    permit_stats: list[PermitTypeStat] = []
    total_permits = 0
    for ptype, label in _PERMIT_TYPE_LABELS.items():
        try:
            permits = await permits_service.list_permits_typed(ptype)
            count = len(permits)
            total_permits += count
            permit_stats.append(PermitTypeStat(type=ptype, label=label, count=count))
        except Exception:
            permit_stats.append(PermitTypeStat(type=ptype, label=label, count=0))

    stats.total_permits = total_permits

    return DashboardResponse(
        stats=stats,
        recent_reviews=recent_reviews,
        permit_type_stats=permit_stats,
        risk_distribution=risk_dist,
    )
