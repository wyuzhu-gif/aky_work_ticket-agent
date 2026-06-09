# 作业票智能审查系统 (ticket-review-lite)

> 基于 LLM + RAG + 双 RAG 体系 的作业票智能审查 + 智能问数系统,符合 GB 30871-2022 危险化学品企业特殊作业安全规范。
>
> **本 README 文档版本**: 2026-06-07 (基于实战部署与 16 个核心问题排查经验整理)

---

## 目录

- [一、项目简介](#一项目简介)
- [二、核心功能](#二核心功能)
- [三、技术栈与外部依赖](#三技术栈与外部依赖)
- [四、完整架构图](#四完整架构图)
- [五、一键启停](#五一键启停)
- [六、API 与路由清单](#六api-与路由清单)
- [七、目录结构](#七目录结构)
- [八、配置项完整参考](#八配置项完整参考)
- [九、关键模块详解](#九关键模块详解)
- [十、遇到的 16 个核心问题与解决方案](#十遇到的-16-个核心问题与解决方案)
- [十一、运维与故障排查](#十一运维与故障排查)
- [十二、文档索引](#十二文档索引)

---

## 一、项目简介

`ticket-review-lite` 是一个**作业票智能审查 + 智能问数一体化平台**,核心目标:

1. **降低 GB 30871-2022 特殊作业规范**的合规审查成本 (人工 → AI 辅助)
2. **让不懂 SQL 的业务人员**用自然语言查作业票数据
3. **运行时热修改** LLM/数据库/训练数据 配置 (无需重启服务)

技术选型:**FastAPI + LangGraph + Milvus + PostgreSQL + Ollama/vLLM + MinerU + Jina Embedding**。

后端 5100 端口,前端 React 编译产物托管在 `api/www/`,部署 1 台 GPU 服务器即可跑通。

---

## 二、核心功能

### 1. 作业票审查 (`/ticket-review`)

**支持的票种**:
- 动火作业 (`hot_work`)
- 受限空间 (`confined_space`)
- 盲板抽堵 (`blind_plate`)

**PDF 上传 → 解析 → LLM 提取 → 8 维度审核**:
1. 解析 (MinerU PDF→markdown)
2. 提取结构化字段 (LLM 按 prompts/*.md 模板)
3. 审核 (LLM 引用 GB 30871 法规 Wiki 知识库)
4. 高亮问题位置 (bbox 渲染)
5. HITL 人工复核 (可选)

**关键提示词**:
- `api/prompts/hot_work_extract.md` / `hot_work_review.md`
- `api/prompts/confined_space_extract.md` / `confined_space_review.md`
- `api/prompts/blind_plate_extract.md` / `blind_plate_review.md`

### 2. 智能问数 (`/smart-query`)

**自然语言 → SQL → 执行 → 报告**:
- 用户在 5100 智能问数页输入"各动火方式作业数量"
- 5 步流程: `get_all_tables_info` → `get_table_schema` (RAG 检索 DDL+SQL模板) → 拼 SQL → `validate_sql_syntax` (PG EXPLAIN 验证) → `execute_sql` (真实执行)
- 第二次 LLM 调: 用 `OUTPUT_FORMAT_PROMPT` 生成 3 段分析报告 + chartconfig
- **RAG 训练数据** (Milvus 容器, 21 条):
  - `vannaddl` (9 条 DDL): 表结构
  - `vannadoc` (2 条文档): 业务说明
  - `vannasql` (10 条 SQL 模板): 历史问答对

### 3. 智能体配置 (`/agent-admin`)

**运行时热修改,无需重启**:
- LLM API Key / Base URL / Model
- PostgreSQL 连接信息
- 智能问数 RAG 训练数据 (DDL / Doc / SQL 增删改查)
- 智能体业务参数

**优先级**: SQLite 热配 > `.env` 文件 > 代码默认值

---

## 三、技术栈与外部依赖

| 组件 | 用途 | 部署方式 | 是否必须 |
|------|------|----------|----------|
| **FastAPI + uvicorn** | 5100 主后端 | `start_lite.sh` | 必须 |
| **PostgreSQL** | 作业票数据 | 客户已有 (本机 10.8.0.100:35432) | 必须 |
| **SQLite** | 配置/审核记录 | 5100 自带 (`api/app/data/app.db`) | 必须 |
| **Ollama** | 本地 LLM 推理 | systemd 服务, 11434 端口 | 必须(三选一) |
| **vLLM** | 本地 LLM 推理 | `start-all.sh` 启动, 8001 端口 | 必须(三选一) |
| **阿里云通义千问** | 云端 LLM | API key 配 .env | 必须(三选一) |
| **Milvus** | 智能问数 RAG 向量库 | Docker 容器, 19530 端口 | 可选(降级: 不用 RAG) |
| **Jina Embedding** | 文本向量化 | 本地 HTTP 38898 端口 | 可选(必须配 Milvus) |
| **MinerU (Docker)** | PDF 解析 | Docker 容器, 30000 端口 | 可选(可改云端) |
| **MinerU (云端)** | PDF 解析 | mineru.net API | 可选(可改本地) |
| **Wiki 知识库** | GB 30871 法规 | `wiki/` Markdown | 可选(降级: 不用 RAG) |

**降级策略**:
- 缺 Milvus: 智能问数降级为直连 PG, 仍可工作但 LLM 生成 SQL 准确度降低
- 缺 MinerU: 作业票审查不能上传 PDF, 需手动填写
- 缺 Wiki: 作业票审查 LLM 不引用法规条款编号

**当前生产配置** (`api/.env`):
```
LLM_PROVIDER=ollama
LLM_MODEL=qwen3.6:35b       # 35B MoE, GPU 30GB
SQ_LLM_MODEL=qwen3.6:35b
LLM_BASE_URL=http://localhost:11434/v1

PG_HOST=10.8.0.100
PG_PORT=35432
PG_DATABASE=special_operations

SQ_MILVUS_URI=http://127.0.0.1:39530
SQ_EMBEDDING_API_URL=http://127.0.0.1:38898/v1/embeddings
MINERU_LOCAL_URL=http://localhost:30000
```

---

## 四、完整架构图

```
                                ┌─────────────────┐
                                │  浏览器          │
                                │  (前端 www/)     │
                                └────────┬────────┘
                                         │ HTTP
                                         ▼
   ┌──────────────────────────────────────────────────────────────────┐
   │  FastAPI :5100  (ticket-review-lite)                            │
   │                                                                  │
   │  ┌────────────┐  ┌──────────────┐  ┌────────────┐               │
   │  │ routers/   │  │  services/   │  │smart_query/│               │
   │  │ - chat     │──│ - permits   │──│ - agent    │               │
   │  │ - permits  │  │ - rules     │  │ - streaming│               │
   │  │ - dashboard│  │ - mineru    │  │ - sessions │               │
   │  │ - files    │  │ - wiki_search│ │ - tools    │               │
   │  │ - issues   │  │ - issues    │  │ - service  │               │
   │  └────────────┘  └──────────────┘  └────────────┘               │
   │         │                │                │                     │
   │         ▼                ▼                ▼                     │
   │  ┌──────────┐    ┌──────────┐    ┌──────────────────┐           │
   │  │ SQLite   │    │ Wiki     │    │ OllamaChat       │           │
   │  │ app.db   │    │ Markdown │    │ (common/llm_utils)│           │
   │  │ (config) │    │ 知识库   │    │ + LangGraph      │           │
   │  └──────────┘    └──────────┘    │ + tool binding   │           │
   │                                  └────────┬─────────┘           │
   └─────────────────────────────────────────┼───────────────────────┘
                                             │
       ┌─────────────────────────────────────┼─────────────────────┐
       │                                     │                     │
       ▼                                     ▼                     ▼
   ┌────────┐  ┌──────────┐  ┌──────────────────────┐  ┌──────────────┐
   │ ollama │  │ MinerU   │  │ Milvus                │  │ PostgreSQL   │
   │ 11434  │  │ 30000    │  │ 19530                 │  │ 10.8.0.100   │
   │ qwen3.6 │  │ (Docker)  │  │ (Docker)              │  │ :35432       │
   │  :35b   │  │ OpenDataLab│ │ vannaddl/vannadoc/    │  │ special_ops  │
   │  35B MoE│  │ MinerU2.5 │  │ vannasql 21条         │  │              │
   └────────┘  └──────────┘  └──────────────────────┘  └──────────────┘
                     │                  │
                     │            ┌─────┴──────┐
                     │            │ Jina v3   │
                     │            │ 38898    │
                     │            │ Embedding│
                     │            └──────────┘
                     │
                ┌────┴────────────────┐
                │ VLLM EngineCore   │
                │ OpenDataLab       │
                │ MinerU2___5-Pro   │
                │ (in-container)    │
                └───────────────────┘
```

---

## 五、一键启停

### 启动

**整系统一键启动** (5100 后端 + 所有外部服务):

```bash
cd /home/czys/workspace
bash start-all.sh
```

`start-all.sh` 启动顺序:
1. vLLM (Qwen3.6-27B, 跳过如果 LLM_PROVIDER != vllm)
2. Docker 容器 (Milvus 4 容器 + MinerU 1 容器)
3. Jina Embedding (uvicorn :38898)
4. **5100 后端** (uvicorn :5100, workers=1, **必须 1 worker** 避免 MinerU vLLM 竞态)
5. Wiki 管理后台 (5050)

输出访问地址:
```
审查系统:    http://<server>:5100
MinerU:      http://<server>:30000
Milvus Attu: http://<server>:38000
```

### 停止

```bash
cd /home/czys/workspace
bash stop-all.sh
```

`stop-all.sh` 停止顺序 (与启动相反):
1. 5100 后端 (`stop_lite.sh`)
2. Jina Embedding (杀 PID)
3. MinerU (docker stop)
4. Milvus 4 容器 (docker stop)
5. vLLM (杀 PID)

### 单个组件启停

```bash
# 5100 后端
cd /home/czys/workspace/ticket-review-lite
bash start_lite.sh
bash stop_lite.sh

# ollama (systemd 管理, 用户用 sudo)
sudo systemctl start ollama
sudo systemctl stop ollama

# Docker 容器
docker start milvus-etcd milvus-minio milvus-standalone milvus-attu
docker start mineru-openai-server
docker stop milvus-etcd milvus-minio milvus-standalone milvus-attu
docker stop mineru-openai-server
```

### 健康检查

```bash
bash /home/czys/workspace/ticket-review-lite/scripts/check.sh
```

应输出所有依赖都 ✓。

---

## 六、API 与路由清单

### 主后端 FastAPI (端口 5100)

| 路径 | 方法 | 用途 |
|------|------|------|
| `/api/health` | GET | 健康检查 |
| `/api/v1/permits/upload-and-extract?permit_type=hot_work` | POST (multipart) | 上传 PDF 并提取结构化字段 |
| `/api/v1/permits/{permit_id}` | GET / PATCH | 作业票 CRUD |
| `/api/v1/permits/{permit_id}/review` | POST | 触发 LLM 审核 |
| `/api/v1/permits/{permit_id}/review/{review_id}` | GET | 查询审核结果 |
| `/api/v1/chat/sessions` | GET / POST | 会话列表 / 创建 |
| `/api/v1/chat/sessions/{id}` | GET / PATCH / DELETE | 会话详情 / 改名 / 删除 |
| `/api/v1/chat/stream` | POST (SSE) | 智能问数流式对话 |
| `/api/v1/dashboard/*` | GET | 仪表盘数据 |
| `/api/v1/files` | POST / GET | 文件上传 / 列表 |
| `/api/v1/issues` | GET | 问题工单 |
| `/api/v1/rules` | GET / POST | 审查规则 |
| `/api/v1/rule-documents` | GET / POST / DELETE | 法规文档管理 |
| `/api/v1/review-external` | POST | 外部审查入口 |
| `/api/v1/sqlagent-admin/*` | GET / POST | 智能体配置 (运行时热配) |

### 外部服务

| 端口 | 服务 | 用途 |
|------|------|------|
| 5100 | FastAPI | 5100 后端 |
| 11434 | Ollama | LLM (qwen3.6:35b) |
| 8001 | vLLM | 可选 LLM (Qwen3.6-27B) |
| 30000 | MinerU | PDF 解析 (OpenDataLab MinerU2.5) |
| 19530 | Milvus | 向量库 (5 张表: vannaddl/vannadoc/vannasql) |
| 38898 | Jina Embedding | 文本向量化 (Jina v3, 768 维) |
| 38899 | Attu (Milvus UI) | 可选, 38000 是 host-mapped |

---

## 七、目录结构

```
/home/czys/workspace/                          # 主工作区
├── ticket-review-lite/                         # 本项目
│   ├── api/                  # FastAPI 后端
│   │   ├── main.py           # 入口 (含 SPA fallback)
│   │   ├── .env              # 实际配置
│   │   ├── .env.template     # 配置模板
│   │   ├── requirements.txt  # Python 依赖
│   │   ├── www/              # 前端静态文件 + inline JS
│   │   │   ├── index.html    # React SPA 入口 (含智能问数 delete button 注入)
│   │   │   ├── assets/       # index-BxUfRIww.js + index-CAAgnnNt.css (React 编译产物)
│   │   │   └── favicon.ico
│   │   ├── routers/          # 10 个 API 路由
│   │   ├── services/         # 12 个业务服务
│   │   ├── smart_query/      # 智能问数模块 (核心)
│   │   │   ├── agent/        # LangGraph create_agent
│   │   │   ├── clients/      # OllamaChat 工厂
│   │   │   ├── config/       # prompts + settings
│   │   │   ├── middleware/   # trace + ui_events
│   │   │   ├── tools/        # get_table_schema / validate_sql / execute_sql
│   │   │   ├── sessions.py   # SQLite 会话存储
│   │   │   ├── streaming.py  # SSE 流式对话 + 第二次 LLM 报告生成
│   │   │   └── service.py    # Agent 初始化
│   │   ├── database/         # PG 访问 + init.sql (7 张作业票表)
│   │   ├── prompts/          # 9 个 LLM 提示词 (3 票种 × extract + review)
│   │   ├── config/           # pydantic-settings 配置
│   │   ├── middleware/       # trace + ui_events
│   │   ├── security/         # AAD 认证
│   │   ├── app/data/         # SQLite + 上传文件
│   │   ├── tests/            # 单元测试
│   │   └── venv/             # Python 虚拟环境
│   ├── common/               # 公共模块
│   │   ├── llm_utils.py      # OllamaChat (核心!)
│   │   ├── logger.py
│   │   └── models.py
│   ├── wiki/                 # GB 30871 法规知识库 (Markdown)
│   ├── scripts/              # 运维/测试脚本
│   │   ├── start-all.sh
│   │   ├── stop-all.sh
│   │   ├── check.sh          # 健康检查
│   │   ├── backup.sh         # 备份
│   │   ├── build.sh          # 前端构建
│   │   ├── rag_train_cli.py  # RAG 训练 CLI
│   │   ├── test_smart_query.sh
│   │   └── test_permit_review.sh
│   ├── start_lite.sh         # 5100 启动 (1 worker!)
│   ├── stop_lite.sh
│   ├── compile_py.sh         # Cython 源码保护 (可选)
│   ├── DEPLOY.md             # 详细部署手册
│   ├── README.md             # 本文件
│   ├── LICENSE
│   └── CHANGELOG.md
│
├── milvus/                   # Milvus 向量库 (docker)
├── MinerU/                   # PDF 解析 (源码)
├── jina-embedding/           # 文本向量化
├── openvpn/                  # VPN 客户端
├── wiki-admin/               # Wiki 管理后台 (5050)
├── llmwiki_data/             # Wiki 数据
├── logs/                     # 外部服务日志
├── test_data/                # 测试 PDF
├── start-all.sh              # 整系统一键启动
└── stop-all.sh               # 整系统一键停止
```

---

## 八、配置项完整参考 (`api/.env`)

```bash
# === 通用 ===
DEBUG=False
SERVE_STATIC=True           # 是否托管前端 (默认 True)
LOG_LEVEL=INFO
LOG_TO_FILE=True
SQLITE_PATH=./app/data/app.db
LOCAL_DOCS_DIR=./app/data/documents

# === LLM (三选一) ===
LLM_PROVIDER=ollama          # vllm / ollama / dashscope
LLM_API_KEY=***              # ollama/vllm 可空, dashscope 必填
LLM_BASE_URL=http://localhost:11434/v1
LLM_MODEL=qwen3.6:35b        # 当前生产
LLM_VISION_MODEL=            # PDF 解析用, 留空用 LLM_MODEL

# === PostgreSQL (作业票数据) ===
PG_HOST=10.8.0.100
PG_PORT=35432
PG_DATABASE=special_operations
PG_USER=postgres
PG_PASSWORD=***

# === MinerU (PDF 解析) ===
MINERU_BASE_URL=https://mineru.net    # 云端
MINERU_API_KEY=***
MINERU_LOCAL_URL=http://localhost:30000  # 本地 Docker
MINERU_MODEL_VERSION=vlm
MINERU_BBOX_UNITS=px
MINERU_BBOX_CONTENT_COVERAGE=0.85
MINERU_MAX_WAIT_SEC=900

# === Wiki 知识库 (作业票审查法规) ===
WIKI_PATH=./wiki
WIKI_SEARCH_LIMIT=3

# === 智能问数 ===
SQ_LLM_MODEL=qwen3.6:35b            # 默认沿用 LLM_MODEL
SQ_LLM_TEMPERATURE=0.2
SQ_LLM_MAX_TOKENS=2000               # 2000 够 100+ 行 CTE + 报告
SQ_EMBEDDING_PROVIDER=jina
SQ_EMBEDDING_API_URL=http://127.0.0.1:38898/v1/embeddings
SQ_EMBEDDING_API_KEY=***
SQ_MILVUS_URI=http://127.0.0.1:39530
SQ_MILVUS_METRIC_TYPE=COSINE          # COSINE / L2
SQ_AGENT_RECURSION_LIMIT=500
```

---

## 九、关键模块详解

### 1. OllamaChat (`common/llm_utils.py`) - 核心

**统一的 LLM 客户端**,检测到 ollama 自动用 `/api/chat` 原生协议 + `think=False`:

```python
# 关键: 必须保留 tool_calls 字段 (Ollama 0.5.7 必需)
def _convert_messages(self, messages):
    for msg in messages:
        if isinstance(msg, ToolMessage):
            ollama_msg["tool_call_id"] = tc_id
        elif role == "assistant" and msg.tool_calls:
            ollama_msg["tool_calls"] = [{
                "function": {
                    "name": tc['name'],
                    "arguments": dict,  # 必须是 dict 不是 string
                }
            }]
```

**配置**:
- `cache_prompt: False` (顶层, 不是 options) - 避免 prefix cache 命中返回空
- `think: False` - 关闭 qwen3.6 thinking
- `num_predict: 1000-3000` - 避免 done=length 截断
- `temperature: 0.1-0.2` - 智能问数 / 作业票审查

### 2. 智能问数 RAG (`smart_query/`)

**5 步强制工作流**:
```
1. get_all_tables_info()       # 拿 7 张表 schema
2. get_table_schema(question)  # RAG 检索 top-3 DDL + top-3 SQL + 业务文档
3. LLM 拼 SQL                  # 套用 RAG 训练数据里的 SQL 模板
4. validate_sql_syntax(sql)   # PG EXPLAIN 真实验证 (不是字符串检查)
5. execute_sql(sql)            # 真实执行, 拿数据
```

**第二次 LLM 调** (streaming.py):
- 用 `OUTPUT_FORMAT_PROMPT` (1328 字符) 生成 chartconfig JSON + 3 段报告
- 检查 `query_data` 真的有数据, 没数据时不瞎编

**RAG 训练数据现状** (Milvus, 用户上传, 21 条):
- `vannaddl` (9 DDL): hot_work_permits, confined_space_permits, hot_work_gas_analysis, confined_space_gas_analysis, permit_blind_plate, work_safety_checks, safety_check_items, test_work_ticket, test_work_ticket_clean
- `vannadoc` (2 文档): 数据库总览, test_work_ticket_clean 字段说明
- `vannasql` (10 SQL 模板): 各动火方式作业数量, 双重角色违规 (CTE), 空间维度统计, 动火作业总数, 各施工单位, 各区域动火, 2026-01-01 基础统计, 单位强度排名, 人员工作强度, 作业高峰时间段

### 3. 作业票审查 (`services/permits_service.py` + `prompts/`)

**流程**:
1. PDF 上传 → 保存到 `api/app/data/uploads/`
2. MinerU (本地 Docker `docker exec mineru CLI`) 解析 PDF → markdown
3. 第一次 LLM 调: 按 `prompts/{type}_extract.md` 提取 38 字段结构化 JSON
4. 第二次 LLM 调: 按 `prompts/{type}_review.md` 8 维度审核 + 引用 GB 30871 条款
5. 保存到 SQLite `permits` + `gas_analyses` + `safety_checks` + `reviews` 4 张表
6. 渲染高亮 (bbox 覆盖在 PDF 渲染图上)

**关键**:
- `max_tokens=3000` (避免 1500 截断)
- 1 worker (避免 docker exec 竞态)
- prompts 9 个分类型管理, 修改直接改文件无需重启

### 4. 前端 inline JS 注入 (`api/www/index.html`)

**React 编译产物不能改**,用 inline JS 注入**智能问数侧栏删除按钮强制显示 + 二次确认**:

```js
// 找 session item 容器: 3 子元素 + 第 3 个是 button + svg + 父级有时间文本
function isSessionItem(el) {
  return el.children.length === 3
    && el.children[2].tagName === 'BUTTON'
    && el.children[2].querySelector('svg')
    && /(\d+\s*分钟前|刚刚|未命名对话)/.test(el.textContent);
}

// 缩小到 12x12
delBtn.style.minWidth = '12px';
delBtn.style.minHeight = '12px';

// 二次确认
if (!confirm('确定要删除会话 ... 吗?')) return;
// 调 React 原 onClick (内部 t.current 拿真函数)
props.onClick(fakeEvent);
```

---

## 十、遇到的 16 个核心问题与解决方案

### 问题 1: PDF 审查 HTTP 500 - MinerU 报 vLLM 错

**症状**: 
```
HTTPException: 解析失败: Client error '404 Not Found' for url 'http://localhost:30000/file_parse'
```

**根因**:
- 旧版 MinerU 用 `/file_parse` HTTP 端点
- 新版 MinerU 2.5 用 `/v1/responses` 或 `docker exec` CLI 模式
- `permits_service.py` 用了 `docker exec mineru CLI` 模式 (已对)
- **但 5100 启动用 `--workers 2`**: 2 个 worker 同时调 docker exec, 容器内 vLLM 同时接 2 个请求竞态, 报 "Unexpected status code"

**解决**:
1. `start_lite.sh` 改 `--workers 1`
2. `_init_llm` `max_tokens` 1500 → 3000 (避免 LLM done=length 截断)
3. 手动 `docker exec mineru -p /work/input/1.pdf ...` 验证 CLI 可独立跑

**验证**:
```
HTTP 200, 60.9s 总耗时
- MinerU: 26.9s
- LLM: 34s
- 38 字段 + 4 gas_analyses + 16 safety_checks
```

### 问题 2: 智能问数报 "auto tool choice requires --enable-auto-tool-choice and --tool-call-parser"

**症状**: 智能问数只能调 1 个工具就停了, `tool_calls=[]`

**根因**:
- 5100 端 trace: `ollama REQ: msg_count=4, tools=4, done=stop, content='', tool_calls=0`
- 直接 curl ollama + tools schema 工具调用 work, 5100 端不 work

**根因 2**: **`OllamaChat._convert_messages` 只转 `{role, content}`, 丢失 `tool_calls` 字段**!

LangGraph agent 把历史 assistant 消息的 tool_calls 喂回 ollama 时, ollama 看到"空 assistant"+"tool result", 不知道下一步该调什么。

**解决**:
```python
def _convert_messages(self, messages):
    for msg in messages:
        if isinstance(msg, ToolMessage):
            ollama_msg["tool_call_id"] = tc_id
        elif role == "assistant" and msg.tool_calls:
            ollama_msg["tool_calls"] = [{
                "function": {
                    "name": tc['name'],
                    "arguments": dict,  # 必须是 dict 不是 string!
                }
            }]
```

**关键细节**:
- `arguments: "{}"` 字符串 → ollama 报 `can't find closing '}'` 解析失败
- `arguments: {}` dict → 正常

### 问题 3: LLM 写伪 tool_call 文本 - "tool_call: get_all_tables_info()</arg_value>"

**症状**: 
```
LLM END: content="tool_call: get_all_tables_info()</arg_value>", tool_calls=0
```

**根因**: `glm-4.7-flash-nothink` 30B MoE 在长 system prompt (>1000 字符) + 工具 schema 组合下, LLM 倾向写"伪 JSON 工具调用"文本, 绕开 ollama 的 tool_calls 协议。

**实测对照**:
| 字符数 | 4 tools | 状态 |
|---|---|---|
| 15 (极简) | 1 tool | ✅ 100% 真 tool_calls |
| 405 (核心) | 4 tools | ✅ 100% |
| 8399 (原版) | 4 tools | ❌ 0% 全伪 JSON |

**解决**: system prompt < 1000 字符

### 问题 4: 换 qwen3.6:35b 后 ollama 0.5.7 + cache_prompt bug

**症状**: LLM 第 2 轮不调工具, `eval_count=1` 1 个 token 就 done=stop

**根因**:
- ollama journalctl: `eval time = 0.00 ms / 1 tokens` + 0.0s 返回
- **ollama 0.5.7 prefix cache bug** - 包含空 content + tool_calls 时, 后续相同 prefix 不再调工具, 直接返回空

**解决**:
```python
payload = {
    "model": ...,
    "messages": ...,
    "stream": False,
    "think": False,
    "cache_prompt": False,  # 顶层, 不是 options 里!
    "options": {"temperature": ..., "num_predict": ...}
}
```

**坑**: `cache_prompt` 放 `options` 里 ollama 0.5.7 不识别, 必须顶层。

### 问题 5: validate_sql_syntax 假验证 (假绿勾)

**症状**: SQL 全角逗号 `apply_unit AS 申请单位/区域名称,` 报 syntax error, 但 validate 通过, LLM 不知道错, 死循环重试

**根因**: 之前 `validate_sql_syntax` 只检查安全关键词 + 括号, 不调 PG 解析器

**解决**: 用 `psycopg2` 直接连 PG 调 `EXPLAIN <sql>`:
```python
def validate_sql_syntax(sql: str) -> str:
    try:
        with conn.cursor() as cur:
            cur.execute(f"EXPLAIN {first_stmt}")  # 不真执行
            rows = cur.fetchall()
            return f"✅ 语法验证通过 (PG EXPLAIN 执行计划):\n{plan_str}"
    except psycopg2.Error as e:
        return f"❌ 语法验证失败 (PG EXPLAIN 报错):\n{err_msg}"
```

**EXPLAIN 不真执行**, 但 PG 解析器抓语法/表/列/聚合错。

### 问题 6: session_history 污染 - LLM hallucination 累积

**症状**: 重复问同样问题, 答案越来越差, LLM 模仿自己之前的"半截"答案继续 hallucination

**根因**:
```python
# 之前
history = get_session_history(sid)
messages_payload = [msg for msg in history]  # 全传!
```

LLM 看到 msg[2] assistant "我来帮您分析动火作业统计数据" (半截, 没真调工具), 模仿写"我将为您..."

**解决**:
```python
# 只取最近 1 轮
recent_history = history[-2:]
messages_payload = [{"role": msg["role"], "content": msg["content"]} for msg in recent_history]
```

### 问题 7: RAG 训练数据冗余 - num_entities vs unique 数量不一致

**症状**:
```
vannaddl: num_entities=16, query 返回 9
vannasql: num_entities=29, query 返回 10
```

**根因**: Milvus Lite 的 delete 是**软删除**, 被删的 entity 还在 num_entities 里。query 默认排除但 stats 显示总数。

**解决**:
1. 备份所有 unique 实体 → `/tmp/milvus_backup.json`
2. `drop_collection` + `create_collection` + 重新 insert
3. 用 `DataType.VARCHAR` 不是 `'VARCHAR'`
4. 强制 `flush` 后 `row_count == query_count`

**结果**:
- `vannaddl` row_count=9 (你的 9 DDL)
- `vannadoc` row_count=2 (你的 2 文档)
- `vannasql` row_count=10 (你的 10 SQL)

### 问题 8: LLM 看到 RAG 100+ 行 CTE SQL 模板后不调工具

**症状**: LLM 拼 SQL 100+ 行 CTE 进 content, 2000 token 用满 `done=length`, 不调 execute_sql

**根因**: LLM 看到 RAG 检索返回的复杂 SQL 模板, 倾向直接抄 SQL 文本进 AI 消息

**解决**:
1. system prompt 加铁律: 
```
**铁律**: 拼完 SQL 立刻调 execute_sql, 不要在 AI 消息里把 SQL 文本写出来! 
100+ 行 CTE 写到 AI 消息会占满 2000 token 上限, 导致没 token 调工具
```
2. `max_tokens` 1000 → 2000
3. RAG few-shot 指令: "如果有类似问题的 SQL 模板, 直接套用"

### 问题 9: ui_events_middleware 干扰工具调用

**症状**:
```
生成工具描述失败: 'str' object has no attribute 'content'
```

**根因**: `ui_events_middleware` 的 `ui_tool_trace` 内部为每个工具调 LLM 生成描述 (5+ 秒/工具), 抛异常后影响主流程

**解决**: `service.py` `enable_ui_events=False` 关闭 UI 事件追踪

### 问题 10: 5100 SPA 路由 404 - `/smart-query` 跳错页面

**症状**: `http://192.168.222.168:5100/smart-query` 404

**根因**:
- React 端 `<a href="/smart-query">` 走 history API 路由
- 但用户直接访问 `/smart-query` 时, 后端没 fallback
- StaticFiles 找不到 `/smart-query` 物理文件 → 404

**解决** (`main.py`): 加 SPA fallback
```python
async def spa_fallback_handler():
    return FileResponse("www/index.html")

for route in ["/smart-query", "/ticket-review", "/agent-admin", "/dashboard", "/settings"]:
    app.get(route, include_in_schema=False)(spa_fallback_handler)
```

### 问题 11: 独立 HTML 智能问数页 JS 报错 "Cannot read properties of null"

**症状**: 第一次独立 HTML 版本显示"加载失败: Cannot read properties of null (reading 'addEventListener')"

**根因**: `sessionList.addEventListener` 之前没判空, 而且独立 HTML 页**不如 React 版本完整**(UI 样式/版面对不上用户的预期)

**解决**: **删除独立 HTML 页面**, 改用 SPA fallback 让 React 原版接管 + inline JS 注入删除按钮

### 问题 12: 验证 vLLM 启动参数 - `qwen3_xml` vs `qwen3xml`

**症状**: vLLM 启动失败, keyError: 'qwen3xml'

**根因**: vLLM 工具调用 parser 名字是 `qwen3_xml` (下划线), 不是 `qwen3xml`

**解决**: 修 `start-all.sh`:
```bash
--tool-call-parser=qwen3_xml   # 不是 qwen3xml
```

### 问题 13: React 端 onClick.toString() 拿不到函数 - React 19 ref 转发

**症状**: 加 inline JS 用 `onClick.toString()` 找 delete button, 所有 button 的 onClick 都是占位符 `(...n)=>{const r=t.current;return r(...n)}`

**根因**: React 19+ 用 ref + spread 转发 onClick, toString 拿到的是占位符, 真实函数是 `t.current`

**解决**: 改用 **DOM 结构特征**找 session item 容器:
```js
function isSessionItem(el) {
  return el.children.length === 3
    && el.children[2].tagName === 'BUTTON'
    && el.children[2].querySelector('svg')
    && /(\d+\s*分钟前|刚刚|未命名对话)/.test(el.textContent);
}
```

### 问题 14: 二次确认后 React onClick 不触发

**症状**: 加 confirm 弹窗, 接受后没真的删除

**根因**: confirm 后 React 19 占位符 onClick 没真调, 真实函数是 `t.current`

**解决**: 找 React fiber 上的 `__reactProps` 拿 props.onClick, 调它:
```js
const reactPropsKey = Object.keys(btn).find(k => k.startsWith('__reactProps'));
const props = btn[reactPropsKey];
const fakeEvent = new MouseEvent('click', { bubbles: true, cancelable: true });
props.onClick(fakeEvent);  // 内部 t.current 拿真函数
```

### 问题 15: SPA fallback lambda 拼写错误导致 500

**症状**: `/smart-query` 500 Internal Server Error

**根因**: 
```python
# 错
app.get(route, include_in_schema=False)(lambda r=route: spa_fallback(r))
# 错在 lambda 接收 path 参数但实际 handler 不接受 path
# 导致 FastAPI 把 coroutine 当 response 序列化
```

**解决**: 直接传 handler 引用, 不要 lambda 包装:
```python
async def spa_fallback_handler():
    return FileResponse("www/index.html")

for route in ["/smart-query", ...]:
    app.get(route, include_in_schema=False)(spa_fallback_handler)
```

### 问题 16: ollama 端 prefix cache + thinking + tool_calls 组合 bug

**症状**: qwen3.6:35b + think=False + tool_calls + cache_prompt=True → 0.0s 返回空响应

**根因**: ollama 0.5.7 的 prefix cache 在 messages 包含空 content + tool_calls + 多轮历史时, 命中缓存但 LLM 实际没生成

**解决**:
- `cache_prompt: False` 顶层
- 加 `log_info("ollama invoke: ... eval_count=...")` 监控
- 监控 `eval_count=1` + `done=stop` 是空响应的标志

---

## 十一、运维与故障排查

### 健康检查

```bash
bash /home/czys/workspace/ticket-review-lite/scripts/check.sh
```

### 智能问数调试

```bash
# 1. 列 sessions
curl -s 'http://127.0.0.1:5100/api/v1/chat/sessions?limit=10'

# 2. 流式问
curl -N -X POST 'http://127.0.0.1:5100/api/v1/chat/stream' \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"<id>","question":"数据库有多少张动火作业票"}'

# 3. 看 trace
tail -f /home/czys/workspace/ticket-review-lite/api/app.log | grep -E 'ollama invoke|TOOL|Error'
```

### 常见错误

| 错误 | 原因 | 解决 |
|------|------|------|
| HTTP 500 /file_parse | MinerU 路径错或 docker 竞态 | 改 1 worker + 改用 docker exec |
| "auto tool choice requires..." | vLLM 启动参数没加 | 修 start-all.sh |
| LLM 写伪 tool_call | system prompt >1000 字符 | 缩 system prompt |
| LLM eval_count=1 空响应 | ollama prefix cache bug | cache_prompt=False 顶层 |
| 智能问数 LLM 拿不到 DDL | get_table_schema top-k 太大 | n_results=3 |
| PDF 提取只输出部分字段 | max_tokens=1500 截断 | 改 3000 |
| 智能问数 hallucination | session_history 全传 | history[-2:] |

### 性能调优

| 参数 | 当前 | 建议 |
|------|------|------|
| uvicorn workers | 1 | **必须 1** (MinerU 竞态) |
| Milvus top-k | 3 | 3-5 (避免 LLM 拿到太多 DDL 思维混乱) |
| ollama num_predict | 1000-2000 | 复杂报告 2000, 简单 500 |
| system prompt 字符 | 3959 + 1328 (两段式) | 拆分避免单段 >1000 |
| LLM temperature | 0.1-0.2 | 智能问数 0.2, 审查 0.1 |
| RAG top-3 DDL + top-3 SQL | ThreadPoolExecutor 并发 | <2s |

### 数据备份

```bash
bash /home/czys/workspace/ticket-review-lite/scripts/backup.sh
# 输出: ticket-review-lite/backups/
# 保留 30 天
```

### 更新前端/后端

```bash
# 前端 (改 www/index.html inline JS 或 assets/...)
bash stop_lite.sh
bash start_lite.sh

# 后端
# 替换 api/ 代码后重启
bash stop_lite.sh
bash start_lite.sh
```

---

## 十二、文档索引

- **[README.md](README.md)** (本文件) - 系统全貌 + 16 个核心问题解决方案
- **[DEPLOY.md](DEPLOY.md)** - 部署操作手册 (详细)
- **[CHANGELOG.md](CHANGELOG.md)** - 版本变更记录
- **[api/smart_query/config/prompts.py](api/smart_query/config/prompts.py)** - 智能问数 5 步流程 + RAG few-shot 提示词
- **[api/prompts/](api/prompts/)** - 9 个作业票审查/提取提示词 (3 票种 × 2 类型)

## 许可

[LICENSE](LICENSE)
