#!/bin/bash
# ============================================================
# 作业票智能审查系统 - 启动脚本
# ============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
API_DIR="$SCRIPT_DIR/api"
VENV_DIR="$API_DIR/venv"
ENV_FILE="$API_DIR/.env"
PID_FILE="$SCRIPT_DIR/.pid"
LOG_FILE="$SCRIPT_DIR/app.log"
PORT=5100

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo_info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
echo_warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
echo_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# ---------- 1. 检查 .env ----------
if [ ! -f "$ENV_FILE" ]; then
    echo_error "配置文件 .env 不存在！"
    echo_info "请先复制模板并修改配置："
    echo "  cd $API_DIR"
    echo "  cp .env.template .env"
    echo "  vi .env"
    exit 1
fi

# ---------- 2. 检查 Python 虚拟环境 ----------
if [ ! -d "$VENV_DIR" ]; then
    echo_info "正在创建 Python 虚拟环境..."
    python3 -m venv "$VENV_DIR"
    echo_info "正在安装依赖包（首次运行较慢）..."
    "$VENV_DIR/bin/pip" install -r "$API_DIR/requirements.txt" -i https://pypi.tuna.tsinghua.edu.cn/simple
fi

# ---------- 3. 检查是否已在运行 ----------
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE")
    if kill -0 "$OLD_PID" 2>/dev/null; then
        echo_warn "服务已在运行 (PID: $OLD_PID)"
        echo "  如需重启，请先执行: ./stop_lite.sh"
        exit 0
    else
        rm -f "$PID_FILE"
    fi
fi

# ---------- 4. 检查端口占用 ----------
if lsof -i :$PORT -sTCP:LISTEN >/dev/null 2>&1; then
    echo_error "端口 $PORT 已被占用！"
    echo "  占用进程："
    lsof -i :$PORT -sTCP:LISTEN
    echo "  请修改端口或停止占用进程"
    exit 1
fi

# ---------- 5. 创建必要目录 ----------
mkdir -p "$API_DIR/app/data/documents"
mkdir -p "$API_DIR/app/data/mineru"
mkdir -p "$API_DIR/app/data/rule_docs"

# ---------- 6. 启动服务 ----------
echo_info "正在启动作业票智能审查系统..."
echo_info "监听端口: $PORT"
echo_info "日志文件: $LOG_FILE"

cd "$API_DIR"

# 加载环境变量并启动
set -a
source "$ENV_FILE"
set +a

nohup "$VENV_DIR/bin/uvicorn" main:app \
    --host 0.0.0.0 \
    --port $PORT \
    --workers 2 \
    --log-level info \
    >> "$LOG_FILE" 2>&1 &

SERVER_PID=$!
echo "$SERVER_PID" > "$PID_FILE"

# 等待启动
sleep 3
if kill -0 "$SERVER_PID" 2>/dev/null; then
    echo_info "启动成功！"
    echo ""
    echo "  访问地址: http://<服务器IP>:$PORT"
    echo "  停止服务: ./stop_lite.sh"
    echo "  查看日志: tail -f $LOG_FILE"
else
    echo_error "启动失败！请检查日志："
    tail -20 "$LOG_FILE"
    rm -f "$PID_FILE"
    exit 1
fi
