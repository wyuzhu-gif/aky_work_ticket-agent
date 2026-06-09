#!/bin/bash
# ============================================================
# 作业票智能审查系统 - 数据备份脚本
# 备份 SQLite (配置/审核记录) + PostgreSQL (作业票数据)
# ============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
API_DIR="$SCRIPT_DIR/../api"
BACKUP_DIR="$SCRIPT_DIR/../backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

mkdir -p "$BACKUP_DIR"

echo "============================================"
echo "  数据备份  ($TIMESTAMP)"
echo "============================================"

# ---------- 1. SQLite ----------
SQLITE_DB="$API_DIR/app/data/app.db"
if [ -f "$SQLITE_DB" ]; then
    SQLITE_BAK="$BACKUP_DIR/app_${TIMESTAMP}.db"
    cp "$SQLITE_DB" "$SQLITE_BAK"
    echo "[INFO] SQLite -> $SQLITE_BAK  ($(stat -c %s "$SQLITE_BAK") bytes)"
else
    echo "[WARN] SQLite 不存在: $SQLITE_DB"
fi

# ---------- 2. PostgreSQL ----------
# 从 .env 读 PG 连接
ENV_FILE="$API_DIR/.env"
if [ ! -f "$ENV_FILE" ]; then
    echo "[ERROR] 找不到 .env: $ENV_FILE"
    exit 1
fi

# 解析 .env
PG_HOST=$(grep '^PG_HOST=' "$ENV_FILE" | cut -d= -f2)
PG_PORT=$(grep '^PG_PORT=' "$ENV_FILE" | cut -d= -f2)
PG_DB=$(grep '^PG_DATABASE=' "$ENV_FILE" | cut -d= -f2)
PG_USER=$(grep '^PG_USER=' "$ENV_FILE" | cut -d= -f2)
PG_PASS=$(grep '^PG_PASSWORD=' "$ENV_FILE" | cut -d= -f2)

if [ -z "$PG_HOST" ] || [ -z "$PG_DB" ]; then
    echo "[ERROR] .env 中 PG 配置缺失"
    exit 1
fi

PG_BAK="$BACKUP_DIR/pg_${TIMESTAMP}.sql"

if command -v pg_dump >/dev/null 2>&1; then
    PGPASSWORD="$PG_PASS" pg_dump -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" -d "$PG_DB" -F p > "$PG_BAK"
    echo "[INFO] PostgreSQL -> $PG_BAK  ($(stat -c %s "$PG_BAK") bytes)"
else
    echo "[WARN] pg_dump 未安装, 跳过 PostgreSQL 备份"
    echo "       apt install postgresql-client"
fi

# ---------- 3. Milvus (可选, 实际连的是容器, 跳过) ----------
echo "[INFO] Milvus 数据在容器里, 本脚本不备份 (建议 docker volume 备份)"

# ---------- 4. 清理老备份 (保留 30 天) ----------
echo "[INFO] 清理 30 天前的备份..."
find "$BACKUP_DIR" -type f -mtime +30 -name "*.db" -delete
find "$BACKUP_DIR" -type f -mtime +30 -name "*.sql" -delete

echo "============================================"
echo "  备份完成!"
echo "  位置: $BACKUP_DIR"
echo "============================================"
ls -lh "$BACKUP_DIR" | tail -10
