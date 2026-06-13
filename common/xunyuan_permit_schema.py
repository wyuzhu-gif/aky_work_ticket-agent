"""
xunyuan_permit_schema.py
迅援客户作业票审查：Pydantic 强校验模型

对齐 xunyuan 数据库 work_permit 表 17 槽位 + 风险/措施子结构 + formPayload 扩展。

设计原则：
- 15 项通用必填 + 2 项条件必填（confinedSpaceName / safetyOfficerUser）
- camelCase 字段名（与 work_permit 表列名一致）
- Pydantic 校验做硬必填 + 类型 + 格式
- 跨字段业务校验由 json_audit_service 内的 Python 代码做
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# ─────────────────────── 枚举值（与 xunyuan 数据库一致） ───────────────────────

class PermitType(str, Enum):
    """8 类特殊作业票，对齐 xunyuan 数据库 work_form_definition 表 8 个 swp_def_*"""
    CONFINED_SPACE = "confined_space"
    HOT_WORK = "hot_work"
    HEIGHT_WORK = "height_work"
    BLIND_PLATE = "blind_plate"
    LIFTING_WORK = "lifting_work"
    EXCAVATION = "excavation"
    TEMP_ELECTRIC = "temp_electric"
    ROAD_BREAK = "road_break"


class RiskLevel(str, Enum):
    """风险等级，对齐 work_permit.risk_level"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    EXTREME = "extreme"


class IssueSource(str, Enum):
    """问题来源（前端展示用）"""
    PYDANTIC = "pydantic"          # Pydantic 强校验产物
    PYTHON_VALIDATOR = "python_validator"  # 跨字段业务校验
    LLM = "llm"                    # LLM 审查产物


class IssueRiskLevel(str, Enum):
    """问题风险等级（前端标签显示）"""
    HIGH = "高"
    MEDIUM = "中"
    LOW = "低"


class FieldStatus(str, Enum):
    """字段校验状态"""
    PASSED = "passed"
    WARNING = "warning"
    ERROR = "error"


class OverallStatus(str, Enum):
    """审查总体结论"""
    PASS = "pass"
    WARNING = "warning"
    FAIL = "fail"


# ─────────────────────── 入参模型 ───────────────────────

class SafetyMeasure(BaseModel):
    """单条安全措施（对齐 xunyuan work_permit_safety_measure 行）"""
    model_config = ConfigDict(extra="allow")  # 允许额外字段（如 measureCode, evidenceUrl）

    rowId: int = Field(..., description="行号，0-indexed")
    measureText: str = Field(..., min_length=1, description="措施文字描述")
    # involved 兼容多种格式：bool / "是"/"否" / 1/0
    involved: Union[bool, str, int] = Field(..., description="是否已确认（true/false/'是'/'否'）")
    confirmerName: Optional[str] = Field(None, description="确认人姓名")

    @field_validator("involved", mode="before")
    @classmethod
    def _coerce_involved(cls, v: Any) -> Union[bool, str, int]:
        """客户数据样本里发现 involved 字段类型不固定，统一在 audit 阶段处理"""
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.strip()
        if isinstance(v, int):
            return v
        raise ValueError(f"involved 必须是 bool/str/int 之一，实际类型: {type(v).__name__}")

    def is_involved(self) -> bool:
        """标准化判定：兼容 bool/str/int"""
        if isinstance(self.involved, bool):
            return self.involved
        if isinstance(self.involved, str):
            return self.involved in ("是", "true", "True", "1", "yes", "Y")
        if isinstance(self.involved, int):
            return self.involved != 0
        return False


class AuditOptions(BaseModel):
    """审查选项"""
    model_config = ConfigDict(extra="forbid")

    skipDataInsufficientCategories: bool = Field(
        True,
        description="true=跳过 4 个数据不足维度（审批/气体分析/完工验收/交叉作业），false=把'数据缺失'也报为 warning"
    )
    llmModel: Optional[str] = Field(
        None,
        description="LLM 模型名（覆盖默认 qwen3.6-35b-a3b）"
    )
    wikiTopK: int = Field(3, ge=1, le=10, description="Milvus 检索 topK")


