"""
SSE 流式生成器
从 SQLAgent-dev 的 api_server.py chat_stream 提取而来
负责 Agent 执行过程中的 SSE 事件推送

SSE 事件格式：
- {"type": "step", "action": "...", "status": "preparing|running|completed"}
- {"type": "data", "data": [...], "columns": [...], "sql": "..."}
- {"type": "answer", "content": "...", "done": false}
- {"type": "chart_config", "config": {...}}
- {"type": "done", "session_id": "..."}
- {"type": "error", "message": "..."}
"""

import os
import re
import json
import time
import asyncio
import logging
from typing import Optional, List, Dict, Any
from decimal import Decimal

logger = logging.getLogger(__name__)


def convert_decimals(obj):
    """将对象中的Decimal类型转换为float，使其可JSON序列化"""
    if isinstance(obj, dict):
        return {k: convert_decimals(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_decimals(item) for item in obj]
    elif isinstance(obj, Decimal):
        return float(obj)
    else:
        return obj


async def generate_chat_stream(
    agent,
    question: str,
    session_id: str,
    messages_payload: list,
    enable_training: bool = False,
    vanna_client=None,
    recursion_limit: int = 150,
):
    """
    异步生成器：执行 Agent 并以 SSE 格式推送结果
    
    Args:
        agent: NL2SQL Agent 实例
        question: 用户问题
        session_id: 会话 ID
        messages_payload: 带历史上下文的消息列表
        enable_training: 是否启用训练决策
        vanna_client: Vanna 客户端（enable_training=True 时需要）
        recursion_limit: Agent 递归限制
    """
    from .clients import get_last_query_result, clear_last_query_result
    from .agent import PostTrainingProcessor
    from .sessions import add_message

    # 连续空结果计数器（防止 agent 死循环）
    consecutive_empty_results = 0
    MAX_CONSECUTIVE_EMPTY = 3

    try:
        cfg = {
            "configurable": {"thread_id": f"session-{session_id}"},
            "recursion_limit": recursion_limit,
        }

        final_event = None
        last_tool = None

        # 第一阶段：实时推送 Agent 执行步骤
        for event in agent.stream(
            {"messages": messages_payload},
            stream_mode="values",
            config=cfg,
        ):
            final_event = event
            messages = event.get("messages", [])

            if messages:
                last_msg = messages[-1]
                msg_type = getattr(last_msg, 'type', 'unknown')

                # 检测工具调用（立即推送工具名）
                if msg_type == 'ai' and hasattr(last_msg, 'tool_calls') and last_msg.tool_calls:
                    for tool_call in last_msg.tool_calls:
                        tool_name = tool_call.get('name', 'unknown')

                        if tool_name != last_tool:
                            last_tool = tool_name
                            step_data = {
                                'type': 'step',
                                'action': f'{tool_name}',
                                'tool_name': tool_name,
                                'status': 'preparing',
                            }
                            yield f"data: {json.dumps(step_data, ensure_ascii=False)}\n\n"

                # 检测工具执行结果
                elif msg_type == 'tool' and last_tool:
                    # 检测连续空结果
                    tool_content = getattr(last_msg, 'content', '')
                    if last_tool == 'execute_sql' and '查询结果为空' in tool_content:
                        consecutive_empty_results += 1
                        logger.warning(f"[Loop Guard] Consecutive empty results: {consecutive_empty_results}")
                        if consecutive_empty_results >= MAX_CONSECUTIVE_EMPTY:
                            logger.error(f"[Loop Guard] Agent stuck in empty-result loop ({consecutive_empty_results}x), forcing stop")
                            error_data = {
                                'type': 'error',
                                'message': f'智能查询连续{consecutive_empty_results}次返回空结果，已自动终止。请尝试换一种问法或更具体的问题。'
                            }
                            yield f"data: {json.dumps(error_data, ensure_ascii=False)}\n\n"
                            break
                    elif last_tool == 'execute_sql' and '查询成功' in tool_content:
                        consecutive_empty_results = 0  # 重置计数
                    additional_kwargs = getattr(last_msg, 'additional_kwargs', {})
                    ui_events = additional_kwargs.get('ui_events', [])

                    duration_ms = None
                    llm_description = None
                    tool_result = None

                    for ui_event in ui_events:
                        if ui_event.get('name') == last_tool:
                            if ui_event.get('kind') == 'tool_start':
                                llm_description = ui_event.get('title', '')
                            elif ui_event.get('kind') == 'tool_end':
                                duration_ms = ui_event.get('duration_ms')

                    tool_content = getattr(last_msg, 'content', '')
                    if tool_content:
                        tool_result = tool_content[:500] if len(tool_content) > 500 else tool_content

                    if llm_description:
                        step_data = {
                            'type': 'step',
                            'action': llm_description,
                            'tool_name': last_tool,
                            'status': 'running',
                            'update': True
                        }
                        yield f"data: {json.dumps(step_data, ensure_ascii=False)}\n\n"

                    step_data = {
                        'type': 'step',
                        'action': llm_description or f'{last_tool}',
                        'tool_name': last_tool,
                        'status': 'completed',
                        'duration_ms': duration_ms,
                        'result': tool_result,
                        'update': True
                    }
                    yield f"data: {json.dumps(step_data, ensure_ascii=False)}\n\n"

                # 检测直接回答
                elif msg_type == 'ai' and not (hasattr(last_msg, 'tool_calls') and last_msg.tool_calls):
                    content = getattr(last_msg, 'content', '').strip()
                    if content:
                        step_data = {
                            'type': 'step',
                            'action': '直接回答用户问题',
                            'tool_name': 'direct_answer',
                            'status': 'completed',
                        }
                        yield f"data: {json.dumps(step_data, ensure_ascii=False)}\n\n"

            await asyncio.sleep(0.01)

        # 第二阶段：提取并推送查询数据
        if final_event:
            messages = final_event.get("messages", [])
            answer = None
            sql_query = None
            query_data = None

            # 从全局缓存获取 DataFrame
            df = get_last_query_result()
            if df is not None and len(df) > 0:
                query_data = df.to_dict('records')
                query_data = convert_decimals(query_data)
                logger.info(f"[Data Extraction] Retrieved query data, rows: {len(query_data)}")
                clear_last_query_result()
            else:
                logger.warning("[Data Extraction] No query result in cache")

            # 提取执行的 SQL
            for msg in messages:
                if getattr(msg, 'type', '') == 'ai' and hasattr(msg, 'tool_calls') and msg.tool_calls:
                    for tool_call in msg.tool_calls:
                        if tool_call.get('name') == 'execute_sql':
                            args = tool_call.get('args', {})
                            sql_query = args.get('sql', '')
                            if sql_query:
                                break
                    if sql_query:
                        break

            # 推送查询数据
            if query_data:
                data_event = {
                    'type': 'data',
                    'data': query_data,
                    'columns': list(query_data[0].keys()) if query_data else [],
                    'sql': sql_query
                }
                yield f"data: {json.dumps(data_event, ensure_ascii=False)}\n\n"

            # 提取最终答案
            for msg in reversed(messages):
                if getattr(msg, 'type', '') == 'ai':
                    content = getattr(msg, 'content', '').strip()
                    if content and len(content) > 0:
                        answer = content
                        step_data = {
                            'type': 'step',
                            'action': '直接回答用户问题',
                            'tool_name': 'direct_answer',
                            'status': 'completed',
                        }
                        yield f"data: {json.dumps(step_data, ensure_ascii=False)}\n\n"
                        break

            if answer:
                # 处理图表配置
                chartconfig_pattern = r'```chartconfig\s*\n?(.*?)\n?```'
                chartconfig_match = re.search(chartconfig_pattern, answer, re.DOTALL)
                chart_config = None

                if chartconfig_match:
                    try:
                        chart_config_str = chartconfig_match.group(1).strip()
                        chart_config = json.loads(chart_config_str)
                    except (json.JSONDecodeError, Exception) as e:
                        logger.warning(f"Chart config parse failed: {e}")
                        chart_config = None
                    answer = re.sub(chartconfig_pattern, '', answer, flags=re.DOTALL).strip()

                if chart_config:
                    chart_event = {
                        'type': 'chart_config',
                        'config': chart_config
                    }
                    yield f"data: {json.dumps(chart_event, ensure_ascii=False)}\n\n"

                # 流式推送答案（逐字符）
                for char in answer:
                    chunk_data = {
                        'type': 'answer',
                        'content': char,
                        'done': False
                    }
                    yield f"data: {json.dumps(chunk_data, ensure_ascii=False)}\n\n"
                    await asyncio.sleep(0.02)

            # 训练决策
            if enable_training and final_event and vanna_client:
                try:
                    processor = PostTrainingProcessor()
                    decision_result = processor.decide_and_add_to_training(
                        question=question,
                        conversation_history=final_event["messages"],
                        vanna_client=vanna_client
                    )
                    logger.info(f"Training decision: {decision_result}")
                except Exception as e:
                    logger.warning(f"Training decision failed: {e}")

            # 保存 AI 回复到会话（含富数据：查询结果、图表、SQL）
            if answer:
                # 构建富数据
                _query_data = None
                if query_data:
                    first_row = query_data[0] if query_data else {}
                    _query_data = {
                        "columns": list(first_row.keys()) if isinstance(first_row, dict) else [],
                        "data": query_data,
                        "sql": sql_query or "",
                    }
                # chart_config 在 answer 解析阶段赋值，此处安全读取
                _chart_cfg = locals().get("chart_config")
                logger.info(f"[Session Save] session={session_id}, has_query_data={_query_data is not None}, has_chart={_chart_cfg is not None}, sql={bool(sql_query)}")
                add_message(
                    session_id=session_id,
                    role="assistant",
                    content=answer,
                    query_data=_query_data,
                    chart_config=_chart_cfg,
                )

        # 结束标记
        done_data = {"type": "done", "session_id": session_id}
        yield f"data: {json.dumps(done_data, ensure_ascii=False)}\n\n"

    except Exception as e:
        logger.error(f"Stream generation error: {e}", exc_info=True)
        error_data = {'type': 'error', 'message': str(e)}
        yield f"data: {json.dumps(error_data, ensure_ascii=False)}\n\n"
