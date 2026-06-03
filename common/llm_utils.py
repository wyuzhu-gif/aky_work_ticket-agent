"""
LLM 工具函数。

统一处理 OpenAI-compatible LLM 的常见问题：
- Qwen3.5-flash 等 thinking model 返回空 content 时的 reasoning_content 兜底
- Markdown code fence 清理
- 通用 LLM JSON 调用封装
"""

import json
import re
from langchain_core.messages import AIMessage
from langchain_openai import ChatOpenAI

from common.logger import get_logger

logger = get_logger(__name__)


def extract_llm_content(resp: AIMessage) -> str:
    """
    从 LLM 响应中提取文本内容。

    处理 Qwen3.5-flash 等 thinking model 的特殊情况：
    - content 为空或仅空白时，回退到 reasoning_content
    - content 为 list 格式时，拼接 text 字段

    Args:
        resp: LangChain AIMessage 响应对象

    Returns:
        清理后的纯文本内容
    """
    raw = resp.content if hasattr(resp, "content") else resp

    # content 可能是 list（多模态响应）
    if isinstance(raw, list):
        raw = "".join(
            [c.get("text", "") if isinstance(c, dict) else str(c) for c in raw]
        )

    # Qwen thinking model: content 为空时使用 reasoning_content
    if not raw or not str(raw).strip():
        reasoning = getattr(resp, "additional_kwargs", {}).get("reasoning_content", "")
        if reasoning:
            logger.info(f"LLM content empty, using reasoning_content (len={len(reasoning)})")
            raw = reasoning

    return str(raw).strip()


def strip_code_fences(text: str) -> str:
    """
    清理 LLM 输出中的 Markdown code fence 包裹。

    移除开头的 ```json 或 ```，以及结尾的 ```。

    Args:
        text: 原始 LLM 输出文本

    Returns:
        清理后的文本
    """
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


async def llm_invoke_json(
    llm: ChatOpenAI,
    messages: list,
    *,
    error_context: str = "LLM",
) -> dict | list | None:
    """
    调用 LLM 并解析 JSON 响应。

    统一处理：
    - thinking model 空 content 兜底
    - code fence 清理
    - JSON 解析

    Args:
        llm: ChatOpenAI 实例
        messages: LangChain 消息列表
        error_context: 错误日志上下文描述

    Returns:
        解析后的 dict/list，解析失败返回 None
    """
    resp = await llm.ainvoke(messages)
    raw = extract_llm_content(resp)
    raw = strip_code_fences(raw)

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.error(f"{error_context} returned non-JSON: {raw[:500]}")
        return None
