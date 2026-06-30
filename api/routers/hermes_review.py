"""
Hermes AI 审查端点 - 直接读 GB 30871-2022 原文注入 prompt

架构简化 (2026-06-30):
  - 不再依赖 wiki_search / llm-wiki skill
  - 直接从 raw/papers 读 GB 30871 全文，按章节截取注入
  - hermes 只做 LLM 推理，不调任何 skill → 大幅减少耗时

端点:
  POST /api/v1/permits/hermes/review    - 调 hermes 审查
  POST /api/v1/permits/hermes/warmup    - 预热 hermes
  GET  /api/v1/permits/hermes/status    - 看 hermes 是否可用
"""

import json
import logging
import re
import time
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.hermes_singleton import (
    call_hermes, extract_json, is_hermes_available,
)
from services.gb30871 import get_regulation_context, get_clause_text

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/permits/hermes", tags=["hermes 审查"])


class ReviewRequest(BaseModel):
    permit_type: str
    permit: dict
    gas_analyses: list = []
    safety_checks: list = []


# 作业类型 → 中文名 (用于 prompt 描述)
PERMIT_TYPE_CN = {
    "hot_work": "动火作业",
    "confined_space": "受限空间作业",
    "blind_plate": "盲板抽堵作业",
    "high_above": "高处作业",
    "lifting": "吊装作业",
    "temp_power": "临时用电作业",
    "earthwork": "动土作业",
    "road_closure": "断路作业",
}


def build_prompt(req: ReviewRequest) -> str:
    """构建发给 hermes 的审查 prompt - 直接注入法规原文"""

    permit_type_cn = PERMIT_TYPE_CN.get(req.permit_type, req.permit_type)

    permit_json = json.dumps(req.permit, ensure_ascii=False, indent=2)
    gas_json = json.dumps(req.gas_analyses, ensure_ascii=False, indent=2)
    safety_json = json.dumps(req.safety_checks, ensure_ascii=False, indent=2)

    # 直接读取 GB 30871 对应章节原文
    regulation_text = get_regulation_context(req.permit_type)
    logger.info(
        "法规上下文: permit_type=%s, regulation_text=%d 字符",
        req.permit_type, len(regulation_text),
    )

    prompt = f"""你是作业票合规性审查员。依据 GB 30871-2022《危险化学品企业特殊作业安全规范》审查以下{permit_type_cn}作业票，输出所有不合规项。

【法规依据】（GB 30871-2022 原文）
{regulation_text}

【作业票字段】
{permit_json}

【气体分析记录】
{gas_json}

【安全措施确认】
{safety_json}

【输出要求】（严格执行）
1. 只输出一个 ```json 代码块，代码块外不要任何文字
2. 平铺 JSON 数组，每条不合规项一个元素，格式：{{"field": "中文字段名", "issue": "问题描述≤100字", "clause": "GB 30871-2022 第X.X条", "suggestion": "修改建议≤80字"}}
3. field 必须使用中文（如"气体分析时间"、"气体分析结果"、"分析人员姓名"等），不要用英文
4. clause 必须引用上方法规依据中实际存在的条款号（如"第5.3.1条"），禁止编造不存在的条款号
5. 如果找不到对应条款，clause 留空字符串""
6. 没有不合规项则输出空数组 []
"""
    return prompt


@router.post("/review")
async def review_with_hermes(req: ReviewRequest):
    """调 hermes 审查作业票"""
    if not await is_hermes_available():
        raise HTTPException(status_code=503, detail="hermes 命令不可用")

    prompt = build_prompt(req)

    t0 = time.time()
    try:
        # 不加载 llm-wiki skill，只做纯 LLM 推理 → 大幅减少耗时
        output = await call_hermes(prompt, timeout=300)
    except Exception as e:
        logger.error("hermes 失败: %s", e)
        raise HTTPException(status_code=500, detail=f"hermes 失败: {e}")
    elapsed = time.time() - t0

    parsed = extract_json(output)
    if parsed is None:
        logger.warning("JSON 解析失败, raw_output=%s", output[:1000])
        return {
            "ok": False,
            "error": "JSON 解析失败",
            "raw_output": output[:3000],
            "elapsed": elapsed,
        }

    # 记录解析结果用于调试
    results = parsed.get("results", [])
    logger.info(
        "hermes 解析成功: method=%s, results_count=%d, elapsed=%.1fs",
        parsed.get("method"), len(results), elapsed,
    )
    for i, r in enumerate(results):
        logger.info("  result[%d]: field=%s, clause=%s", i, r.get("field"), r.get("clause"))

    # 给每条 clause 附加法规原文（让用户核对条款是否对应）
    for r in results:
        clause = r.get("clause", "")
        if not clause:
            continue
        # 从 "GB 30871-2022 第5.3.1条" 提取条款号
        m = re.search(r'(\d+\.\d+(?:\.\d+)?)', clause)
        if m:
            clause_num = m.group(1)
            content = get_clause_text(clause_num)
            if content:
                r["clause_content"] = content
                logger.info("附加条款原文: %s → %d字符", clause_num, len(content))
            else:
                logger.warning("未找到条款原文: %s", clause_num)

    return {
        "ok": True,
        "results": results,
        "parse_method": parsed["method"],
        "elapsed": elapsed,
        "raw_preview": output[:500],
    }


@router.post("/warmup")
async def hermes_warmup():
    """预热: 用户上传作业票时调用，提前启动 hermes"""
    if not await is_hermes_available():
        raise HTTPException(status_code=503, detail="hermes 命令不可用")

    t0 = time.time()
    try:
        await call_hermes("回 ok 即可, 这是预热", timeout=120)
    except Exception as e:
        # 预热失败不算错，审查时会重试
        logger.warning("hermes 预热失败 (审查时会重试): %s", e)
    elapsed = time.time() - t0

    return {"status": "warmed_up", "elapsed": elapsed}


@router.get("/status")
async def hermes_status():
    """前端轮询: hermes 是否可用"""
    available = await is_hermes_available()
    return {
        "available": available,
        "hermes_bin": "/home/czys/.local/bin/hermes",
    }
