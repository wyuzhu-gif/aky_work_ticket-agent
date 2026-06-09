"""
追踪中间件
用于调试和监控 Agent 的执行过程

迁移自 SQLAgent-dev: backend/vanna/src/Improve/middleware/trace_middleware.py
无改动：不依赖 shared 模块
"""

import logging
logger = logging.getLogger(__name__)
import json
import time
from typing import Callable, Any
from langchain.agents.middleware import wrap_model_call, wrap_tool_call  # type: ignore
from langchain.agents.middleware import ModelRequest, ModelResponse  # type: ignore
from langchain_core.messages import AIMessage  # type: ignore


def _print_message(i, msg):
    """打印单条消息的辅助函数"""
    msg_type = getattr(msg, 'type', 'unknown')
    content = getattr(msg, 'content', str(msg))
    
    if msg_type == 'system':
        logger.info(f"[{i}] System Prompt:\n{content[:50]}{'...' if len(content) > 50 else ''}\n")
    elif msg_type == 'human':
        logger.info(f"[{i}] User:\n{content[:100]}{'...' if len(content) > 100 else ''}\n")
    elif msg_type == 'ai':
        logger.info(f"[{i}] AI:\n{content[:100] if content else '(tool calls only)'}{'...' if len(content) > 100 else ''}\n")
    elif msg_type == 'tool':
        tool_name = getattr(msg, 'name', 'unknown')
        logger.info(f"[{i}] Tool ({tool_name}):\n{str(content)[:100]}{'...' if len(str(content)) > 100 else ''}\n")


@wrap_model_call
def trace_model_call(
    request: ModelRequest,
    handler: Callable[[ModelRequest], ModelResponse],
) -> ModelResponse:
    """拦截 LLM 调用，记录输入/输出/耗时"""
    t0 = time.time()
    
    messages = getattr(request, "messages", [])
    if not messages:
        runtime = getattr(request, "runtime", None)
        if runtime and hasattr(runtime, "state"):
            messages = runtime.state.get("messages", [])
    logger.info("[LLM START]")
    
    if len(messages) <= 2:
        for i, msg in enumerate(messages):
            _print_message(i, msg)
    else:
        _print_message(0, messages[0])
        logger.info(f"  ... (skip {len(messages) - 2} messages) ...\n")
        _print_message(len(messages) - 1, messages[-1])
    
    resp = handler(request)
    
    dt = (time.time() - t0) * 1000
    logger.info(f"\n [LLM END] {dt:.1f} ms")
    
    ai_message = getattr(resp, "message", resp)
    if isinstance(ai_message, AIMessage):
        content = ai_message.content or ""
        logger.info(f"AIMessage content:\n{content[:100]}{'...' if len(content) > 100 else ''}")
        if getattr(ai_message, "tool_calls", None):
            logger.info(f"\nTool calls requested: {len(ai_message.tool_calls)}")
            for i, tc in enumerate(ai_message.tool_calls, 1):
                logger.info(f"  [{i}] {tc.get('name', 'unknown')}")
                args = tc.get('args', {})
                args_str = json.dumps(args, ensure_ascii=False, indent=2)
                logger.info(f" Args: {args_str[:100]}{'...' if len(args_str) > 100 else ''}")
    else:
        logger.info(f"Raw output:\n{str(ai_message)[:100]}")
    
    return resp


@wrap_tool_call
def trace_tool_call(
    request,
    handler: Callable,
) -> Any:
    """拦截工具调用，记录入参/结果/耗时"""
    tool_call = getattr(request, "tool_call", None)
    if tool_call:
        tool_name = tool_call.get("name", "unknown")
        tool_input = tool_call.get("args", {})
    else:
        tool_name = getattr(request, "tool_name", "unknown")
        tool_input = getattr(request, "tool_input", {})
    
    compact_tools = {"get_all_tables_info", "get_table_schema"}
    is_compact = tool_name in compact_tools

    logger.info(f"[TOOL START] {tool_name}")

    args_str = json.dumps(tool_input, ensure_ascii=False, indent=2)
    logger.info(f"Args:\n{args_str[:600]}{'...' if len(args_str) > 600 else ''}")
    
    t0 = time.time()
    result = handler(request)
    dt = (time.time() - t0) * 1000
    
    logger.info(f"\n[TOOL END] {dt:.1f} ms")
    
    if hasattr(result, "content"):
        preview = str(result.content)
    else:
        preview = str(result)
    
    if is_compact:
        _print_compact_output(tool_name, preview)
    else:
        logger.info(f"Output:\n{preview[:100]}{'...' if len(preview) > 100 else ''}")
    
    return result


def _print_compact_output(tool_name: str, text: str) -> None:
    """精简打印工具输出"""
    import re
    
    logger.info(f"Output (精简模式):")
    
    stats = []
    
    table_count_match = re.search(r"表数量\s*:\s*(\d+)", text)
    if table_count_match:
        stats.append(f"表数量: {table_count_match.group(1)}")
    
    col_matches = re.findall(r"列数\s*:\s*(\d+)", text)
    if col_matches:
        total_cols = sum(int(c) for c in col_matches)
        stats.append(f"总列数: {total_cols}")
    
    ddl_count = text.count("CREATE TABLE")
    if ddl_count:
        stats.append(f"DDL 语句: {ddl_count} 个")
    
    table_names_match = re.findall(r"^表名\s*:\s*(.+)$", text, flags=re.MULTILINE)
    if table_names_match:
        table_list = ", ".join(table_names_match[:5])
        if len(table_names_match) > 5:
            table_list += f" ... (共{len(table_names_match)}张)"
        stats.append(f"表清单: {table_list}")
    
    if stats:
        for stat in stats:
            logger.info(f"   {stat}")
    else:
        logger.info(f"   {text[:300]}{'...' if len(text) > 300 else ''}")


# 异步版本 (trace_model_call_async / trace_tool_call_async) 已于 2026-06 清理
# 历史背景: 早期为支持 agent.astream 路径, 改用 sync stream 后不需要

