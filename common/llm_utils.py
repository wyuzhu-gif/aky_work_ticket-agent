"""
LLM 工具函数。

统一处理 OpenAI-compatible LLM 的常见问题：
- Qwen3.5-flash 等 thinking model 返回空 content 时的 reasoning_content 兜底
- Markdown code fence 清理
- 通用 LLM JSON 调用封装

Ollama 原生 client:
- 解决问题: ollama OpenAI 兼容 API (v1) 不支持 think=False 参数, glm-4.7 思考过程仍占 max_tokens
- 解决: 检测到 ollama, 改用 httpx 直接调 /api/chat, 带 think=False
"""

import json
import re
import time
import tempfile
from pathlib import Path
import httpx
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI

from common.logger import get_logger

logger = get_logger(__name__)


# =============================================================================
# 原生 ollama client (用 httpx 调 /api/chat, 真的支持 think=False)
# 接口尽量模拟 ChatOpenAI: invoke / ainvoke / bind / max_tokens / model_name
# =============================================================================
class OllamaChat:
    """ollama 原生 /api/chat 客户端, 真的支持 think=False (OpenAI 兼容 API 不支持)

    用法兼容 langchain ChatOpenAI:
        llm = OllamaChat(base_url='http://localhost:11434', model='glm-4.7-flash:latest', max_tokens=200)
        resp = llm.invoke([HumanMessage(content='hi')])  # resp.content = 实际输出 (无 thinking)
        llm_bound = llm.bind(max_tokens=100)  # 后续调用 max_tokens=100
    """

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "glm-4.7-flash:latest",
        temperature: float = 0.2,
        max_tokens: int = 200,
        think: bool = False,  # 关键: 真的禁掉思考 (nothink 模型的 chat_template 强制 false)
        timeout: float = 180.0,  # ⚠️ 2026-06-10 改 60.0 -> 180.0: 作业票审查 PDF 路径 MinerU 30s 跑完, 第二阶段 LLM 结构化 22GB qwen3.6:35b 处理 6471 字符 markdown 60s 不够
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.model_name = model  # 兼容 langchain
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.think = think
        self.timeout = timeout
        self.kwargs = {"max_tokens": max_tokens}  # 兼容 langchain bind

    def bind(self, max_tokens: int = None, **kwargs):
        """返回新的 OllamaChat 实例, 改 max_tokens 等参数 (跟 langchain ChatOpenAI.bind 同语义)"""
        new = OllamaChat(
            base_url=self.base_url,
            model=self.model,
            temperature=self.temperature,
            max_tokens=max_tokens or self.max_tokens,
            think=self.think,
            timeout=self.timeout,
        )
        return new

    def bind_tools(self, tools, **kwargs):
        """LangChain agent.create_agent 需要 bind_tools 接口
        把 langchain StructuredTool 转换成 ollama tools schema, 让 ollama 真的能调工具
        """
        ollama_tools = []
        for tool in tools:
            # langchain StructuredTool 有 args_schema (Pydantic) 或 .args
            try:
                # 尝试从 tool 提取 name/description/parameters
                name = getattr(tool, 'name', None) or str(tool)
                description = getattr(tool, 'description', '')
                # 获取 Pydantic schema
                if hasattr(tool, 'args') and tool.args:
                    params = tool.args
                elif hasattr(tool, 'args_schema') and tool.args_schema:
                    params = tool.args_schema.schema() if hasattr(tool.args_schema, 'schema') else {}
                else:
                    params = {"type": "object", "properties": {}}
                ollama_tools.append({
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": description,
                        "parameters": params,
                    },
                })
            except Exception as e:
                logger.warning(f"bind_tools: skip {tool}: {e}")

        # 返回新的 OllamaChat, _tools 字段带 tools schema
        new = OllamaChat(
            base_url=self.base_url,
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            think=self.think,
            timeout=self.timeout,
        )
        new._tools = ollama_tools
        logger.info(f"OllamaChat.bind_tools: {len(ollama_tools)} tools -> {[t['function']['name'] for t in ollama_tools]}")
        return new

    def _convert_messages(self, messages):
        """把 langchain 消息列表转 ollama 格式
        关键: AIMessage 的 tool_calls 字段必须保留, ToolMessage 必须标记 tool_call_id
        """
        result = []
        for msg in messages:
            if isinstance(msg, HumanMessage):
                role = "user"
            elif isinstance(msg, SystemMessage):
                role = "system"
            elif isinstance(msg, ToolMessage):
                role = "tool"
                # ToolMessage 必须有 tool_call_id 关联到 AIMessage 的 tool_calls[i].id
                content = msg.content if isinstance(msg.content, str) else str(msg.content)
                tc_id = getattr(msg, 'tool_call_id', None) or (msg.additional_kwargs.get('tool_call_id') if hasattr(msg, 'additional_kwargs') else None)
                result.append({
                    "role": "tool",
                    "content": content,
                    **({"tool_call_id": tc_id} if tc_id else {}),
                })
                continue
            else:
                role = "assistant"
            content = msg.content if isinstance(msg.content, str) else str(msg.content)
            ollama_msg = {"role": role, "content": content}
            # 关键: AIMessage 的 tool_calls 必须传给 ollama
            if role == "assistant" and hasattr(msg, 'tool_calls') and msg.tool_calls:
                ollama_msg["tool_calls"] = []
                for tc in msg.tool_calls:
                    # tc 可能是 dict 也有可能是 ToolCall 对象
                    if isinstance(tc, dict):
                        fn_name = tc.get('name') or tc.get('function', {}).get('name', '')
                        fn_args = tc.get('args')
                        if fn_args is None:
                            fn_args = tc.get('function', {}).get('arguments', {})
                        # 关键: arguments 必须是 dict 不能是 string (否则 ollama 解析失败)
                        if isinstance(fn_args, str):
                            try:
                                import json as _json
                                fn_args = _json.loads(fn_args) if fn_args else {}
                            except:
                                fn_args = {}
                        ollama_msg["tool_calls"].append({
                            "function": {
                                "name": fn_name,
                                "arguments": fn_args if fn_args else {},
                            }
                        })
            result.append(ollama_msg)
        return result

    def _invoke_sync(self, messages, max_tokens=None):
        """同步调 ollama /api/chat"""
        url = f"{self.base_url}/api/chat"
        ollama_messages = self._convert_messages(messages)
        payload = {
            "model": self.model,
            "messages": ollama_messages,
            "stream": False,
            "think": self.think,  # 关键: 真的禁掉思考
            "cache_prompt": False,  # 关键: 禁 prefix cache (顶层字段, 不是 options 里)
            "options": {
                "temperature": self.temperature,
                "num_predict": max_tokens or self.max_tokens,  # ollama 用 num_predict
            },
        }
        # 关键: 如果有 tools schema, 传给 ollama 让 LLM 真的能调工具
        # ollama 原生 /api/chat 接受 format='json' + tools list
        if hasattr(self, '_tools') and self._tools:
            payload["tools"] = self._tools
        t0 = time.time()
        try:
            # 关键诊断: 打印实际发给 ollama 的请求 (写到 INFO, 方便看)
            try:
                logger.info(f"ollama REQ: msg_count={len(payload['messages'])}, tools={len(payload.get('tools', []))}")
                for i, m in enumerate(payload['messages']):
                    c = m.get('content', '') or ''
                    logger.info(f"  msg[{i}] {m.get('role')}: content_len={len(c)}, content_preview='{c[:80]}'")
            except Exception as e:
                logger.warning(f"spy err: {e}")
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(url, json=payload)
            elapsed = time.time() - t0
            if resp.status_code != 200:
                raise RuntimeError(f"ollama {resp.status_code}: {resp.text[:500]}")
            data = resp.json()
            msg = data.get("message", {})
            content = msg.get("content", "")
            # 检查是否 thinking 占空间
            thinking = msg.get("thinking", "")
            # ollama tool calling: msg 里有 tool_calls 字段 [{function: {name, arguments}}]
            ollama_tool_calls = msg.get("tool_calls") or []
            # 转换成 langchain tool_calls 格式: [{name, args, id}, ...]
            lc_tool_calls = []
            for tc in ollama_tool_calls:
                fn = tc.get("function", {})
                lc_tool_calls.append({
                    "name": fn.get("name", ""),
                    "args": fn.get("arguments", {}),
                    "id": tc.get("id", f"call_{len(lc_tool_calls)}"),
                    "type": "tool_call",
                })
            logger.info(  # 改 DEBUG → INFO 方便看
                f"ollama invoke: {elapsed:.1f}s, model={self.model}, "
                f"content={len(content)} chars, thinking={len(thinking)} chars, "
                f"tool_calls={len(lc_tool_calls)}, "
                f"eval_count={data.get('eval_count')}, done={data.get('done_reason')}"
            )
            return AIMessage(
                content=content,
                tool_calls=lc_tool_calls if lc_tool_calls else [],  # 关键: tool_calls 字段传给 langchain
                response_metadata={
                    "token_usage": {
                        "prompt_tokens": data.get("prompt_eval_count", 0),
                        "completion_tokens": data.get("eval_count", 0),
                        "total_tokens": (data.get("prompt_eval_count", 0) + data.get("eval_count", 0)),
                    },
                    "model_name": self.model,
                    "finish_reason": data.get("done_reason", "stop"),
                },
            )
        except httpx.TimeoutException as e:
            logger.error(f"ollama timeout after {self.timeout}s: {e}")
            raise RuntimeError(f"ollama 调用超时 ({self.timeout}s)") from e
        except Exception as e:
            logger.error(f"ollama invoke failed: {e}")
            raise

    def invoke(self, messages, **kwargs):
        """同步 invoke (langchain ChatOpenAI 兼容接口)"""
        # bind 过来的 max_tokens 通过 kwargs 传
        max_tokens = kwargs.get("max_tokens") or self.max_tokens
        return self._invoke_sync(messages, max_tokens=max_tokens)

    async def ainvoke(self, messages, **kwargs):
        """异步 invoke (兼容 async context, 不阻塞 event loop)"""
        import asyncio
        max_tokens = kwargs.get("max_tokens") or self.max_tokens

        def _do():
            return self._invoke_sync(messages, max_tokens=max_tokens)

        return await asyncio.to_thread(_do)