class WorkPermitRequest(BaseModel):
    """
    迅援作业票审查入参
    对齐 xunyuan 数据库 work_permit 表 17 槽位 + 风险/措施子结构 + formPayload 扩展
    """
    model_config = ConfigDict(extra="forbid")  # 严格不允许未知字段

    # ───── 8 类标识 ─────
    permitType: PermitType = Field(..., description="8 类作业票类型")

    # ───── 17 槽位（work_permit 表 1:1）─────
    planId: int = Field(..., ge=1, description="关联作业计划 ID")
    permitNo: str = Field(..., min_length=1, max_length=64, description="作业票号")
    riskLevel: RiskLevel = Field(..., description="风险等级")

    # confinedSpaceName: 受限空间类必填，其他类可选（条件必填由 model_validator 控）
    confinedSpaceName: Optional[str] = Field(None, max_length=128, description="受限空间名称")

    workLocationId: str = Field(..., min_length=1, max_length=64, description="作业地点 ID")
    workContentText: str = Field(..., min_length=1, max_length=2000, description="作业内容")
    workUnitId: str = Field(..., min_length=1, max_length=64, description="作业单位 ID")
    contractorUnitId: Optional[str] = Field(None, max_length=64, description="承包商单位 ID（无则 null）")

    # 人员：xunyuan 是 user_id（snowflake 19 位）
    principalUser: int = Field(..., ge=1, description="作业负责人 user_id（snowflake）")
    guardianUser: int = Field(..., ge=1, description="监护人 user_id（snowflake）")
    # safetyOfficerUser: 受限空间类必填（条件必填由 model_validator 控）
    safetyOfficerUser: Optional[int] = Field(None, ge=1, description="安全员 user_id（受限空间必填）")

    personnelExtraJson: Optional[Dict[str, Any]] = Field(
        None, description="扩展人员（workers/外协人员/资质证书等）"
    )
    monitoringDeviceRef: Optional[str] = Field(
        None, max_length=64, description="监护设备关联（受限空间、动火作业可能涉及）"
    )

    plannedStartTime: datetime = Field(..., description="计划开始时间（ISO 8601）")
    plannedEndTime: datetime = Field(..., description="计划结束时间（ISO 8601）")

    # ───── 风险 + 措施子结构 ─────
    riskFactorsJson: List[str] = Field(..., min_length=1, description="风险因素 key 列表（必填≥1）")
    safetyMeasuresJson: List[SafetyMeasure] = Field(..., description="安全措施子表")

    # ───── 扩展槽（formPayload）─────
    formPayload: Optional[Dict[str, Any]] = Field(
        None,
        description="动态扩展槽（不含 17 槽位；可含 fieldSuppl 子对象存补充说明）"
    )

    # ───── 审查选项 ─────
    options: AuditOptions = Field(default_factory=AuditOptions)

    @model_validator(mode="after")
    def _validate_required_fields(self) -> "WorkPermitRequest":
        """条件必填字段 + 跨字段业务校验"""
        errors: List[str] = []

        # 1. 受限空间类：confinedSpaceName + safetyOfficerUser 都必填
        if self.permitType == PermitType.CONFINED_SPACE:
            if not self.confinedSpaceName:
                errors.append("confined_space 类作业票 confinedSpaceName 必填")
            if not self.safetyOfficerUser:
                errors.append("confined_space 类作业票 safetyOfficerUser 必填")

        # 2. 动火/受限空间：monitoringDeviceRef 强烈建议（warning 而非 error）
        # 留作 warning，不在 Pydantic 校验，交给审计阶段

        # 3. 时间合法性
        if self.plannedStartTime >= self.plannedEndTime:
            errors.append("plannedStartTime 必须早于 plannedEndTime")

        # 4. 人员去重：3 个 user_id 不能两两相同
        persons = {
            "principalUser": self.principalUser,
            "guardianUser": self.guardianUser,
        }
        if self.safetyOfficerUser:
            persons["safetyOfficerUser"] = self.safetyOfficerUser
        if len(persons) != len(set(persons.values())):
            errors.append("作业负责人/监护人/安全员不可由同一人担任")

        # 5. 风险因素至少 1 条
        if not self.riskFactorsJson:
            errors.append("riskFactorsJson 至少 1 条")

        # 6. 措施至少 1 条
        if not self.safetyMeasuresJson:
            errors.append("safetyMeasuresJson 至少 1 条")

        if errors:
            raise ValueError("; ".join(errors))

        return self

    @field_validator("riskFactorsJson")
    @classmethod
    def _deduplicate_risk_factors(cls, v: List[str]) -> List[str]:
        """风险因素去重（保序）"""
        seen = set()
        result = []
        for f in v:
            f = f.strip() if isinstance(f, str) else f
            if f and f not in seen:
                seen.add(f)
                result.append(f)
        return result


