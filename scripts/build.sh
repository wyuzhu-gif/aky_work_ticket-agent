#!/bin/bash
# ============================================================
# 作业票智能审查系统 - 前端构建脚本
# 在开发机上跑,把前端编译产物复制到部署服务器的 api/www/
# ============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
API_DIR="$SCRIPT_DIR/../api"
UI_SRC="$API_DIR/../app/ui-lite"  # 前端源码 (开发机)
UI_OUT="$API_DIR/www"             # 前端输出 (部署目标)

if [ ! -d "$UI_SRC" ]; then
    echo "[ERROR] 找不到前端源码: $UI_SRC"
    echo "请确认前端项目路径 (默认在 app/ui-lite)"
    exit 1
fi

echo "============================================"
echo "  构建前端"
echo "============================================"

cd "$UI_SRC"
echo "[INFO] 安装依赖..."
npm install

echo "[INFO] 构建..."
npm run build

if [ -d "$UI_OUT" ]; then
    echo "[INFO] 清理旧版本 www/..."
    rm -rf "$UI_OUT"/* 2>/dev/null || true
fi

echo "[INFO] 复制构建产物到 $UI_OUT ..."
mkdir -p "$UI_OUT"
cp -r dist/* "$UI_OUT/" 2>/dev/null || cp -r build/* "$UI_OUT/"

echo "============================================"
echo "  完成! 部署包: $UI_OUT"
echo "============================================"
ls -la "$UI_OUT"
