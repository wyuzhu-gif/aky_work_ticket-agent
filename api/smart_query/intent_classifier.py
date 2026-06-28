"""
意图分类器：本地 LLM 直回 JSON，把用户问题分流到 3 路。

类别:
  - database_query:    涉及作业票数据库统计/查询 → 走 Vanna + llm-wiki（完整链路）
  - safety_knowledge:  纯安全知识/法规条款咨询 → 只走 llm-wiki（hermes 查 GB 30871 等）
  - casual_chat:       闲聊/打招呼 → 也走 hermes（统一入口, 由 streaming.py 的 casual 分支处理）

实现细节:
  - 复用 common.llm_utils.build_llm 工厂, 不引入新的 LLM 实例
  - prompt 最简化: 3 类标签 + JSON 输出格式, 不写过多规则 (LLM 在简洁规则下更稳)
  - max_tokens=50 足够 (只回 1 行 JSON)
  - 解析失败 fallback 到 safety_knowledge (最保守: 不查库, 只查法规)

为什么不用 hermes 做分类:
  - hermes 启动 ~12s, 分类一个 "你好" 等 15s+ 不值
  - 分类是纯文本判断, 不需要 llm-wiki / 工具
  - 分类 LLM 必须快, 让用户感觉"立刻识别"
"""

from __future__ import annotations

import json
import logging
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage

logger = logging.getLogger(__name__)

IntentType = Literal["database_query", "safety_knowledge", "casual_chat"]

# 3 个固定标签 - LLM 必须从中选一个
INTENT_LABELS = ("database_query", "safety_knowledge", "casual_chat")

# 兜底: 解析失败时返回 safety_knowledge (保守策略: 不查库, 只查法规)
FALLBACK_INTENT: IntentType = "safety_knowledge"

CLASSIFY_PROMPT = """你是意图分类器。把用户问题分成 3 类中的一类。

3 类标签:
- database_query: 用户要查询/统计/分析作业票数据 (例如 "昨天动火多少张", "博航染料本月作业票", "统计各部门")
- safety_knowledge: 用户问安全知识/法规条款 (例如 "动火作业需要哪些措施", "GB 30871 第几条", "受限空间作业审批要求")
- casual_chat: 闲聊/打招呼/系统问题 (例如 "你好", "你能做什么", "谢谢", "你是谁")

输出规则:
- 只输出 1 行 JSON: {"intent": "<3 类标签之一>"}
- 不要解释, 不要 markdown, 不要其他文字
- 不确定时输出 safety_knowledge"""


def classify_intent(question: str) -> IntentType:
    """
    同步分类用户问题意图。

    Args:
        question: 用户输入的问题

    Returns:
        IntentType: database_query / safety_knowledge / casual_chat

    失败兜底:
        - LLM 调用失败 → safety_knowledge (保守)
        - JSON 解析失败 → safety_knowledge (保守)
        - 不在 3 类标签中 → safety_knowledge (保守)
    """
    # 延迟 import: 跟 service.py 一样, 避免循环依赖
    from common.llm_utils import build_llm

    try:
        llm = build_llm(max_tokens=50)  # 只回 1 行 JSON, 50 token 足够
        messages = [
            SystemMessage(content=CLASSIFY_PROMPT),
            HumanMessage(content=question),
        ]
        resp = llm.invoke(messages)
        raw = (resp.content or "").strip()

        # 清理 code fence (LLM 偶尔包 ```json)
        raw = raw.replace("```json", "").replace("```", "").strip()

        # 尝试解析 JSON
        intent = _parse_intent_json(raw)
        if intent:
            logger.info(f"[Intent] '{question[:50]}' → {intent}")
            return intent

        # JSON 解析失败: 尝试从纯文本提取关键词 (兜底)
        logger.warning(f"[Intent] JSON parse failed, raw='{raw[:100]}', fallback to {FALLBACK_INTENT}")
        return FALLBACK_INTENT

    except Exception as e:
        logger.error(f"[Intent] classify failed: {e}, fallback to {FALLBACK_INTENT}")
        return FALLBACK_INTENT


def _parse_intent_json(raw: str) -> IntentType | None:
    """从 LLM 输出中解析 intent 字段。返回 None 表示解析失败。"""
    if not raw:
        return None
    try:
        obj = json.loads(raw)
        intent = obj.get("intent", "").strip()
        if intent in INTENT_LABELS:
            return intent  # type: ignore[return-value]
        return None
    except json.JSONDecodeError:
        # 兜底: LLM 可能直接输出 "database_query" 这种纯文本
        raw_lower = raw.lower().strip().strip('"').strip("'")
        if raw_lower in INTENT_LABELS:
            return raw_lower  # type: ignore[return-value]
        return None