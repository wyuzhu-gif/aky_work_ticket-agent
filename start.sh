#!/bin/bash
# ============================================================
# 🚀 AI Document Review - 一键启动脚本 (Linux/Mac)
# ============================================================
# 功能：同时启动后端 API 和前端 UI
# 用法：chmod +x start.sh && ./start.sh
# ============================================================

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
WHITE='\033[1;37m'
NC='\033[0m' # No Color

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo ""
echo -e "${CYAN}╔══════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║        🚀 AI Document Review - 一键启动                  ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════════════════╝${NC}"
echo ""

echo -e "${YELLOW}📁 项目目录: $SCRIPT_DIR${NC}"
echo ""

# ========== 环境检查 ==========
echo -e "${YELLOW}🔍 环境检查...${NC}"

# 检查 Node.js
if command -v node &> /dev/null; then
    NODE_VERSION=$(node --version)
    echo -e "${GREEN}✅ Node.js: $NODE_VERSION${NC}"
else
    echo -e "${RED}❌ Node.js 未安装，请先安装 Node.js${NC}"
    exit 1
fi

# 检查 Python (优先使用较新版本，与 install.sh 保持一致)
if command -v python &> /dev/null; then
    PYTHON_CMD="python"
elif command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
else
    echo -e "${RED}❌ Python 未安装，请先安装 Python${NC}"
    exit 1
fi
PYTHON_VERSION=$($PYTHON_CMD --version)
echo -e "${GREEN}✅ $PYTHON_VERSION${NC}"

echo ""

# 检查环境变量文件
if [ ! -f "app/api/.env" ]; then
    echo -e "${YELLOW}⚠️  未找到 app/api/.env 文件${NC}"
    echo -e "${YELLOW}   请复制 app/api/.env.tpl 并重命名为 .env，然后配置 API Key${NC}"
    echo ""
fi

# ========== 启动后端 ==========
echo -e "${CYAN}🔧 启动后端服务 (FastAPI)...${NC}"

cd app/api

# 激活虚拟环境（如果存在）
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
fi

# 在后台启动后端
$PYTHON_CMD -m uvicorn main:app --host 0.0.0.0 --port 38021 --reload &
BACKEND_PID=$!

echo -e "${GREEN}   ✅ 后端服务已启动 (PID: $BACKEND_PID)${NC}"
echo -e "${WHITE}   📍 API 地址: http://localhost:38021${NC}"
echo -e "${WHITE}   📍 API 文档: http://localhost:38021/docs${NC}"
echo ""

cd "$SCRIPT_DIR"

# 等待后端启动
echo -e "${YELLOW}⏳ 等待后端服务启动 (3秒)...${NC}"
sleep 3

# ========== 启动前端 ==========
echo -e "${CYAN}🎨 启动前端服务 (Vite)...${NC}"

cd app/ui

# 在后台启动前端
PORT=35173 npm run dev &
FRONTEND_PID=$!

echo -e "${GREEN}   ✅ 前端服务已启动 (PID: $FRONTEND_PID)${NC}"
echo -e "${WHITE}   📍 前端地址: http://192.168.16.85:35173${NC}"
echo ""

cd "$SCRIPT_DIR"

# ========== 保存 PID ==========
echo "$BACKEND_PID" > .backend.pid
echo "$FRONTEND_PID" > .frontend.pid

# ========== 完成 ==========
echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}🎉 所有服务已启动！${NC}"
echo ""
echo -e "${YELLOW}📌 服务地址:${NC}"
echo -e "${WHITE}   • 前端 UI:  http://localhost:35173${NC}"
echo -e "${WHITE}   • 后端 API: http://localhost:38021${NC}"
echo -e "${WHITE}   • API 文档: http://localhost:38021/docs${NC}"
echo ""
echo -e "${YELLOW}📌 进程 PID:${NC}"
echo -e "${WHITE}   • 后端: $BACKEND_PID${NC}"
echo -e "${WHITE}   • 前端: $FRONTEND_PID${NC}"
echo ""
echo -e "${YELLOW}📌 停止服务:${NC}"
echo -e "${WHITE}   • 运行 ./stop.sh${NC}"
echo -e "${WHITE}   • 或按 Ctrl+C${NC}"
echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"
echo ""

# 询问是否打开浏览器
read -p "是否打开浏览器？(Y/n): " OPEN_BROWSER
if [ "$OPEN_BROWSER" != "n" ] && [ "$OPEN_BROWSER" != "N" ]; then
    # 跨平台打开浏览器
    if command -v xdg-open &> /dev/null; then
        xdg-open "http://localhost:35173" &
    elif command -v open &> /dev/null; then
        open "http://localhost:35173" &
    fi
fi

echo ""
echo -e "${WHITE}按 Ctrl+C 停止所有服务...${NC}"

# 捕获 Ctrl+C 信号
trap 'echo ""; echo "🛑 正在停止服务..."; kill $BACKEND_PID 2>/dev/null; kill $FRONTEND_PID 2>/dev/null; rm -f .backend.pid .frontend.pid; echo "✅ 服务已停止"; exit 0' SIGINT SIGTERM

# 等待进程
wait

