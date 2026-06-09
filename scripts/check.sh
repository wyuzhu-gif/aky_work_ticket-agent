#!/bin/bash
# ============================================================
# 作业票智能审查系统 - 健康检查脚本
# 检查所有依赖服务 + 5100 后端
# ============================================================

set +e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
API_DIR="$SCRIPT_DIR/../api"
ENV_FILE="$API_DIR/.env"

# 颜色
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

ok()   { echo -e "  ${GREEN}✓${NC} $1"; }
warn() { echo -e "  ${YELLOW}!${NC} $1"; }
fail() { echo -e "  ${RED}✗${NC} $1"; }

echo "============================================"
echo "  健康检查"
echo "============================================"

# ---------- 1. 5100 后端 ----------
echo "[1] 5100 后端"
if curl -s -m 3 -o /dev/null -w "%{http_code}" http://127.0.0.1:5100/api/health | grep -q "204"; then
    ok "5100 /api/health = 204"
else
    fail "5100 /api/health 无响应"
    echo "      启动: bash start_lite.sh"
fi

# ---------- 2. vLLM (LLM) ----------
if [ -f "$ENV_FILE" ]; then
    LLM_URL=$(grep '^LLM_BASE_URL=' "$ENV_FILE" | cut -d= -f2)
    LLM_HOST=$(echo "$LLM_URL" | sed 's|http://||;s|/v1||')
    LLM_PORT=$(echo "$LLM_HOST" | cut -d: -f2)
    LLM_HOST=$(echo "$LLM_HOST" | cut -d: -f1)
    echo "[2] LLM  ($LLM_HOST:$LLM_PORT)"
    if curl -s -m 3 "http://$LLM_HOST:$LLM_PORT/v1/models" >/dev/null 2>&1; then
        MODEL=$(curl -s -m 3 "http://$LLM_HOST:$LLM_PORT/v1/models" | python3 -c "import sys, json; d=json.load(sys.stdin); print(d['data'][0]['id'] if d.get('data') else '?')" 2>/dev/null)
        ok "LLM 在线, model=$MODEL"
    else
        fail "LLM 不在线: http://$LLM_HOST:$LLM_PORT"
    fi
fi

# ---------- 3. PostgreSQL ----------
if [ -f "$ENV_FILE" ]; then
    PG_HOST=$(grep '^PG_HOST=' "$ENV_FILE" | cut -d= -f2)
    PG_PORT=$(grep '^PG_PORT=' "$ENV_FILE" | cut -d= -f2)
    echo "[3] PostgreSQL ($PG_HOST:$PG_PORT)"
    if timeout 3 bash -c "</dev/tcp/$PG_HOST/$PG_PORT" 2>/dev/null; then
        ok "PG 端口可达"
    else
        fail "PG 端口不通: $PG_HOST:$PG_PORT"
    fi
fi

# ---------- 4. Milvus ----------
if [ -f "$ENV_FILE" ]; then
    MILVUS=$(grep '^SQ_MILVUS_URI=' "$ENV_FILE" | cut -d= -f2 | sed 's|http://||')
    echo "[4] Milvus ($MILVUS)"
    if curl -s -m 3 "http://$MILVUS/health" >/dev/null 2>&1; then
        ok "Milvus 在线"
    elif timeout 3 bash -c "</dev/tcp/$(echo $MILVUS | sed 's|:.*||')/$(echo $MILVUS | grep -oP ':\K[0-9]+')" 2>/dev/null; then
        warn "Milvus 端口通, /health 不响应 (可能部署方式不同)"
    else
        fail "Milvus 不可达: $MILVUS"
    fi
fi

# ---------- 5. MinerU ----------
if [ -f "$ENV_FILE" ]; then
    MINERU=$(grep '^MINERU_LOCAL_URL=' "$ENV_FILE" | cut -d= -f2 | sed 's|http://||')
    echo "[5] MinerU ($MINERU)"
    if timeout 3 bash -c "</dev/tcp/$(echo $MINERU | sed 's|:.*||')/$(echo $MINERU | grep -oP ':\K[0-9]+')" 2>/dev/null; then
        ok "MinerU 端口可达"
    else
        warn "MinerU 端口不通 (作业票 PDF 上传会失败, 但智能问数 OK)"
    fi
fi

# ---------- 6. Jina Embedding ----------
if [ -f "$ENV_FILE" ]; then
    JINA=$(grep '^SQ_EMBEDDING_API_URL=' "$ENV_FILE" | cut -d= -f2 | sed 's|http://||;s|/v1.*||')
    echo "[6] Jina Embedding ($JINA)"
    if timeout 3 bash -c "</dev/tcp/$(echo $JINA | sed 's|:.*||')/$(echo $JINA | grep -oP ':\K[0-9]+')" 2>/dev/null; then
        ok "Jina 端口可达"
    else
        warn "Jina 端口不通 (RAG 训练数据会失败, 智能问数降级)"
    fi
fi

# ---------- 7. 总结 ----------
echo ""
echo "============================================"
echo "  完成"
echo "============================================"
