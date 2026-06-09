#!/bin/bash
# ============================================================================
# 智能问数测试脚本
# 绕过浏览器前端,直接通过 API 端到端测试 smart_query 流程
#   - 模拟前端登录/对话
#   - 调 ollama LLM (vLLM 也行)
#   - 走 LangChain agent + tool calling
#   - 返回 NL2SQL 结果
# ============================================================================
# 用法:
#   bash test_smart_query.sh "今天有几张动火作业票?"
#   bash test_smart_query.sh "统计昨天的作业票" vllm
# ============================================================================

set -e

QUESTION="${1:-今天有几张动火作业票?}"
LLM_PROVIDER="${2:-$(grep ^LLM_PROVIDER= /home/czys/workspace/ticket-review-lite/api/.env 2>/dev/null | cut -d= -f2)}"
LLM_PROVIDER="${LLM_PROVIDER:-vllm}"

# 颜色
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo "=================================================================="
echo "  智能问数测试"
echo "  问题: $QUESTION"
echo "  LLM Provider: $LLM_PROVIDER"
echo "=================================================================="
echo ""

# 1. health check
echo -e "${YELLOW}[1/4] 5100 健康检查${NC}"
HEALTH=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 http://127.0.0.1:5100/api/health)
if [ "$HEALTH" != "204" ]; then
    echo -e "${RED}  ✗ 5100 不可达 (HTTP $HEALTH)${NC}"
    exit 1
fi
echo -e "${GREEN}  ✓ 5100 健康${NC}"
echo ""

# 2. 创建会话
echo -e "${YELLOW}[2/4] 创建会话${NC}"
SESSION_RESP=$(curl -s -X POST http://127.0.0.1:5100/api/v1/chat/sessions \
    -H "Content-Type: application/json" \
    -d '{"title":"CLI测试"}' 2>&1)
SESSION_ID=$(echo "$SESSION_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('data',{}).get('id','') or d.get('session_id','') or d.get('id',''))" 2>&1)
if [ -z "$SESSION_ID" ]; then
    echo -e "${RED}  ✗ 创建会话失败: $SESSION_RESP${NC}"
    exit 1
fi
echo -e "${GREEN}  ✓ 会话 ID: $SESSION_ID${NC}"
echo ""

# 3. 流式提问(智能问数, NL2SQL)
echo -e "${YELLOW}[3/4] 发送问题(流式响应)${NC}"
echo "  URL: http://127.0.0.1:5100/api/v1/chat/stream"
echo "  Session: $SESSION_ID"
echo "  ----------------------------------------------------------------"

START=$(date +%s)
RAW_LOG=/tmp/smart_query_resp_$$.log
# ChatRequest 用 question 字段, 不是 message
PAYLOAD=$(python3 -c "import json; print(json.dumps({'session_id':'$SESSION_ID','question':'$QUESTION','stream':True}))")
curl -s -N --max-time 900 -X POST "http://127.0.0.1:5100/api/v1/chat/stream" \
    -H "Content-Type: application/json" \
    -d "$PAYLOAD" \
    2>&1 | tee "$RAW_LOG"
END=$(date +%s)
ELAPSED=$((END - START))
echo ""
echo "  ----------------------------------------------------------------"
echo -e "${GREEN}  ✓ 完成, 耗时 ${ELAPSED} 秒${NC}"
echo ""

# 4. 解析响应(提取 LLM 输出和 SQL)
echo -e "${YELLOW}[4/4] 解析响应${NC}"
python3 <<PYEOF
import re, json
with open("$RAW_LOG") as f:
    raw = f.read()

# 流式响应是 SSE 格式: data: {...}\n\n
# 提取所有 data: 行
events = []
for line in raw.split('\n'):
    line = line.strip()
    if line.startswith('data: '):
        try:
            events.append(json.loads(line[6:]))
        except Exception:
            pass

# 提取所有 event
all_event_types = {}
full_content = ""
tool_calls = []
sql_executed = None
sql_result = None

for ev in events:
    # 累加 type
    t = ev.get('type', 'unknown')
    all_event_types[t] = all_event_types.get(t, 0) + 1
    # 累加 content
    if 'content' in ev and ev['content']:
        full_content += ev['content']
    # 累加 tool_calls
    if 'tool_calls' in ev and ev['tool_calls']:
        tool_calls.extend(ev['tool_calls'])
    # SQL
    if ev.get('type') == 'sql_executed' or 'sql' in ev:
        sql_executed = ev.get('sql') or ev.get('query')
    if ev.get('type') == 'sql_result' or 'result' in ev:
        sql_result = ev.get('result')

print(f"  事件数: {len(events)}")
print(f"  事件类型分布: {all_event_types}")
print(f"  content 长度: {len(full_content)}")
print(f"  tool_calls 数量: {len(tool_calls)}")
if tool_calls:
    for i, tc in enumerate(tool_calls):
        print(f"    [{i}] name={tc.get('name')} args={tc.get('args')}")
print()
print("=" * 60)
print("最终 LLM 回答:")
print("=" * 60)
print(full_content if full_content else "(空)")
print()
if sql_executed:
    print("=" * 60)
    print("生成的 SQL:")
    print("=" * 60)
    print(sql_executed)
    print()
if sql_result is not None:
    print("=" * 60)
    print("SQL 结果 (前 5 行):")
    print("=" * 60)
    if isinstance(sql_result, list):
        for row in sql_result[:5]:
            print(row)
        if len(sql_result) > 5:
            print(f"... 共 {len(sql_result)} 行")
    else:
        print(sql_result)
PYEOF
echo ""
echo "完整响应已保存到: $RAW_LOG"
echo "=================================================================="
