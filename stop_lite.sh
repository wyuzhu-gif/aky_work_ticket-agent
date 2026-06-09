#!/bin/bash
# ============================================================
# 作业票智能审查系统 - 停止脚本
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PID_FILE="$SCRIPT_DIR/.pid"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo_info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
echo_warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
echo_error() { echo -e "${RED}[ERROR]${NC} $1"; }

if [ ! -f "$PID_FILE" ]; then
    echo_warn "未找到 PID 文件，服务可能未在运行"
    exit 0
fi

PID=$(cat "$PID_FILE")

if ! kill -0 "$PID" 2>/dev/null; then
    echo_warn "进程 $PID 已不存在"
    rm -f "$PID_FILE"
    exit 0
fi

echo_info "正在停止服务 (PID: $PID)..."
kill "$PID"

# 等待进程结束
for i in $(seq 1 10); do
    if ! kill -0 "$PID" 2>/dev/null; then
        echo_info "服务已停止"
        rm -f "$PID_FILE"
        exit 0
    fi
    sleep 1
done

# 强制结束
echo_warn "进程未正常退出，强制终止..."
kill -9 "$PID" 2>/dev/null
rm -f "$PID_FILE"
echo_info "服务已强制停止"
