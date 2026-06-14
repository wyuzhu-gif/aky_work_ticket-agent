"""
json_audit_service.py
迅援客户作业票审查：JSON 入参 → AuditReport 出参

不复用 PDF/MinerU/VLM 链路——输入直接是结构化 JSON，LLM 走 qwen3.5-flash。

主流程（同步主路径，异步包装由 router 决定）：
  1. Pydantic 强校验（WorkPermitRequest）→ fieldValidation 报告
  2. Python 跨字段校验（风险-措施覆盖、人员资质、时间合理性）→ riskMeasureCoverage 报告
  3. Milvus/wiki 检索 GB 30871 法规 → regulationMatches
  4. LLM 按 _validate.md 审查 → issues 列表
  5. LLM 写 aiReportMarkdown 完整报告
  6. 合并 → AuditReport
  7. return dict（不写库）
"""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from config.config import settings
from common.llm_utils import extract_llm_content, llm_invoke_json, strip_code_fences
from common.logger import get_logger
from common.xunyuan_permit_schema import (
    AuditIssue,
    AuditMetadata,
    AuditReport,
    AuditSummary,
    FieldStatus,
    FieldValidationItem,
    FieldValidationReport,
    IssueRiskLevel,
    IssueSource,
    OverallStatus,
    PermitType,
    RegulationMatch,
    RiskMeasureCoverageReport,
    SafetyMeasure,
    UnconfirmedMeasure,
    UncoveredRisk,
    WorkPermitRequest,
    compute_overall_status,
)
from services.wiki_search import get_wiki_search

logger = get_logger(__name__)


# ─────────────────────── 8 类典型风险-措施关键词映射 ───────────────────────
# 用于 Python 跨字段校验（不依赖 LLM）

PERMIT_TYPE_RISK_KEYWORDS: Dict[str, List[Tuple[str, List[str]]]] = {
    PermitType.CONFINED_SPACE.value: [
        # 风险关键词 → 必须有措施覆盖
        ("hypoxia", ["气体检测", "通风", "呼吸器", "氧含量"]),
        ("toxic_harmful_media", ["防毒", "呼吸器", "气体检测", "隔离"]),
        ("mechanical_injury", ["防护装备", "警戒", "隔离"]),
        ("fall_from_height", ["安全带", "速差自控器", "安全绳"]),
        ("electric_shock", ["断电", "接地", "绝缘"]),
        ("no_gas_detection", ["气体检测", "气体分析"]),
        ("no_blind_isolation", ["盲板", "隔离", "切断"]),
        ("rotating_equipment", ["断电", "锁定", "挂牌"]),
    ],
    PermitType.HOT_WORK.value: [
        ("fire", ["灭火器", "消防", "防火", "接火盆"]),
        ("explosion", ["可燃气体", "浓度", "检测"]),
        ("splash", ["防护", "接火盆", "隔离"]),
        ("insufficient_clearance", ["距离", "可燃物", "清理"]),
    ],
    PermitType.HEIGHT_WORK.value: [
        ("fall_from_height", ["安全带", "速差自控器", "防坠"]),
        ("object_strike", ["工具袋", "警戒", "隔离区"]),
    ],
    PermitType.TEMP_ELECTRIC.value: [
        ("electric_shock", ["接地", "绝缘", "断电", "漏电保护"]),
        ("short_circuit", ["绝缘", "短路保护", "接地"]),
    ],
    PermitType.LIFTING_WORK.value: [
        ("object_fall", ["吊带", "钢丝绳", "检查"]),
        ("mechanical_injury", ["警戒", "隔离", "持证"]),
    ],
    PermitType.EXCAVATION.value: [
        ("collapse", ["放坡", "支护", "围栏"]),
        ("underground_pipe_damage", ["管线交底", "人工开挖", "探测"]),
    ],
    PermitType.BLIND_PLATE.value: [
        ("leakage", ["盲板", "试漏", "隔离"]),
        ("wrong_position", ["双盲板", "位置确认", "编号"]),
    ],
    PermitType.ROAD_BREAK.value: [
        ("traffic_accident", ["警示", "围挡", "交通指挥"]),
        ("underground_cable_damage", ["探测", "人工开挖"]),
    ],
}