# =============================================================================
# 统一 LLM 工厂 (build_llm)
# 目的: 所有 ChatOpenAI 调用走这里, think/temperature/base_url 统一管理
# 切换 ollama glm-4.7-flash:latest 时只需改 build_llm 一处
# =============================================================================
def build_llm(
    model: str = None,
    temperature: float = 0.2,
    max_tokens: int = 2000,  # 2000 token 详细分析 (用户要求 LLM 详细分析, 短回答不够; 之前 1000 时 LLM 抄 100+ 行 SQL 模板达到 token 限制就 done=length 没调工具)
    **kwargs,
) -> ChatOpenAI:
    """
    统一构造 ChatOpenAI 实例, 兼容 vLLM / Ollama / 阿里云 通义千问.

    自动从 settings 读 LLM_BASE_URL / LLM_API_KEY / LLM_PROVIDER.
    自动加 extra_body={"think": False} 禁掉 ollama glm-4.7 思考过程.

    Args:
        model: 覆盖默认模型 (默认从 settings.llm_model)
        temperature: 温度 (默认 0.2; ollama glm-4.7 默认 1.0 会乱, 强制 0.2)
        max_tokens: 最大 token (默认从 settings.llm_max_tokens)
        **kwargs: 传给 ChatOpenAI 的额外参数

    Returns:
        ChatOpenAI 实例
    """
    # 延迟 import 避免循环依赖
    from config.config import settings

    _model = model or settings.llm_model
    _base_url = settings.llm_base_url
    _api_key = settings.llm_api_key or "EMPTY"

    # ollama 特定: 禁掉 glm-4.7 的 thinking, 强制 temperature=0.2
    extra_body = dict(kwargs.pop("extra_body", {}) or {})
    provider = settings.llm_provider.lower() if settings.llm_provider else "vllm"

    if provider == "ollama":
        # glm-4.7-flash:latest 等思考模型, 必须显式 think=False
        extra_body.setdefault("think", False)

        # ollama 默认 temperature=1.0 会乱, 强制 0.2
        # (调用方传 temperature 参数可覆盖)
        if "temperature" not in kwargs:
            temperature = 0.2

    logger.debug(
        f"build_llm: provider={provider}, model={_model}, base_url={_base_url}, "
        f"temperature={temperature}, extra_body={extra_body}"
    )

    chat_kwargs = dict(
        model=_model,
        temperature=temperature,
        openai_api_key=_api_key,
        openai_api_base=_base_url,
        **kwargs,
    )
    # max_tokens 始终设 (默认 200, 防止 LLM 长输出 4000+ token 完整报告)
    chat_kwargs["max_tokens"] = max_tokens
    if extra_body:
        chat_kwargs["extra_body"] = extra_body

    # 关键: 检测到 ollama, 用原生 /api/chat client (真的支持 think=False)
    # vLLM / OpenAI 兼容服务用 ChatOpenAI
    if provider == "ollama":
        # 提取 base_url 的 host:port (去掉 /v1 后缀)
        ollama_base = _base_url.rstrip("/")
        if ollama_base.endswith("/v1"):
            ollama_base = ollama_base[:-3]
        llm = OllamaChat(
            base_url=ollama_base,
            model=_model,
            temperature=temperature,
            max_tokens=max_tokens,
            think=False,  # 强制禁掉思考
            timeout=60.0,
        )
        logger.info(f"build_llm: provider=ollama, using native /api/chat, model={_model}, max_tokens={max_tokens}, think=False")
        return llm

    # 非 ollama (vLLM / 通义千问 / OpenAI) 用 ChatOpenAI
    llm = ChatOpenAI(**chat_kwargs)
    return llm.bind(max_tokens=max_tokens)


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
    - 截断 JSON 修复(常见 max_tokens 截断场景)
    - 失败时记录完整 raw 到 logger + 临时文件,便于排查

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

    # 1) 尝试直接解析
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error(f"{error_context} direct json.loads failed: {e}")

    # 2) 截断修复: 找到最外层 { ... } 或 [ ... ], 补全缺失的闭合括号
    fixed = _try_fix_truncated_json(raw)
    if fixed is not None:
        try:
            obj = json.loads(fixed)
            logger.warning(f"{error_context} JSON was truncated, repaired successfully ({len(raw)}->{len(fixed)} chars)")
            return obj
        except json.JSONDecodeError as e:
            logger.error(f"{error_context} truncated-repair also failed: {e}")

    # 3) 完全失败: 记录完整 raw 便于排查
    logger.error(f"{error_context} returned non-JSON (full length={len(raw)}): {raw[:500]}")
    try:
        dump_path = Path(tempfile.gettempdir()) / f"llm_raw_{int(time.time())}_{error_context.replace(' ', '_')}.txt"
        dump_path.write_text(raw, encoding="utf-8", errors="replace")
        logger.error(f"{error_context} full raw dumped to {dump_path}")
    except Exception as dump_err:
        logger.error(f"{error_context} failed to dump raw: {dump_err}")
    return None


