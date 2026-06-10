# 作业票智能审查系统 - 部署操作手册

## 一、系统概述

### 三大功能

1. **作业票审查** - 动火/受限空间/盲板抽堵作业票的 AI 智能审核(8 维度,GB 30871-2022)
2. **智能问数** - 自然语言查询数据库,自动生成 SQL 并返回结果
3. **智能体配置** - 运行时热修改 LLM 模型、数据库连接、训练数据

### 系统架构

```
                                    ┌──────────────┐
                                    │ PostgreSQL   │ (客户环境,作业票数据)
                                    │ 10.8.0.100   │
                                    └──────────────┘
                                          ▲
                                          │
   ┌──────────────────────────────────────┴─────────────────────────────────────┐
   │   应用服务器 (本机)                                                          │
   │                                                                            │
   │   浏览器 ──→ FastAPI :5100 ──→ SQLite (配置/审核记录)                       │
   │                  │       │                                                  │
   │                  │       └──→ LLM (vLLM/Ollama/通义千问)                   │
   │                  │       │      ↑                                           │
   │                  │       │      └──→ LLM_PROVIDER 切换 .env                  │
   │                  │       │                                                  │
   │                  │       ├──→ MinerU (本地 Docker 或云端) PDF 解析          │
   │                  │       │                                                  │
   │                  │       ├──→ 智能问数 RAG (Milvus 容器)                     │
   │                  │       │      ↑                                           │
   │                  │       │      └──→ Jina Embedding                          │
   │                  │       │                                                  │
   │                  │       └──→ 作业票审查 RAG (Wiki 知识库, Markdown)         │
   │                  │                                                          │
   │                  └──→ 静态前端 (api/www/)                                   │
   └────────────────────────────────────────────────────────────────────────────┘
                                          ▲
                                          │ SSH 隧道 (OpenVPN 防火墙)
                                          │ ssh -L 5100:127.0.0.1:5100 czys@<server>
                                          │
                                       浏览器
```

### 外部依赖

| 服务 | 用途 | 是否必须 | 部署方式 |
|------|------|----------|----------|
| PostgreSQL | 作业票数据存储 | **必须** | 客户已有或新部署 |
| LLM | AI 审核 + 智能问数 | **必须** | vLLM / Ollama / 云端 API |
| MinerU | PDF 解析 | 可选 | 本地 Docker 或云端 API |
| Milvus | 智能问数 RAG 向量检索 | 可选 | Docker 容器,无则智能问数降级 |
| Jina Embedding | 文本向量化(配 Milvus) | 可选 | 本地 HTTP 或云端 API |
| Wiki 知识库 | 作业票审查法规依据 | 可选 | 内置 Markdown |

**按功能降级策略**:

- **作业票审查**:必须有 LLM + PostgreSQL。MinerU 缺则不能上传 PDF(可手动填写)
- **智能问数**:必须有 LLM + PostgreSQL。Milvus 缺则降级为直连 PG(没有 RAG 参考)
- **智能体配置**:无外部依赖

---

## 二、环境要求

- **OS**: Linux (Ubuntu 20.04+) / macOS
- **Python**: 3.10+
- **内存**: 最低 4 GB,推荐 8 GB+
- **磁盘**: 最低 2 GB(不含数据库)
- **GPU** (本地 LLM 必需): NVIDIA,显存 ≥ 24 GB(本项目跑 Qwen3.6-27B 用 87 GB)

验证:
```bash
python3 --version    # 3.10+
nvidia-smi           # GPU (本地 LLM 时)
```

---

## 三、目录结构

```
ticket-review-lite/                      # 本项目
├── api/                  # FastAPI 后端
│   ├── main.py           # 入口
│   ├── .env.template     # 配置模板
│   ├── .env              # 实际配置 (从模板复制)
│   ├── requirements.txt  # Python 依赖
│   ├── www/              # 前端静态文件
│   ├── routers/          # 9 个 API 路由
│   ├── services/         # 12 个业务服务
│   ├── smart_query/      # 智能问数模块 (27 个 .py)
│   ├── database/         # PG 访问 + init.sql
│   ├── prompts/          # LLM 提示词 (9 个)
│   ├── config/           # 配置模块
│   ├── middleware/       # 中间件
│   ├── security/         # AAD 认证
│   ├── app/data/         # SQLite + 上传文件
│   ├── tests/            # 单元测试
│   └── venv/             # Python 虚拟环境
├── common/               # 公共模块 (logger, models, llm_utils, permit_models)
├── wiki/                 # 法规知识库 (Markdown + 向量索引)
├── scripts/              # 运维脚本
│   ├── build.sh          # 前端构建
│   ├── backup.sh         # 数据备份
│   ├── check.sh          # 健康检查
│   ├── test_smart_query.sh    # 智能问数 CLI 测试
│   ├── test_permit_review.sh  # PDF 审查 CLI 测试
│   └── rag_train_cli.py       # RAG 训练 CLI
├── start_lite.sh         # 启动后端
├── stop_lite.sh          # 停止后端
├── compile_py.sh         # Cython 源码保护 (可选)
├── DEPLOY.md             # 本文件
├── README.md             # 项目介绍
├── LICENSE               # MIT
├── CHANGELOG.md          # 变更记录
└── .gitignore

/home/czys/workspace/                    # 工作区根 (外部服务)
├── start-all.sh          # 启动所有外部服务
├── stop-all.sh           # 停止所有外部服务
├── milvus/               # Milvus 向量数据库
├── mineru/               # MinerU PDF 解析
├── jina-embedding/       # 文本向量化
├── logs/                 # 外部服务日志
└── ... 其他服务
```