# ─────────────────────── 主服务类 ───────────────────────

class JsonAuditService:
    """
    迅援 JSON 入参审查服务。

    用法:
        service = JsonAuditService()
        report_dict = await service.audit(req)
    """

    def __init__(self):
        self.llm = self._init_llm()
        self.wiki = get_wiki_search()

    def _init_llm(self) -> ChatOpenAI:
        """复用 settings，temperature=0.1 保证审查稳定

        注意：不传 extra_body（qwen3.5-flash 默认不开启 thinking，传了反而可能让
        openai 客户端走不同 endpoint 触发 ConnectError）。
        """
        return ChatOpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            model=settings.llm_model,
            temperature=0.1,
            timeout=60,
        )

    # ───── 主入口 ─────
    async def audit(self, req: WorkPermitRequest) -> Dict[str, Any]:
        """
        同步主路径（不带 async 等待），但暴露 async 以便 router 用 await。

        Returns:
            dict (AuditReport 的 dict 形式)
        """
        t0 = time.time()
        logger.info(f"[xunyuan-audit] start: {req.permitType} {req.permitNo}")

        # 1. Pydantic 校验（入参已校验完，此处补"warnings"层）
        field_items = self._collect_field_warnings(req)
        field_report = FieldValidationReport(
            validated=17,  # 17 槽位
            passed=17 - sum(1 for it in field_items if it.status == FieldStatus.ERROR),
            warnings=sum(1 for it in field_items if it.status == FieldStatus.WARNING),
            errors=sum(1 for it in field_items if it.status == FieldStatus.ERROR),
            items=field_items,
        )

        # 2. Python 跨字段校验
        coverage = self._validate_coverage(req)

        # 3. 法规检索
        regulation_matches = self._retrieve_regulations(req)

        # 4. LLM 审查（issues + markdown）
        issues, ai_markdown = await self._llm_audit(req, regulation_matches)

        # 5. 汇总
        summary = AuditSummary(
            total=len(issues),
            high=sum(1 for i in issues if i.riskLevel == IssueRiskLevel.HIGH),
            medium=sum(1 for i in issues if i.riskLevel == IssueRiskLevel.MEDIUM),
            low=sum(1 for i in issues if i.riskLevel == IssueRiskLevel.LOW),
        )
        overall = compute_overall_status(
            field_errors=field_report.errors,
            high_issues=summary.high,
            medium_issues=summary.medium,
        )

        # 6. 拼装
        metadata = AuditMetadata(
            reviewedAt=datetime.now().isoformat(timespec="seconds"),
            llmModel=settings.llm_model,
            wikiChaptersRetrieved=len(regulation_matches),
            durationMs=int((time.time() - t0) * 1000),
        )
        report = AuditReport(
            permitNo=req.permitNo,
            permitType=req.permitType,
            overallStatus=overall,
            summary=summary,
            fieldValidation=field_report,
            riskMeasureCoverage=coverage,
            regulationMatches=regulation_matches,
            issues=issues,
            aiReportMarkdown=ai_markdown,
            metadata=metadata,
        )

        logger.info(
            f"[xunyuan-audit] done: {req.permitNo} "
            f"status={overall} issues={summary.total} duration={metadata.durationMs}ms"
        )
        return report.model_dump(mode="json")

    # ───── 1. 字段 warnings 收集（已通过 Pydantic 强校验后的"软"建议） ─────
    def _collect_field_warnings(self, req: WorkPermitRequest) -> List[FieldValidationItem]:
        """
        收集 warning 级字段问题。Pydantic 已拦截 error，这里只生成"建议"。

        warning 规则：
        - 计划时长超过 8h
        - 动火/受限空间缺 monitoringDeviceRef
        - contractorUnitId 缺失（建议有外协标识）
        """
        items: List[FieldValidationItem] = []

        # 1. 计划时长
        delta_hours = (req.plannedEndTime - req.plannedStartTime).total_seconds() / 3600
        if delta_hours > 8:
            items.append(FieldValidationItem(
                field="plannedEndTime",
                status=FieldStatus.WARNING,
                message=f"计划时长 {delta_hours:.1f} 小时，超过 8 小时班次，建议拆分多张票",
                ruleReference="GB 30871-2022 第5.2条（一般要求）",
            ))

        # 2. 动火/受限空间缺 monitoringDeviceRef
        if req.permitType in (PermitType.HOT_WORK, PermitType.CONFINED_SPACE):
            if not req.monitoringDeviceRef:
                items.append(FieldValidationItem(
                    field="monitoringDeviceRef",
                    status=FieldStatus.WARNING,
                    message=f"{req.permitType.value} 作业建议指定气体检测/监护设备",
                    ruleReference=(
                        "GB 30871-2022 第6.4条（受限空间气体检测）"
                        if req.permitType == PermitType.CONFINED_SPACE
                        else "GB 30871-2022 第5.3条（动火作业气体检测）"
                    ),
                ))

        # 3. contractorUnitId 缺失
        if not req.contractorUnitId:
            items.append(FieldValidationItem(
                field="contractorUnitId",
                status=FieldStatus.WARNING,
                message="未指定承包商单位（如果全部为本单位作业可忽略）",
            ))

        return items

    # ───── 2. 风险-措施覆盖度校验 ─────
    def _validate_coverage(self, req: WorkPermitRequest) -> RiskMeasureCoverageReport:
        """
        Python 跨字段校验（不调 LLM）：
          - 每个 riskFactor 是否至少 1 条 measureText 在关键词上"覆盖"
          - 每条 measure 的 involved 是否勾选 + 确认人是否填
        """
        permit_type = req.permitType.value
        risk_keywords = PERMIT_TYPE_RISK_KEYWORDS.get(permit_type, [])

        # 风险因素 key → 对应的关键词列表
        factor_keywords: Dict[str, List[str]] = {}
        for factor_key, kws in risk_keywords:
            factor_keywords[factor_key] = kws

        # 把措施文本拼一起便于子串匹配
        measure_texts = [m.measureText for m in req.safetyMeasuresJson]
        joined_measures = " ".join(measure_texts)

        # 1. uncovered: 风险因素没找到任何对应关键词
        uncovered: List[UncoveredRisk] = []
        for factor in req.riskFactorsJson:
            kws = factor_keywords.get(factor, [])
            if not kws:
                # 未知风险类型，尝试按"是否至少有一条措施"判定
                # 严苛模式：如果此风险不在我们的典型映射里，认为"无法验证覆盖度"→ 跳过
                continue
            # 任意关键词在 joined_measures 里出现 → 算覆盖
            hit = any(kw in joined_measures for kw in kws)
            if not hit:
                uncovered.append(UncoveredRisk(
                    riskFactor=factor,
                    reason=f"未在措施列表中找到应对关键词: {'/'.join(kws[:3])}",
                ))

        # 2. unconfirmed: involved=false + confirmerName 缺失
        unconfirmed: List[UnconfirmedMeasure] = []
        for m in req.safetyMeasuresJson:
            if not m.is_involved():
                if not m.confirmerName:
                    unconfirmed.append(UnconfirmedMeasure(
                        measureText=m.measureText,
                        reason="未勾选（involved=false）且无确认人签名",
                    ))
                else:
                    unconfirmed.append(UnconfirmedMeasure(
                        measureText=m.measureText,
                        reason=f"未勾选（involved=false），仅 {m.confirmerName} 签字未生效",
                    ))

        return RiskMeasureCoverageReport(
            riskFactorCount=len(req.riskFactorsJson),
            measureCount=len(req.safetyMeasuresJson),
            uncovered=uncovered,
            unconfirmed=unconfirmed,
        )

    # ───── 3. 法规检索 ─────
    def _retrieve_regulations(self, req: WorkPermitRequest) -> List[RegulationMatch]:
        """
        从 LLM Wiki (FTS5) 拉此票种对应的 GB 30871 法规。
        """
        try:
            context = self.wiki.get_permit_review_context(
                req.permitType.value,
                max_chars=4000,
            )
        except Exception as e:
            logger.warning(f"wiki retrieve failed: {e}")
            context = ""

        if not context:
            return [RegulationMatch(
                category=f"GB 30871-2022 {req.permitType.value} 章节",
                matchedClauses=[],
            )]

        # 抽取关键条款编号（如"第6.4条"）
        clauses = re.findall(r"第\s*\d+(?:\.\d+)?\s*条", context)
        clauses = list(dict.fromkeys(clauses))[:10]  # 去重保序

        category_label = {
            PermitType.CONFINED_SPACE: "GB 30871-2022 第6章 受限空间作业",
            PermitType.HOT_WORK: "GB 30871-2022 第5章 动火作业",
            PermitType.HEIGHT_WORK: "GB 30871-2022 第7章 高处作业",
            PermitType.TEMP_ELECTRIC: "GB 30871-2022 第4章 临时用电作业",
            PermitType.BLIND_PLATE: "GB 30871-2022 第8章 盲板抽堵作业",
            PermitType.LIFTING_WORK: "GB 30871-2022 第9章 起重作业",
            PermitType.EXCAVATION: "GB 30871-2022 第10章 动土作业",
            PermitType.ROAD_BREAK: "GB 30871-2022 第11章 断路作业",
        }.get(req.permitType, "GB 30871-2022")

        return [RegulationMatch(
            category=category_label,
            matchedClauses=clauses,
        )]

    # ───── 4. LLM 审查 ─────
    async def _llm_audit(
        self,
        req: WorkPermitRequest,
        regulation_matches: List[RegulationMatch],
    ) -> Tuple[List[AuditIssue], str]:
        """
        LLM 审查，返回 (issues, aiReportMarkdown)。

        LLM 拿到：
          - 法规上下文（from wiki）
          - 作业票 JSON
          - options.skipDataInsufficientCategories
        输出：严格 JSON { "issues": [...], "report_markdown": "..." }
        """
        # 法规上下文
        reg_text = "\n".join(
            f"### {m.category}\n" + "\n".join(f"- {c}" for c in m.matchedClauses)
            for m in regulation_matches
        )

        # 作业票 JSON（去掉 options 字段，LLM 不需要）
        # mode='json' 让 Pydantic 把 datetime/Enum 转成字符串
        permit_dict = req.model_dump(exclude={"options"}, exclude_none=True, mode="json")
        permit_json = json.dumps(permit_dict, ensure_ascii=False, indent=2)

        # 跳过的 4 维度（由 Pydantic + Python 已部分覆盖；LLM 主要审查其他维度）
        skip_hint = ""
        if req.options.skipDataInsufficientCategories:
            skip_hint = (
                "下列 4 个维度因输入数据不充分（无审批签字链/气体分析时序/完工验收/交叉作业），"
                "**直接跳过，不要编造审查意见**：\n"
                "  - 审批签字链是否齐全\n"
                "  - 气体分析时序合规性\n"
                "  - 完工验收流程\n"
                "  - 交叉作业冲突检查\n\n"
                "如确需审查这些维度，请建议客户在 Phase 2 通过 _extra 字段补充数据。\n\n"
            )

        system_prompt = f"""你是 GB 30871-2022《危险化学品企业特殊作业安全规范》的合规审查专家。
你的输入是一张作业票的结构化 JSON 字段 + 法规上下文。
票种: {req.permitType.value} ({_permit_type_zh(req.permitType)})
风险等级: {req.riskLevel.value}

{skip_hint}**只审查下列 4 个可审查的维度**（数据充分）：
1. **人员配置**：作业负责人/监护人/安全员是否齐全、是否有重复（principalUser/guardianUser/safetyOfficerUser 三者至少 1 个）
2. **风险-措施覆盖度**：每个 riskFactor 是否至少 1 条 measureText 应对。重要：只检查现有 riskFactor 列表是否被措施覆盖，不要建议增加"应该"列出的风险 —— 你没看到的不代表客户没考虑
3. **风险辨识语义合法性**：riskFactor 取值是否合理。例如把"未做某事"（如 no_gas_detection）当成风险因素是逻辑错误 —— 这种情况要标 issue 但 riskLevel=低，因为可能是字段语义不统一而非客户错误
4. **措施完整性**：measureText 是否明确、involved 是否"勾选生效"（即 is_involved() 返回 true）、confirmerName 是否填
5. **时间合理性**：plannedStart/End 顺序、时长是否超 8h 班次

注意：involved 字段是异构的（前端可能传 True/是/1/0/true/否），后端已经统一归一化为标准布尔值。不要把 involved 数据格式不规范当成 issue —— 你拿到的 JSON 里它已经是标准格式。

输出严格 JSON（不要任何额外文字）：
{{
  "issues": [
    {{
      "type": "气体分析不合格",
      "riskLevel": "高/中/低",
      "category": "现场控制措施落实",
      "fieldKey": "riskFactorsJson[0]",
      "text": "具体问题描述",
      "explanation": "违反 GB 30871-2022 第X条要求",
      "suggestedFix": "整改建议"
    }}
  ],
  "report_markdown": "## 作业票审查报告\\n### 总体结论\\n..."
}}

如果无问题，issues 设为空数组 []，report_markdown 写 "本次审查未发现明显问题"。"""

        user_prompt = (
            f"## 法规上下文\n{reg_text}\n\n"
            f"## 作业票 JSON\n```json\n{permit_json}\n```\n\n"
            "请按 system prompt 定义的 4-5 维度严格审查，输出 JSON。"
        )

        raw: str = ""
        try:
            resp = await self.llm.ainvoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
            ])
            raw = extract_llm_content(resp)
            if not raw.strip().startswith(("{", "[")):
                # 重试一次，要求严格 JSON
                retry = await self.llm.ainvoke([
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=user_prompt + "\n\n请再次确保输出严格 JSON。"),
                ])
                raw = extract_llm_content(retry)

            raw = strip_code_fences(raw)
            parsed = json.loads(raw)

            raw_issues = parsed.get("issues", [])
            issues: List[AuditIssue] = []
            for idx, it in enumerate(raw_issues):
                try:
                    issues.append(AuditIssue(
                        id=f"iss-llm-{idx + 1}",
                        type=it.get("type", "未分类"),
                        riskLevel=IssueRiskLevel(it.get("riskLevel", "中")),
                        category=it.get("category", "未分类"),
                        fieldKey=it.get("fieldKey", "未知"),
                        text=it.get("text", ""),
                        explanation=it.get("explanation", ""),
                        suggestedFix=it.get("suggestedFix", ""),
                        source=IssueSource.LLM,
                    ))
                except Exception as e:
                    logger.warning(f"LLM issue {idx} 解析失败: {e}; 跳过")

            ai_markdown = parsed.get("report_markdown", "（LLM 未生成完整报告）")
            return issues, ai_markdown

        except json.JSONDecodeError as e:
            logger.error(f"LLM 输出非 JSON: {e}; raw={raw[:200]}")
            return [], "（LLM 输出解析失败，无完整报告）"
        except Exception as e:
            logger.error(f"LLM 调用失败: {e}", exc_info=True)
            return [], f"（LLM 审查失败: {str(e)[:200]}）"


def _permit_type_zh(p: PermitType) -> str:
    """8 类作业票中文名"""
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


# ─────────────────────── 单例 ───────────────────────

_service_instance: Optional[JsonAuditService] = None


def get_json_audit_service() -> JsonAuditService:
    global _service_instance
    if _service_instance is None:
        _service_instance = JsonAuditService()
    return _service_instance
