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

两段式 prompt:
1. SYSTEM_PROMPT (核心规则, 放 system role, 避免 glm-4.7-nothink tool calling 失效)
2. OUTPUT_FORMAT_PROMPT (输出格式, 在第二次 LLM 调用时追加, 引导 chartconfig + 3 段报告)
"""

import re
import json
import time
import logging
from typing import Optional, List, Dict, Any
from decimal import Decimal

logger = logging.getLogger(__name__)


def convert_decimals(obj):
    """将对象中的 Decimal / Timestamp / datetime 类型转换为可 JSON 序列化的值"""
    from datetime import datetime, date
    from decimal import Decimal
    if isinstance(obj, dict):
        return {k: convert_decimals(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_decimals(item) for item in obj]
    elif isinstance(obj, Decimal):
        return float(obj)
    elif isinstance(obj, (datetime, date)):
        return obj.isoformat()  # ISO 8601 字符串
    else:
        return obj


def generate_chat_stream(
    agent,
    question: str,
    session_id: str,
    messages_payload: list,
    enable_training: bool = False,
    vanna_client=None,
    recursion_limit: int = 150,
):
    """
    生成器：执行 Agent 并以 SSE 格式推送结果 (FastAPI sync def, 自动用 thread pool)

    之前是 async def, 内部用 to_thread 包 sync agent.stream, 客户端看不到中间 event
    现在改 sync def: FastAPI 自动把 sync generator 放到 thread pool, 不阻塞 event loop
    sync agent.stream yield 一次, 我们就 yield 一次给 SSE, 客户端实时看到进度

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
    consecutive_sql_failures = 0
    consecutive_execute_sql = 0  # 新增: 连续 execute_sql 次数 (避免 LLM 拿到数据后继续查询)
    MAX_CONSECUTIVE_EMPTY = 3
    MAX_CONSECUTIVE_SQL_FAILURES = 3  # 连续 3 次 SQL 失败就停 (避免 LLM 死循环拼错 SQL)
    MAX_CONSECUTIVE_EXECUTE_SQL = 2  # 连续 2 次 execute_sql 就停 (避免 LLM 拿到数据后继续查询)
    MAX_TOTAL_STEPS = 15  # 新增: 总步骤数硬上限 (超过强制跳出 stream 进入 report gen)

    try:
        cfg = {
            "configurable": {"thread_id": f"session-{session_id}"},
            "recursion_limit": recursion_limit,
        }

        final_event = None
        last_tool = None

        # 第一阶段:实时推送 Agent 执行步骤
        # sync def + sync agent.stream, FastAPI 自动 thread pool, 不阻塞 event loop
        # sync stream yield 一次就推一次给 SSE, 客户端实时看到进度
        total_steps = 0  # 总步骤数
        force_stop = False  # 强制跳出 stream 标志
        for event in agent.stream(
            {"messages": messages_payload},
            stream_mode="values",
            config=cfg,
        ):
            if force_stop:
                break
            final_event = event
            messages = event.get("messages", [])
            total_steps += 1

            # 总步骤数硬上限 (避免 LLM 30+ 步死循环)
            if total_steps > MAX_TOTAL_STEPS:
                logger.warning(f"[Loop Guard] Total steps ({total_steps}) exceeded MAX_TOTAL_STEPS={MAX_TOTAL_STEPS}, forcing stop")
                # 不报错, 静默跳出, 后面 report gen 会拿已有 query_data
                break

            if messages:
                last_msg = messages[-1]
                msg_type = getattr(last_msg, 'type', 'unknown')

                # 检测工具调用（立即推送工具名）
                if msg_type == 'ai' and hasattr(last_msg, 'tool_calls') and last_msg.tool_calls:
                    for tool_call in last_msg.tool_calls:
                        tool_name = tool_call.get('name', 'unknown')

                        # 连续 execute_sql 计数 (非 execute_sql 工具重置计数)
                        if tool_name == 'execute_sql':
                            consecutive_execute_sql += 1
                            logger.info(f"[Step Counter] consecutive_execute_sql={consecutive_execute_sql}")
                            if consecutive_execute_sql > MAX_CONSECUTIVE_EXECUTE_SQL:
                                logger.warning(f"[Loop Guard] Consecutive execute_sql ({consecutive_execute_sql}) > MAX={MAX_CONSECUTIVE_EXECUTE_SQL}, forcing stop (LLM got data but kept querying)")
                                # 静默跳出, 后面 report gen 会拿已有 query_data
                                force_stop = True
                                break
                        else:
                            consecutive_execute_sql = 0  # 调其他工具时重置

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
                    elif last_tool == 'execute_sql' and 'SQL执行失败' in tool_content:
                        # 新增: 检测 SQL 连续失败 (避免 LLM 死循环拼错 SQL)
                        consecutive_sql_failures += 1
                        logger.warning(f"[Loop Guard] Consecutive SQL failures: {consecutive_sql_failures}")
                        if consecutive_sql_failures >= MAX_CONSECUTIVE_SQL_FAILURES:
                            logger.error(f"[Loop Guard] Agent stuck in SQL-failure loop ({consecutive_sql_failures}x), forcing stop")
                            error_data = {
                                'type': 'error',
                                'message': f'智能查询连续{consecutive_sql_failures}次SQL执行失败，已自动终止。SQL可能存在语法错误或表名/列名拼写错误，请换一种问法。'
                            }
                            yield f"data: {json.dumps(error_data, ensure_ascii=False)}\n\n"
                            break
                    elif last_tool == 'execute_sql' and '查询成功' in tool_content:
                        consecutive_empty_results = 0  # 重置计数
                        consecutive_sql_failures = 0  # 重置计数
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
            # ⚠️ 跟 get_last_query_result() 配对: 取**最后一个** execute_sql tool_call 的 SQL
            #    (避免 SQL 跟 df 不匹配 — 之前正序遍历取的是对话里最早那个, df 是最后那个)
            for msg in reversed(messages):
                if getattr(msg, 'type', '') == 'ai' and hasattr(msg, 'tool_calls') and msg.tool_calls:
                    for tool_call in reversed(msg.tool_calls):
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

                # 🔔 过渡提示: execute_sql 出结果后, 到报告生成前, 推送 info 事件
                #    前端可拿来弹 toast / 顶部条幅. 5-15 秒等待里给用户明确反馈.
                info_event = {
                    'type': 'info',
                    'level': 'info',
                    'message': f'✅ 已获取 {len(query_data)} 行查询数据, 正在生成分析报告 (5-15 秒)',
                    'icon': '⏳',
                }
                yield f"data: {json.dumps(info_event, ensure_ascii=False)}\n\n"

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

            if answer or query_data:
                # 两段式 prompt: 当有真实查询数据时, 调第二次 LLM 用 OUTPUT_FORMAT_PROMPT 生成 chartconfig + 3 段报告
                # 避免在 system prompt 里塞 1328 字符输出格式导致 glm-4.7-nothink tool calling 失效
                if query_data and final_event:
                    try:
                        from .config import OUTPUT_FORMAT_PROMPT
                        from langchain_core.messages import SystemMessage, HumanMessage
                        from common.llm_utils import build_llm

                        # 推 step: 开始生成报告
                        # ⏳ 用户感知: execute_sql 数据已就绪 -> 进入报告生成阶段
                        #    此步骤会调第二次 LLM (5-15 秒), 必须给前端明确的"正在生成"状态, 避免用户以为卡死
                        step_data = {
                            'type': 'step',
                            'action': '⏳ 分析结果生成中, 请稍候...',
                            'tool_name': 'generate_report',
                            'status': 'running',
                            'description': '已获取查询数据, 正在生成数据分析报告 + 可视化图表, 预计 5-15 秒',
                        }
                        yield f"data: {json.dumps(step_data, ensure_ascii=False)}\n\n"

                        # 调第二次 LLM: system + history (filtered) + OUTPUT_FORMAT_PROMPT
                        # 用 build_llm 直接调 (不走 agent, 不需要 tools, 只要 content)
                        report_llm = build_llm(max_tokens=2000)  # 报告可能长, 加大

                        # 准备 messages: 系统 + 简化历史 + 输出格式 prompt
                        report_messages = [
                            SystemMessage(content="你是数据分析员, 负责根据 SQL 查询结果生成专业报告。"),
                            HumanMessage(content=(
                                f"用户问题: {question}\n\n"
                                f"SQL 查询结果 ({len(query_data)} 行):\n"
                                f"{json.dumps(query_data, ensure_ascii=False, default=str)[:2000]}\n\n"
                                f"SQL 语句: {sql_query or 'N/A'}\n\n"
                                f"{OUTPUT_FORMAT_PROMPT}\n\n"
                                f"**重要提醒**: 以上查询结果是真实数据, 请严格基于这些数据写报告, "
                                f"禁止编造数据, 禁止假设, 禁止使用'估计/大约'等模糊措辞。"
                            )),
                        ]

                        logger.info(f"[Report Gen] Calling LLM with OUTPUT_FORMAT_PROMPT ({len(OUTPUT_FORMAT_PROMPT)} chars)")
                        t0 = time.time()
                        report_resp = report_llm.invoke(report_messages)
                        logger.info(f"[Report Gen] LLM response in {time.time()-t0:.1f}s, content_len={len(report_resp.content)}")
                        answer = report_resp.content
                    except Exception as e:
                        logger.error(f"[Report Gen] Failed, fallback to original answer: {e}")
                        # fallback: 用 agent 自己的 answer
                        if not answer:
                            for msg in reversed(messages):
                                if getattr(msg, 'type', '') == 'ai':
                                    content = getattr(msg, 'content', '').strip()
                                    if content and len(content) > 0:
                                        answer = content
                                        break

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

                # 推 step: 报告生成完成
                step_data = {
                    'type': 'step',
                    'action': '✅ 分析报告生成完成',
                    'tool_name': 'generate_report',
                    'status': 'completed',
                    'update': True,  # ⚠️ 跟前面的 running 配对, 前端 findLastIndex 找同 tool_name 更新状态
                }
                yield f"data: {json.dumps(step_data, ensure_ascii=False)}\n\n"

                # 流式推送答案（逐字符）
                for char in answer:
                    chunk_data = {
                        'type': 'answer',
                        'content': char,
                        'done': False
                    }
                    yield f"data: {json.dumps(chunk_data, ensure_ascii=False)}\n\n"
                    import time as _t; _t.sleep(0.02)  # sync delay (simulate typing)

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
