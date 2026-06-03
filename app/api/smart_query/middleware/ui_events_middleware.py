"""
UI 事件中间件
在 LLM 返回时自动注入工具调用的简略描述到 AIMessage.additional_kwargs["ui_events"]
使用 LLM 自动生成工具调用的简洁描述（包含调用原因）

迁移自 SQLAgent-dev: backend/vanna/src/Improve/middleware/ui_events_middleware.py
改动：import 路径从 ..shared 改为 ..clients
"""

import logging
logger = logging.getLogger(__name__)
import json
import time
import contextvars
from typing import Callable, Any, List, Dict
from langchain.agents.middleware import wrap_model_call, wrap_tool_call  # type: ignore
from langchain.agents.middleware import ModelRequest, ModelResponse  # type: ignore
from langchain_core.messages import AIMessage  # type: ignore

# 导入共享的 LLM 实例
from ..clients import get_llm_instance


# 在一次 agent run 的上下文里累计工具事件
RUN_UI_EVENTS: contextvars.ContextVar[List[Dict[str, Any]]] = contextvars.ContextVar(
    "RUN_UI_EVENTS", default=[]
)

# 缓存用户问题，用于生成描述
CURRENT_QUESTION: contextvars.ContextVar[str] = contextvars.ContextVar(
    "CURRENT_QUESTION", default=""
)


def _brief(txt: Any, limit=160) -> str:
    """截断文本用于简略显示"""
    s = str(txt or "").replace("\n", " ")
    return s[:limit] + ("…" if len(s) > limit else "")


def _generate_tool_description_by_llm(
    tool_name: str, 
    args: dict, 
    user_question: str
) -> str:
    """使用 LLM 生成工具调用的简洁描述（包含调用原因）
    
    Args:
        tool_name: 工具名称
        args: 工具参数
        user_question: 用户原始问题
        
    Returns:
        LLM 生成的简洁描述（15-20字）
    """
    try:
        llm = get_llm_instance()
        if not llm:
            return _get_fallback_description(tool_name, args)
        
        prompt = f"""你是一个 SQL Agent 的动作描述生成器。用户提问："{user_question}"

当前正在调用工具：{tool_name}
工具参数：{json.dumps(args, ensure_ascii=False)}

请用一句话（15-20字）描述：
1. 正在做什么
2. 为什么要这样做（与用户问题的关系）

要求：
- 简洁清晰，面向用户
- 不要技术术语
- 直接输出描述文本，不要引号或额外解释

示例：
- "检查数据库版本，确保SQL语法兼容"
- "获取客户表结构，分析年龄字段"
- "执行查询统计女性客户的平均消费"
"""
        
        response = llm.invoke(prompt, config={"temperature": 0, "max_tokens": 50})
        description = response.content.strip().strip('"\'')
        
        if len(description) > 40:
            description = description[:37] + "..."
        
        return description
    
    except Exception as e:
        logger.warning(f"生成工具描述失败: {e}")
        return _get_fallback_description(tool_name, args)


def _get_fallback_description(tool_name: str, args: dict) -> str:
    """降级方案：使用简单映射生成描述"""
    tool_map = {
        'check_mysql_version': '检查数据库版本',
        'get_all_tables_info': '获取表信息',
        'get_table_schema': '分析表结构',
        'generate_sql': '生成SQL查询',
        'validate_sql_syntax': '验证SQL语法',
        'execute_sql': '执行数据库查询',
    }
    return tool_map.get(tool_name, f'执行{tool_name}')


# 1) 工具调用中间件：使用 LLM 生成简述
@wrap_tool_call
def ui_tool_trace(
    request,
    handler: Callable,
) -> Any:
    """拦截工具调用，使用 LLM 生成 UI 事件描述"""
    
    # 从 request 中提取工具名和参数
    tool_call = getattr(request, "tool_call", None)
    if tool_call:
        tool_name = tool_call.get("name", "unknown")
        tool_args = tool_call.get("args", {})
    else:
        tool_name = getattr(request, "tool_name", "unknown")
        tool_args = getattr(request, "tool_input", {})
    
    # 获取用户问题
    user_question = CURRENT_QUESTION.get() or "未知问题"
    
    t0 = time.time()
    
    # 使用 LLM 生成友好描述（包含原因）
    description = _generate_tool_description_by_llm(tool_name, tool_args, user_question)
    
    # 记录开始事件
    events = RUN_UI_EVENTS.get()
    events.append({
        "kind": "tool_start",
        "name": tool_name,
        "title": description,
        "args_brief": _brief(json.dumps(tool_args, ensure_ascii=False)),
        "ts": time.time()
    })
    RUN_UI_EVENTS.set(events)
    
    # 执行工具
    result = handler(request)
    
    # 记录结束事件
    dt = (time.time() - t0) * 1000
    
    if hasattr(result, "content"):
        out_brief = result.content
    else:
        out_brief = str(result)
    
    try:
        if isinstance(out_brief, (dict, list)):
            out_brief = json.dumps(out_brief, ensure_ascii=False)
    except Exception:
        pass
    
    events = RUN_UI_EVENTS.get()
    events.append({
        "kind": "tool_end",
        "name": tool_name,
        "title": f"{description}完成",
        "duration_ms": round(dt, 1),
        "output_brief": _brief(out_brief),
        "ts": time.time()
    })
    RUN_UI_EVENTS.set(events)
    
    # 将 ui_events 附加到工具返回结果上
    try:
        from langchain_core.messages import ToolMessage  # type:ignore
        if isinstance(result, ToolMessage):
            if not hasattr(result, 'additional_kwargs'):
                result.additional_kwargs = {}
            result.additional_kwargs['ui_events'] = list(events)
    except Exception as e:
        logger.warning(f"注入 ui_events 到 ToolMessage 失败: {e}")
    
    return result


# 2) 模型中间件：在返回的 AIMessage 上附加 ui_events
@wrap_model_call
def ui_model_trace(
    request: ModelRequest,
    handler: Callable[[ModelRequest], ModelResponse],
) -> ModelResponse:
    """拦截 LLM 调用，在 AIMessage 上注入 ui_events，并提取用户问题"""
    
    messages = getattr(request, "messages", [])
    if not messages:
        runtime = getattr(request, "runtime", None)
        if runtime and hasattr(runtime, "state"):
            messages = runtime.state.get("messages", [])
    
    for msg in messages:
        if getattr(msg, 'type', '') == 'human':
            user_question = getattr(msg, 'content', '')
            CURRENT_QUESTION.set(user_question)
            break
    
    RUN_UI_EVENTS.set([])
    
    t0 = time.time()
    resp = handler(request)
    dt = (time.time() - t0) * 1000
    
    try:
        ai_msg = getattr(resp, "message", resp)
        
        if isinstance(ai_msg, AIMessage):
            extra = dict(ai_msg.additional_kwargs or {})
            events = RUN_UI_EVENTS.get()
            events.append({
                "kind": "llm_end",
                "title": "模型思考完成",
                "duration_ms": round(dt, 1),
                "ts": time.time()
            })
            
            extra["ui_events"] = events
            ai_msg.additional_kwargs = extra
    
    except Exception as e:
        logger.warning(f"Failed to inject UI events: {e}")
    
    return resp


__all__ = ['ui_tool_trace', 'ui_model_trace', 'RUN_UI_EVENTS', 'CURRENT_QUESTION']