---

## 四、部署步骤

### 4.1 上传部署包

```bash
scp ticket-review-lite.tar.gz user@<server>:/opt/
# 或在服务器上: rz ticket-review-lite.tar.gz
```

### 4.2 解压

```bash
cd /opt
tar xzf ticket-review-lite.tar.gz
cd ticket-review-lite
```

### 4.3 配置 .env

```bash
cd api
cp .env.template .env
vi .env
```

**必填项**(参考 `api/database/init.sql` 准备 PG):

```bash
# ---- 1. LLM (必填, 三选一) ----

# 方式 A: 阿里云通义千问 (开箱即用,推荐)
LLM_API_KEY=sk-xxx
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_MODEL=qwen3.5-flash
LLM_VISION_MODEL=qwen-vl-plus

# 方式 B: 本地 vLLM (推荐 27B+,需本地 GPU)
LLM_API_KEY=
LLM_BASE_URL=http://localhost:8001/v1
LLM_MODEL=Qwen3.6-27B

# 方式 C: 本地 Ollama (轻量模型,笔记本也能跑)
LLM_PROVIDER=ollama
LLM_API_KEY=
LLM_BASE_URL=http://localhost:11434/v1
LLM_MODEL=glm-4.7-flash-nothink:latest

# ---- 2. PostgreSQL (必填) ----
PG_HOST=10.8.0.100
PG_PORT=35432
PG_DATABASE=special_operations
PG_USER=postgres
PG_PASSWORD=your_password
```

**可选项**(按需):

```bash
# MinerU (PDF 上传时需要)
MINERU_LOCAL_URL=http://localhost:30000
# 或云端:
# MINERU_BASE_URL=https://mineru.net
# MINERU_API_KEY=eyJ0eX...

# 智能问数 RAG (Milvus + Embedding)
SQ_LLM_MODEL=glm-4.7-flash-nothink:latest
SQ_EMBEDDING_PROVIDER=jina
SQ_EMBEDDING_API_URL=http://localhost:38898/v1/embeddings
SQ_MILVUS_URI=http://localhost:39530
```

### 4.4 初始化数据库

```bash
# 第一次部署需要建表
psql -h <PG_HOST> -p <PG_PORT> -U <PG_USER> -d <PG_DATABASE> -f api/database/init.sql

# 验证: 应能列出 7 张表
psql -h <PG_HOST> -p <PG_PORT> -U <PG_USER> -d <PG_DATABASE> -c "\dt"
# hot_work_permits / confined_space_permits / permit_blind_plate / ...
```

### 4.5 启动外部服务(本机 Docker)

```bash
cd /home/czys/workspace
bash start-all.sh    # 启 vLLM + Milvus + MinerU + Jina
```

如果外部服务**已通过其他方式启动**,跳过此步。

### 4.6 启动 5100 后端

```bash
cd /opt/ticket-review-lite
bash start_lite.sh
```

启动成功后:
```
[INFO] 启动成功!
  访问地址: http://<server>:5100
  停止服务: ./stop_lite.sh
  查看日志: tail -f app.log
```

**注意**: `start_lite.sh` 默认 `--workers 2`,可通过环境变量 `UVICORN_WORKERS=N` 修改。

### 4.7 健康检查

```bash
cd /opt/ticket-review-lite
bash scripts/check.sh
```

应输出所有依赖服务都 ✓。

### 4.8 验证前端

浏览器打开 `http://<server>:5100`,左侧导航:
- 作业票审查
- 数据分析 → 智能问数
- 系统管理 → 智能体配置

---

## 五、智能体配置(运行时热修改)

"系统管理 → 智能体配置" 页面支持**无需重启**修改:

- LLM API Key / Base URL / 模型名
- 数据库连接信息
- 智能问数训练数据 (增删改 DDL/Doc/SQL)

**优先级**: SQLite 配置 > .env 文件

---

## 六、运维操作

### 启停

```bash
# 后端
bash start_lite.sh
bash stop_lite.sh

# 外部服务 (vLLM/Milvus/MinerU/Jina)
bash /home/czys/workspace/start-all.sh
bash /home/czys/workspace/stop-all.sh
```

### 监听端口

默认 5100,修改 `start_lite.sh` 的 `PORT=5100`。

### 数据备份

