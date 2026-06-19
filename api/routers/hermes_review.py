"""
Hermes AI 审查端点 - 让 hermes subprocess 调 llm-wiki 完成作业票审查

端点:
  POST /api/v1/permits/review-hermes  - 调 hermes 审查
  GET  /api/v1/permits/hermes-status  - 看 hermes 进程状态
"""

import json
import logging
import time
from typing import Optional

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel

from services.hermes_singleton import (
    call_hermes, extract_json, is_hermes_available,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/permits/hermes", tags=["hermes 审查"])


class ReviewRequest(BaseModel):
    permit_type: str
    permit: dict
    gas_analyses: list = []
    safety_checks: list = []


# 8 维度的固定顺序 + 描述 (审查输出格式)
REVIEW_DIMENSIONS = [
    ("1. 基础信息", "permit"),
    ("2. 风险辨识", "risk_identification"),
    ("3. 作业人员资质", "worker_names"),
    ("4. 气体检测", "gas_analyses"),
    ("5. 安全措施", "safety_checks"),
    ("6. 审批签字", "approval"),
    ("7. 作业时间管控", "time"),
    ("8. 监护与应急", "monitoring"),
]

# 作业类型 → wiki 章节
CHAPTER_BY_TYPE = {
    "hot_work": "GB 30871-2022 第 5 章 动火作业",
    "confined_space": "GB 30871-2022 第 6 章 受限空间作业",
    "blind_plate": "GB 30871-2022 第 7 章 盲板抽堵作业",
    "high_above": "GB 30871-2022 第 8 章 高处作业",
    "lifting": "GB 30871-2022 第 9 章 吊装作业",
    "temp_power": "GB 30871-2022 第 10 章 临时用电",
    "earthwork": "GB 30871-2022 第 11 章 动土作业",
    "road_closure": "GB 30871-2022 第 12 章 断路作业",
}


def build_prompt(req: ReviewRequest) -> str:
    """构建发给 hermes 的审查 prompt - 严格 JSON 模式"""
    
    chapter = CHAPTER_BY_TYPE.get(req.permit_type, "GB 30871-2022 通用要求")
    
    permit_json = json.dumps(req.permit, ensure_ascii=False, indent=2)
    gas_json = json.dumps(req.gas_analyses, ensure_ascii=False, indent=2)
    safety_json = json.dumps(req.safety_checks, ensure_ascii=False, indent=2)
    
    # 简化 prompt: 直接说"输出 JSON", hermes 更听话
    prompt = f"""你是作业票审查员. 用 llm-wiki 查 {chapter} 相关条款, 审查以下 {req.permit_type} 作业票字段, 按 8 维度输出严格 JSON:

字段:
{permit_json}

气体分析:
{gas_json}

安全措施:
{safety_json}

输出要求 (严格执行):
- **只输出**一个 ```json 代码块
- 8 个元素的 JSON 数组, 每个维度: {{"category": "1. 基础信息", "status": "pass|warning|fail", "issues": [...]}}
- issues 数组每条: {{"text": "≤80字", "field_key": "字段名", "suggestion": "≤60字", "clause": "GB 30871-2022 第 X.X 条"}}
- clause 找不到对应条款时留空字符串
- 代码块外**不要**任何文字
"""
    return prompt


@router.post("/review")
async def review_with_hermes(req: ReviewRequest):
    """
    调 hermes 审查作业票 (subprocess.run + --continue 续接)
    """
    if not await is_hermes_available():
        raise HTTPException(status_code=503, detail="hermes 命令不可用")
    
    prompt = build_prompt(req)
    
    t0 = time.time()
    try:
        # 审查: hermes LLM 推理需要 30-90s, 给 180s
        output = await call_hermes(prompt, timeout=180)
    except Exception as e:
        logger.error("hermes 失败: %s", e)
        raise HTTPException(status_code=500, detail=f"hermes 失败: {e}")
    elapsed = time.time() - t0
    
    parsed = extract_json(output)
    if parsed is None:
        return {
            "ok": False,
            "error": "JSON 解析失败",
            "raw_output": output[:3000],
            "elapsed": elapsed,
        }
    
    return {
        "ok": True,
        "results": parsed["results"],
        "parse_method": parsed["method"],
        "elapsed": elapsed,
        "raw_preview": output[:500],
    }


@router.post("/warmup")
async def hermes_warmup():
    """
    预热: 用户上传作业票时调用, 提前启动 hermes
    
    实际上 hermes subprocess 每次启动都慢, 但 --continue 能省 LLM 初始化.
    这个端点就是发个简单 prompt 让 hermes 启动, 让 --resume session 缓存生效.
    """
    if not await is_hermes_available():
        raise HTTPException(status_code=503, detail="hermes 命令不可用")
    
    t0 = time.time()
    try:
        # 预热: 用户上传作业票时调用, 提前启动 hermes
        # 实际 hermes 第一次启动要 30-90s (LLM 加载), 给 120s
        try:
            await call_hermes("回 ok 即可, 这是预热", timeout=120)
        except Exception as e:
            # 预热失败不算错, 审查时会重试
            logger.warning("hermes 预热失败 (审查时会重试): %s", e)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"hermes 预热失败: {e}")
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
