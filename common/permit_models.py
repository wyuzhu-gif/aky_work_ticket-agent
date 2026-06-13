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

# ─────────────────────── 高处作业票主表 ───────────────────────
# GB 30871-2022 第 5 章

class HeightPermit(BaseModel):
    model_config = ConfigDict(use_enum_values=True, populate_by_name=True)

    id: int | None = None
    permit_code: str = ""
    work_id: str | None = None

    # 基础信息
    apply_unit: str | None = None
    apply_time: str | None = None
    work_content: str | None = None
    work_location: str | None = None
    work_level: str | None = None          # 一级/二级/三级/特级
    work_type: str | None = None          # 临边/洞口/攀登/悬空/交叉作业等
    work_height: str | None = None        # 作业高度（米）

    # 人员信息
    work_unit: str | None = None
    work_owner_name: str | None = None
    work_owner_phone: str | None = None
    height_worker_info: str | None = None   # 高处作业人员及证书编号

    # 防护与监护
    protective_measure: str | None = None   # 防护措施（安全带/脚手架/护栏等）
    attendant: str | None = None           # 监护人

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

    # 审批 — 主管部门
    approval_dept_opinion: str | None = None
    approval_dept_sign: str | None = None
    approval_dept_time: str | None = None

    # 完工验收
    completion_acceptance_result: str | None = None
    completion_acceptance_sign: str | None = None
    completion_acceptance_time: str | None = None

    # 状态
    status: str = "DRAFT"
    create_time: str | None = None


# ─────────────────────── 吊装作业票主表 ───────────────────────
# GB 30871-2022 第 6 章

class LiftingPermit(BaseModel):
    model_config = ConfigDict(use_enum_values=True, populate_by_name=True)

    id: int | None = None
    permit_code: str = ""
    work_id: str | None = None

    # 基础信息
    apply_unit: str | None = None
    apply_time: str | None = None
    work_content: str | None = None
    work_location: str | None = None

    # 吊装参数
    lifting_weight: str | None = None      # 吊装质量（吨）
    lifting_height: str | None = None      # 吊装高度（米）
    lifting_method: str | None = None      # 吊装方式（汽车吊/履带吊/桥式吊等）
    crane_model: str | None = None         # 起重设备型号
    slinger_info: str | None = None        # 司索工/指挥/司机及证书

    # 警戒区
    warning_zone: str | None = None

    # 人员
    work_unit: str | None = None
    work_owner_name: str | None = None
    work_owner_phone: str | None = None
    attendant: str | None = None

    # 关联
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

    # 审批 — 作业负责人
    approval_owner_opinion: str | None = None
    approval_owner_sign: str | None = None
    approval_owner_time: str | None = None

    # 审批 — 所在单位
    approval_unit_opinion: str | None = None
    approval_unit_sign: str | None = None
    approval_unit_time: str | None = None

    # 审批 — 主管部门
    approval_dept_opinion: str | None = None
    approval_dept_sign: str | None = None
    approval_dept_time: str | None = None

    # 审批 — 安全管理部门
    approval_safety_opinion: str | None = None
    approval_safety_sign: str | None = None
    approval_safety_time: str | None = None

    # 完工验收
    completion_acceptance_result: str | None = None
    completion_acceptance_sign: str | None = None
    completion_acceptance_time: str | None = None

    status: str = "DRAFT"
    create_time: str | None = None


# ─────────────────────── 临时用电作业票主表 ───────────────────────
# GB 30871-2022 第 7 章

class TempElectricPermit(BaseModel):
    model_config = ConfigDict(use_enum_values=True, populate_by_name=True)

    id: int | None = None
    permit_code: str = ""
    work_id: str | None = None

    # 基础信息
    apply_unit: str | None = None
    apply_time: str | None = None
    work_content: str | None = None
    work_location: str | None = None

    # 电气参数
    voltage_level: str | None = None      # 电压等级（如 380V/220V）
    power_capacity: str | None = None     # 用电容量（kW）
    equipment_list: str | None = None     # 用电设备清单
    power_source: str | None = None       # 电源接入点

    # 防护
    protective_measure: str | None = None  # 接地/漏保/绝缘等防护措施
    electrician_info: str | None = None    # 电工及作业证编号

    # 气体分析（临时用电涉及可燃气体环境时需检测）
    gas_analysis_time: str | None = None
    gas_analyst_name: str | None = None
    gas_analysis_result: str | None = None

    # 人员
    work_unit: str | None = None
    work_owner_name: str | None = None
    work_owner_phone: str | None = None
    attendant: str | None = None

    # 关联
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

    # 审批 — 电气主管部门
    approval_electrical_opinion: str | None = None
    approval_electrical_sign: str | None = None
    approval_electrical_time: str | None = None

    # 完工验收
    completion_acceptance_result: str | None = None
    completion_acceptance_sign: str | None = None
    completion_acceptance_time: str | None = None

    status: str = "DRAFT"
    create_time: str | None = None


