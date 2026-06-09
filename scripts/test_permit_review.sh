#!/bin/bash
# ============================================================================
# 作业票 PDF 上传 + 提取 + 审查测试脚本
# 端到端测试 PDF → MinerU → ollama LLM → 结构化 JSON
# ============================================================================
# 用法:
#   bash test_permit_review.sh /path/to/permit.pdf
#   bash test_permit_review.sh                # 默认用 /home/czys/workspace/test_data/1.pdf
# ============================================================================

set -e

PDF_PATH="${1:-/home/czys/workspace/test_data/1.pdf}"
PERMIT_TYPE="${2:-hot_work}"  # hot_work / confined_space / blind_plate

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

if [ ! -f "$PDF_PATH" ]; then
    echo -e "${RED}✗ PDF 文件不存在: $PDF_PATH${NC}"
    exit 1
fi

PDF_SIZE=$(du -h "$PDF_PATH" | cut -f1)
echo "=================================================================="
echo "  作业票审查测试"
echo "  PDF: $PDF_PATH ($PDF_SIZE)"
echo "  类型: $PERMIT_TYPE"
echo "=================================================================="
echo ""

# 1. health check
echo -e "${YELLOW}[1/3] 健康检查${NC}"
HEALTH=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 http://127.0.0.1:5100/api/health)
if [ "$HEALTH" != "204" ]; then
    echo -e "${RED}  ✗ 5100 不可达${NC}"
    exit 1
fi
echo -e "${GREEN}  ✓ 5100 健康${NC}"
echo ""

# 2. 上传 + 提取(MinerU + LLM)
echo -e "${YELLOW}[2/3] 上传 PDF + 提取 (这会跑 MinerU 30s + LLM 2-8 分钟)${NC}"
echo "  URL: http://127.0.0.1:5100/api/v1/permits/upload-and-extract"
echo "  等待响应中 (max 15 min)..."
echo "  ----------------------------------------------------------------"

START=$(date +%s)
RESP_FILE=/tmp/permit_extract_resp_$$.json
HTTP_CODE=$(curl -s -o "$RESP_FILE" -w "%{http_code}" --max-time 900 \
    -X POST "http://127.0.0.1:5100/api/v1/permits/upload-and-extract?permit_type=$PERMIT_TYPE" \
    -F "file=@$PDF_PATH")
END=$(date +%s)
ELAPSED=$((END - START))
echo ""
echo "  HTTP: $HTTP_CODE, 耗时: ${ELAPSED}s"
echo ""

# 3. 解析响应
echo -e "${YELLOW}[3/3] 解析响应${NC}"
if [ "$HTTP_CODE" != "200" ]; then
    echo -e "${RED}  ✗ 失败: HTTP $HTTP_CODE${NC}"
    cat "$RESP_FILE"
    exit 1
fi
echo -e "${GREEN}  ✓ 成功${NC}"
echo ""
python3 <<PYEOF
import json
with open("$RESP_FILE") as f:
    d = json.load(f)

print("=" * 60)
print("响应顶层字段:")
print("=" * 60)
for k in d:
    v = d[k]
    if isinstance(v, (list, dict)):
        print(f"  {k}: <{type(v).__name__} with {len(v)} items>")
    else:
        s = str(v)[:80]
        print(f"  {k}: {s!r}")

print()
print("=" * 60)
print("permit (结构化字段):")
print("=" * 60)
permit = d.get('permit', {})
if permit:
    for k, v in permit.items():
        s = str(v)
        if len(s) > 100:
            s = s[:100] + '...'
        print(f"  {k}: {s!r}")
else:
    print("  (空)")
    if 'raw_llm_output' in permit:
        print(f"  raw_llm_output: {permit['raw_llm_output']!r}")

print()
print("=" * 60)
print(f"gas_analyses ({len(d.get('gas_analyses', []))} 条):")
print("=" * 60)
for i, g in enumerate(d.get('gas_analyses', [])[:5]):
    print(f"  [{i}] {g}")
if len(d.get('gas_analyses', [])) > 5:
    print(f"  ... 共 {len(d.get('gas_analyses', []))} 条")

print()
print("=" * 60)
print(f"safety_checks ({len(d.get('safety_checks', []))} 条):")
print("=" * 60)
for i, s in enumerate(d.get('safety_checks', [])[:5]):
    print(f"  [{i}] {s}")
if len(d.get('safety_checks', [])) > 5:
    print(f"  ... 共 {len(d.get('safety_checks', []))} 条")

print()
print("=" * 60)
print(f"raw_md 长度: {len(d.get('raw_md', ''))} 字符")
print("=" * 60)
if d.get('raw_md'):
    print(d['raw_md'][:500] + ('...' if len(d['raw_md']) > 500 else ''))
PYEOF

echo ""
echo "完整响应: $RESP_FILE"
echo "=================================================================="
