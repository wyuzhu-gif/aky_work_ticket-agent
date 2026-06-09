"""
作业票（动火作业票）数据模型。

与 PostgreSQL 表 hot_work_permits / hot_work_gas_analysis / safety_check_items / work_safety_checks 对应。
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


# ─────────────────────── 动火作业票主表 ───────────────────────

class HotWorkPermit(BaseModel):
    model_config = ConfigDict(use_enum_values=True, populate_by_name=True)

    id: int | None = None
    permit_code: str = ""
    work_id: str | None = None

    # 基础信息
    apply_unit: str | None = None
    apply_time: str | None = None
    work_content: str | None = None
    work_location: str | None = None
    work_level: str | None = None          # 特级/一级/二级
    work_method: str | None = None
    fire_worker_info: str | None = None
    work_unit: str | None = None
    work_owner_name: str | None = None
    work_owner_phone: str | None = None

    # 气体分析概览
    gas_analysis_time: str | None = None
    gas_analyst_name: str | None = None
    gas_analysis_result: str | None = None

    # 关联信息
    related_permit_ids: str | None = None
    risk_identification: str | None = None

    # 作业时间
    start_time: str | None = None
    end_time: str | None = None

    # 安全交底
    safety_disclosure_person: str | None = None
    safety_disclosure_time: str | None = None
    accept_person: str | None = None
    accept_time: str | None = None
    attendant: str | None = None

    # 审批 — 作业负责人
    approval_owner_opinion: str | None = None
    approval_owner_sign: str | None = None
    approval_owner_time: str | None = None

    # 审批 — 所在单位
    approval_unit_opinion: str | None = None
    approval_unit_sign: str | None = None
    approval_unit_time: str | None = None

    # 审批 — 安全管理部门
    approval_safety_opinion: str | None = None
    approval_safety_sign: str | None = None
    approval_safety_time: str | None = None

    # 审批 — 动火审批人
    approval_fire_leader_opinion: str | None = None
    approval_fire_leader_sign: str | None = None
    approval_fire_leader_time: str | None = None

    # 动火前岗位当班班长验票
    shift_leader_check_result: str | None = None
    shift_leader_sign: str | None = None
    shift_leader_time: str | None = None

    # 完工验收
    completion_acceptance_result: str | None = None
    completion_acceptance_sign: str | None = None
    completion_acceptance_time: str | None = None

    # 状态
    status: str = "DRAFT"
    create_time: str | None = None


# ─────────────────────── 气体分析子表 ───────────────────────

class HotWorkGasAnalysis(BaseModel):
    model_config = ConfigDict(use_enum_values=True, populate_by_name=True)

    id: int | None = None
    permit_id: int | None = None
    analysis_round: int | None = None
    sample_time: str | None = None
    representative_gas: str | None = None
    analysis_result: str | None = None
    analyst_name: str | None = None
    create_time: str | None = None


# ─────────────────────── 安全措施标准库 ───────────────────────

class SafetyCheckItem(BaseModel):
    id: int | None = None
    code: str = ""
    description: str = ""
    applicable_to: list[str] = []         # e.g. ["HOT_WORK"]


# ─────────────────────── 作业票-安全措施关联 ───────────────────────

class WorkSafetyCheck(BaseModel):
    permit_id: int
    permit_type: str = "HOT_WORK"
    check_item_id: int
    is_confirmed: bool = False
    confirmed_by: str | None = None
    confirmed_at: str | None = None
    params: dict | None = None
    evidence_url: str | None = None


# ─────────────────────── API 交互模型 ───────────────────────

class ExtractedSafetyCheck(BaseModel):
    """LLM 提取的单条安全措施"""
    description: str
    is_confirmed: bool = False
    confirmed_by: str | None = None


class PermitUploadResponse(BaseModel):
    """上传 PDF → MinerU → LLM 提取后的返回结构"""
    permit: HotWorkPermit
    gas_analyses: list[HotWorkGasAnalysis] = []
    safety_checks: list[ExtractedSafetyCheck] = []
    raw_md: str = ""


class ComplianceReviewRequest(BaseModel):
    """合规性审查请求（前端传入已提取的数据）"""
    permit: HotWorkPermit
    gas_analyses: list[HotWorkGasAnalysis] = []
    safety_checks: list[ExtractedSafetyCheck] = []


class PermitSaveRequest(BaseModel):
    """前端确认后提交的保存请求"""
    permit: HotWorkPermit
    gas_analyses: list[HotWorkGasAnalysis] = []
    safety_checks: list[ExtractedSafetyCheck] = []