```bash
# 一键备份 (SQLite + PG)
bash scripts/backup.sh
# 输出到: ticket-review-lite/backups/
# 保留 30 天
```

### 更新前端

```bash
# 开发机: 构建
bash scripts/build.sh

# 部署机: 替换 www/
# (在开发机上跑,产物已就位,直接重启 5100)
bash stop_lite.sh
bash start_lite.sh
```

### 更新后端

替换 `api/` 代码后重启:
```bash
bash stop_lite.sh
bash start_lite.sh
```

---

## 七、故障排查

### 服务启动失败

```bash
# 查看日志
tail -100 app.log

# 依赖缺失
cd api
rm -rf venv
python3 -m venv venv
./venv/bin/pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### 5100 启来但前端无数据

检查 PG 连接:
```bash
psql -h <PG_HOST> -p <PG_PORT> -U <PG_USER> -d <PG_DATABASE> -c "SELECT count(*) FROM hot_work_permits;"
```

### 智能问数报"未找到相关信息"

1. 检查 LLM 配置 (`.env` 或 SQLite 热配)
2. 检查 Milvus: `curl http://<MILVUS_URI>/health`
3. 检查 Jina Embedding: `curl http://<JINA_URL>/v1/embeddings -d '{"input":["test"]}'`
4. 看 `app.log` 找具体错误

### 智能问数报 `tool_choice="auto" 400`

vLLM 启动参数没加 `--enable-auto-tool-choice --tool-call-parser=qwen3_xml`。
`start_lite.sh` 不启 vLLM,需手动修 `start-all.sh` 里的 vLLM 启动参数。

### PDF 审查报 "404 Not Found" /file_parse

MinerU 服务没启,或 `MINERU_LOCAL_URL` 配错。

### 端口占用

```bash
lsof -i :5100
kill <PID>
```

---

## 八、双 RAG 体系说明

本项目**故意**保留两套 RAG 检索:

| 体系 | 存储 | 服务 | 用途 |
|------|------|------|------|
| **Milvus 向量库** | Milvus Lite + 向量 | `smart_query/` (智能问数) | 检索 DDL/文档/SQL 训练数据,帮 LLM 生成更准的 SQL |
| **Wiki 知识库** | Markdown 文件 + sqlite 索引 | `services/wiki_search.py` (作业票审查) | 检索 GB 30871 法规条款,帮 LLM 引用具体条款编号 |

**不合并原因**: 两套体系服务的业务不同,数据格式和检索策略都不一样。Milvus 适合结构化的 DDL/SQL 样本,Wiki 适合长文本的法规条款。

---

## 九、配置项完整参考

| 环境变量 | 默认 | 说明 | 必填 |
|----------|------|------|------|
| DEBUG | False | 调试模式 | 否 |
| SERVE_STATIC | True | 是否托管前端静态文件 | 否 |
| LOG_LEVEL | INFO | 日志级别 | 否 |
| LLM_PROVIDER | vllm | vllm/ollama/dashscope | 否 |
| LLM_API_KEY | - | LLM Key | 是(本地可空) |
| LLM_BASE_URL | dashscope | LLM 地址 | 是 |
| LLM_MODEL | qwen3.5-flash | LLM 模型名 | 是 |
| LLM_VISION_MODEL | qwen-vl-plus | 视觉模型 | 否 |
| PG_HOST | localhost | PG 地址 | 是 |
| PG_PORT | 5432 | PG 端口 | 是 |
| PG_DATABASE | special_operations | 数据库名 | 是 |
| PG_USER | postgres | 用户名 | 是 |
| PG_PASSWORD | - | 密码 | 是 |
| MINERU_LOCAL_URL | - | 本地 MinerU | 否 |
| MINERU_BASE_URL | mineru.net | 云端 MinerU | 否 |
| MINERU_API_KEY | - | MinerU Key | 否 |
| SQ_LLM_MODEL | qwen3.6:35b | 智能问数 LLM (本地 ollama, 内网部署避免云端) | 否 |
| SQ_EMBEDDING_PROVIDER | jina | Embedding 提供商 | 否 |
| SQ_EMBEDDING_API_URL | - | Embedding 地址 | 否 |
| SQ_MILVUS_URI | - | Milvus 地址 | 否 |
| SQ_MILVUS_METRIC_TYPE | COSINE | 距离度量 (COSINE/L2) | 否 |

---

## 十、测试

### 单元测试

```bash
cd api
./venv/bin/python -m pytest tests/ -v
```

### CLI 集成测试

```bash
# 智能问数
bash scripts/test_smart_query.sh "数据库里有多少张动火作业票"

# PDF 审查
bash scripts/test_permit_review.sh /path/to/permit.pdf
```

### RAG 训练

```bash
# 列出已有训练数据
./scripts/rag_train_cli.py --list --list-type sql

# 训练新 SQL 模板
./scripts/rag_train_cli.py --type sql --text "按月统计作业票数量" --sql "SELECT TO_CHAR(...)"
```
