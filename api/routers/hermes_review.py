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
from services.wiki_search import get_wiki_search

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

# 作业类型 → wiki 章节 + 真实条款清单 (防止 LLM 编不存在的条款)
CHAPTER_BY_TYPE = {
    "hot_work": "GB 30871-2022 第 5 章 动火作业",
    "confined_space": "GB 30871-2022 第 6 章 受限空间作业",
    "blind_plate": "GB 30871-2022 第 7 章 盲板抽堵作业",
    "high_above": "GB 30871-2022 第 8 章 高处作业",
    "lifting": "GB 30871-2022 第 9 章 吊装作业",
    "temp_power": "GB 30871-2022 第 10 章 临时用电作业",
    "earthwork": "GB 30871-2022 第 11 章 动土作业",
    "road_closure": "GB 30871-2022 第 12 章 断路作业",
}

# GB 30871-2022 全部条款清单 (从 wiki 真实抽取)
# 防止 LLM 编造不存在的条款号 (如 5.4.3, 5.4.4 等)
CLAUSE_INDEX = {
    "通用": "4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9, 4.10, 4.11, 4.12, 4.13, 4.14, 4.15, 4.16, 4.17, 4.18",
    "动火": "5.1.1, 5.1.2, 5.1.3, 5.1.4, 5.1.5, 5.2.1, 5.2.2, 5.2.3, 5.2.4, 5.2.5, 5.2.6, 5.2.7, 5.2.8, 5.2.9, 5.2.10, 5.2.11, 5.2.12, 5.2.13, 5.2.14, 5.2.15, 5.2.16, 5.3.1, 5.3.2, 5.4.1, 5.4.2, 5.5.1, 5.5.2",
    "受限空间": "6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8, 6.9, 6.10",
    "盲板抽堵": "7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8, 7.9, 7.10, 7.11, 7.12",
    "高处": "8.1.1, 8.1.2, 8.1.3, 8.2.1, 8.2.2, 8.2.3, 8.2.4, 8.2.5, 8.2.6, 8.2.7, 8.2.8, 8.2.9, 8.2.10, 8.2.11",
    "吊装": "9.1.1, 9.1.2, 9.1.3, 9.1.4, 9.1.5, 9.2.1, 9.2.2, 9.2.3, 9.2.4, 9.2.5, 9.2.6, 9.2.7, 9.2.8, 9.2.9, 9.2.10, 9.2.11, 9.2.12, 9.2.13, 9.2.14",
    "临时用电": "10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7, 10.8",
    "动土": "11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.7, 11.8, 11.9, 11.10, 11.11",
    "断路": "12.1, 12.2, 12.3, 12.4, 12.5",
}

# 作业类型 → 清单 key
TYPE_TO_CLAUSE_KEY = {
    "hot_work": "动火",
    "confined_space": "受限空间",
    "blind_plate": "盲板抽堵",
    "high_above": "高处",
    "lifting": "吊装",
    "temp_power": "临时用电",
    "earthwork": "动土",
    "road_closure": "断路",
}


def build_prompt(req: ReviewRequest) -> str:
    """构建发给 hermes 的审查 prompt - 严格 JSON 模式"""

    chapter = CHAPTER_BY_TYPE.get(req.permit_type, "GB 30871-2022 通用要求")
    # 注入真实条款清单 (从 wiki 抽取), 防止 LLM 编不存在的条款
    clause_key = TYPE_TO_CLAUSE_KEY.get(req.permit_type, "")
    clause_list = CLAUSE_INDEX.get(clause_key, "")
    general_list = CLAUSE_INDEX["通用"]

    permit_json = json.dumps(req.permit, ensure_ascii=False, indent=2)
    gas_json = json.dumps(req.gas_analyses, ensure_ascii=False, indent=2)
    safety_json = json.dumps(req.safety_checks, ensure_ascii=False, indent=2)

    # 16:29 状态: 平铺格式 + 让 hermes 自己调 /api/wiki 查 wiki 找条款 (16:29 验证 9/9 准确)
    # 关键: 不预给清单, 不强制 8 维度, 让 hermes 自由审查每个字段
    # 不用 /no_think - 16:29 准确那次没加 /no_think, 加了反而让 LLM 走捷径返回空数组
    prompt = f"""你是作业票合规性审查员. 用 llm-wiki 查 {chapter} 相关条款, 审查以下 {req.permit_type} 作业票字段, 输出所有不合规项.

字段:
{permit_json}

气体分析:
{gas_json}

安全措施:
{safety_json}

输出要求 (严格执行):
- **只输出**一个 ```json 代码块
- 平铺 JSON 数组, 每条不合规项一个元素, 格式: {{"field": "字段名", "issue": "≤100字", "clause": "GB 30871-2022 第 X.X 条", "suggestion": "≤80字"}}
- clause 找不到对应条款时留空字符串
- 没有不合规项则输出空数组 []
- 代码块外**不要**任何文字"""
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

    # 给每条 clause 附加 wiki 原文 (让用户自己核对条款是否对应)
    # 兼容两种格式: 8 维度 {category, issues: [...]} 和 平铺 {field, issue, clause, ...}
    try:
        wiki = get_wiki_search()
        for r in parsed.get("results", []):
            # 8 维度格式: issues 是数组; 平铺格式: r 本身就是一个 issue
            issues = r.get("issues", [r]) if r.get("issues") is not None else [r]
            for issue in issues:
                clause = issue.get("clause", "")
                if not clause:
                    continue
                # 提取条款号 (如 "5.3.1") - 从 "GB 30871-2022 第 5.3.1 条" 提取
                import re
                m = re.search(r'(\d+\.\d+(?:\.\d+)?)', clause)
                if m:
                    clause_num = m.group(1)
                    content = wiki.get_clause_content(clause_num)
                    if content:
                        issue["clause_content"] = content
    except Exception as e:
        logger.warning("附加 clause_content 失败 (不影响主流程): %s", e)

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