# ─────────────────────── 出参模型 ───────────────────────

class FieldValidationItem(BaseModel):
    """单字段校验结果"""
    field: str = Field(..., description="字段名（点号路径如 safetyMeasuresJson[2]）")
    status: FieldStatus
    message: str = Field(..., description="错误/警告描述")
    ruleReference: Optional[str] = Field(None, description="引用法规条款（如 GB 30871-2022 第6.4条）")


class FieldValidationReport(BaseModel):
    """Pydantic 强校验结果汇总"""
    validated: int = Field(..., ge=0, description="已校验字段数")
    passed: int = Field(..., ge=0)
    warnings: int = Field(..., ge=0)
    errors: int = Field(..., ge=0)
    items: List[FieldValidationItem] = Field(default_factory=list)


class UncoveredRisk(BaseModel):
    """未覆盖的风险因素"""
    riskFactor: str
    reason: str = Field(..., description="为什么判定为未覆盖")


class UnconfirmedMeasure(BaseModel):
    """未确认的措施"""
    measureText: str
    reason: str


class RiskMeasureCoverageReport(BaseModel):
    """风险-措施覆盖度报告（Python 跨字段校验产物）"""
    riskFactorCount: int = Field(..., ge=0)
    measureCount: int = Field(..., ge=0)
    uncovered: List[UncoveredRisk] = Field(default_factory=list)
    unconfirmed: List[UnconfirmedMeasure] = Field(default_factory=list)


class RegulationMatch(BaseModel):
    """法规条款引用"""
    category: str = Field(..., description="条款所属章节（如'GB 30871-2022 第6章 受限空间作业'）")
    matchedClauses: List[str] = Field(default_factory=list, description="具体条款编号列表")


class AuditIssue(BaseModel):
    """单条审查问题（前端卡片/表格展示）"""
    id: str = Field(..., description="问题 ID（审计侧生成）")
    type: str = Field(..., description="问题类型（如'气体分析不合格'、'安全措施未落实'）")
    riskLevel: IssueRiskLevel
    category: str = Field(..., description="所属审查维度（如'现场控制措施落实'）")
    fieldKey: str = Field(..., description="关联字段（点号路径）")
    text: str = Field(..., description="问题描述")
    explanation: str = Field(..., description="违反条款说明（引用 GB 30871-2022）")
    suggestedFix: str = Field(..., description="整改建议")
    source: IssueSource = Field(..., description="问题来源")


class AuditSummary(BaseModel):
    """问题统计"""
    total: int = Field(..., ge=0)
    high: int = Field(..., ge=0)
    medium: int = Field(..., ge=0)
    low: int = Field(..., ge=0)


class AuditMetadata(BaseModel):
    """审计元信息"""
    reviewedAt: str = Field(..., description="审计完成时间（ISO 8601）")
    llmModel: str = Field(..., description="实际使用的 LLM 模型")
    wikiChaptersRetrieved: int = Field(..., ge=0, description="Milvus 检索到的法规条数")
    durationMs: int = Field(..., ge=0, description="审计总耗时（毫秒）")


class AuditReport(BaseModel):
    """
    迅援作业票审查出参

    5 大块：summary + fieldValidation + riskMeasureCoverage + regulationMatches + issues
    + aiReportMarkdown 完整报告
    """
    permitNo: str
    permitType: PermitType
    overallStatus: OverallStatus

    summary: AuditSummary
    fieldValidation: FieldValidationReport
    riskMeasureCoverage: RiskMeasureCoverageReport
    regulationMatches: List[RegulationMatch] = Field(default_factory=list)
    issues: List[AuditIssue] = Field(default_factory=list)
    aiReportMarkdown: str = Field(..., description="LLM 生成的完整 markdown 报告")

    metadata: AuditMetadata

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "permitNo": "DHZY-20260613-001",
            "permitType": "confined_space",
            "overallStatus": "fail",
        }
    })


# ─────────────────────── 工具函数 ───────────────────────

def compute_overall_status(
    field_errors: int,
    high_issues: int,
    medium_issues: int,
) -> OverallStatus:
    """判定总体结论"""
    if field_errors > 0 or high_issues > 0:
        return OverallStatus.FAIL
    if medium_issues > 0:
        return OverallStatus.WARNING
    return OverallStatus.PASS