def _try_fix_truncated_json(raw: str) -> str | None:
    """
    Attempt to fix a truncated JSON string by:
    1) If we're in the middle of an unterminated string, find the last
       complete value (looking backwards for a closing quote followed by
       a comma/colon at the right depth) and truncate there.
    2) Strip trailing incomplete key/value (after the last complete , or :)
    3) Closing any unclosed braces/brackets
    Returns repaired string, or None if no JSON object/array detected.
    """
    # Find first { or [
    start = -1
    for i, ch in enumerate(raw):
        if ch in "[{":
            start = i
            break
    if start < 0:
        return None

    opener = raw[start]

    # Walk forward, count depth and string state
    depth = 0
    in_string = False
    escape_next = False
    last_safe_end = start  # last position where raw[:end] is balanced
    for i in range(start, len(raw)):
        ch = raw[i]
        if escape_next:
            escape_next = False
            continue
        if ch == "\\":
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            if not in_string:
                # Just closed a string. This is a candidate safe cut point.
                # But we want safe cuts ONLY at depth >= 1 (i.e., inside the top-level)
                # at the position right after the closing quote, since "..."
                # forms a complete string value or key.
                # However, if next char is `:` it's a key (need value); if `,` it's end of value.
                # Safest: just after the closing quote.
                if depth >= 1:
                    # Check what comes next; if it's , we're safe; if : we're after a key (still need value)
                    # For now, mark as candidate; we'll resolve at end
                    pass
            continue
        if in_string:
            continue
        if ch in "{[":
            depth += 1
        elif ch in "}]":
            depth -= 1
            if depth == 0:
                last_safe_end = i + 1
                break
        # Safe cut point after a comma or colon (these only appear in object/array context)
        if depth >= 1 and ch in ",:":
            # Move past the comma/colon to the next char
            # Actually, cut AT the comma/colon, then we close with } or ]
            last_safe_end = i

    # If we ended inside an unterminated string, we need to find the LAST
    # position where we had a complete value. The most reliable: scan
    # backwards from the end for a position where depth was 1 and the
    # previous char was `}` or `]` or a closing quote, and the char before
    # that was `,` or `:`.
    if in_string:
        # Re-walk but record last "complete value end" at depth=1
        depth2 = 0
        in_string2 = False
        esc2 = False
        last_complete_value_end = start
        for i in range(start, len(raw)):
            ch = raw[i]
            if esc2:
                esc2 = False
                continue
            if ch == "\\":
                esc2 = True
                continue
            if ch == '"':
                in_string2 = not in_string2
                if not in_string2 and depth2 >= 1:
                    # Just closed a string at depth >= 1: this is end of a key or value
                    # But check next non-space char: if `,` or `}` or `]` it's truly end
                    j = i + 1
                    while j < len(raw) and raw[j] in " \t\n":
                        j += 1
                    if j >= len(raw) or raw[j] in ",}]":
                        last_complete_value_end = i + 1
                continue
            if in_string2:
                continue
            if ch in "{[":
                depth2 += 1
            elif ch in "}]":
                depth2 -= 1
                if depth2 >= 1:
                    last_complete_value_end = i + 1
        # Now cut at last_complete_value_end
        truncated = raw[start:last_complete_value_end].rstrip(",: \t\n")
        open_braces = truncated.count("{") - truncated.count("}")
        open_brackets = truncated.count("[") - truncated.count("]")
        truncated += "}" * max(0, open_braces) + "]" * max(0, open_brackets)
        return truncated

    if depth == 0 and last_safe_end > start:
        return raw[start:last_safe_end]

    # Unclosed structures (no in_string issue)
    truncated = raw[start:last_safe_end].rstrip(",: \t\n")
    open_braces = truncated.count("{") - truncated.count("}")
    open_brackets = truncated.count("[") - truncated.count("]")
    truncated += "}" * max(0, open_braces) + "]" * max(0, open_brackets)
    return truncated