# ─────────────────────── 临时用电气体分析子表 ───────────────────────

class TempElectricGasAnalysis(BaseModel):
    model_config = ConfigDict(use_enum_values=True, populate_by_name=True)

    id: int | None = None
    permit_id: int | None = None
    analysis_round: int | None = None
    sample_time: str | None = None
    representative_gas: str | None = None
    analysis_result: str | None = None
    analyst_name: str | None = None
    create_time: str | None = None


# ─────────────────────── 动土作业票主表 ───────────────────────
# GB 30871-2022 第 8 章

class ExcavationPermit(BaseModel):
    model_config = ConfigDict(use_enum_values=True, populate_by_name=True)

    id: int | None = None
    permit_code: str = ""
    work_id: str | None = None

    # 基础信息
    apply_unit: str | None = None
    apply_time: str | None = None
    work_content: str | None = None
    work_location: str | None = None

    # 动土参数
    excavation_type: str | None = None     # 开挖方式（人工/机械/爆破）
    excavation_depth: str | None = None    # 开挖深度（米）
    soil_type: str | None = None           # 土壤性质
    underground_facility: str | None = None  # 地下设施情况（管线/电缆等）
    protective_measure: str | None = None  # 支护/放坡/排水等措施

    # 警戒区
    warning_zone: str | None = None

    # 人员
    work_unit: str | None = None
    work_owner_name: str | None = None
    work_owner_phone: str | None = None
    attendant: str | None = None

    # 关联
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

    # 审批 — 作业负责人
    approval_owner_opinion: str | None = None
    approval_owner_sign: str | None = None
    approval_owner_time: str | None = None

    # 审批 — 所在单位
    approval_unit_opinion: str | None = None
    approval_unit_sign: str | None = None
    approval_unit_time: str | None = None

    # 审批 — 主管部门
    approval_dept_opinion: str | None = None
    approval_dept_sign: str | None = None
    approval_dept_time: str | None = None

    # 完工验收
    completion_acceptance_result: str | None = None
    completion_acceptance_sign: str | None = None
    completion_acceptance_time: str | None = None

    status: str = "DRAFT"
    create_time: str | None = None


# ─────────────────────── 断路作业票主表 ───────────────────────
# GB 30871-2022 第 9 章

class RoadBreakingPermit(BaseModel):
    model_config = ConfigDict(use_enum_values=True, populate_by_name=True)

    id: int | None = None
    permit_code: str = ""
    work_id: str | None = None

    # 基础信息
    apply_unit: str | None = None
    apply_time: str | None = None
    work_content: str | None = None
    work_location: str | None = None
    work_reason: str | None = None         # 断路原因
    affected_area: str | None = None       # 影响范围

    # 警戒与警示
    warning_zone: str | None = None
    warning_signs: str | None = None       # 警示标志设置情况
    traffic_diversion: str | None = None   # 交通疏导措施

    # 人员
    work_unit: str | None = None
    work_owner_name: str | None = None
    work_owner_phone: str | None = None
    attendant: str | None = None

    # 关联
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

    # 审批 — 作业负责人
    approval_owner_opinion: str | None = None
    approval_owner_sign: str | None = None
    approval_owner_time: str | None = None

    # 审批 — 所在单位
    approval_unit_opinion: str | None = None
    approval_unit_sign: str | None = None
    approval_unit_time: str | None = None

    # 审批 — 主管部门
    approval_dept_opinion: str | None = None
    approval_dept_sign: str | None = None
    approval_dept_time: str | None = None

    # 完工验收
    completion_acceptance_result: str | None = None
    completion_acceptance_sign: str | None = None
    completion_acceptance_time: str | None = None

    status: str = "DRAFT"
    create_time: str | None = None
