# 变更记录 (Changelog)

## [Unreleased]

### 修复 (2026-06-07 session)
- **智能问数 LLM 步骤数硬上限** (streaming.py):
  - 加 `MAX_TOTAL_STEPS = 15` 总步骤数硬上限 (原 LangGraph `recursion_limit=150` 太高)
  - 加 `MAX_CONSECUTIVE_EXECUTE_SQL = 2` 连续 execute_sql 计数 (LLM 拿到数据后继续查就停)
  - 加 `force_stop` flag 让 break 真正跳出 `for event` 循环 (之前 break 只跳出内层 for tool_call)
- **prompts.py 加铁律** (SYSTEM_PROMPT 步骤 5 后):
  - "**拿到 1+ 行 execute_sql 结果后, 立即给 final_answer**, 不许再调任何工具, 不许再调 execute_sql!"
  - "违反此铁律会被系统强制终止, 浪费 30+ 步 LLM 调用"
- **修复 systemd `ticket-review.service` 疯狂重启 bug**:
  - 原 service Type=simple + nohup, parent 立刻 exit 0, systemd 误以为死了
  - 写 `/home/czys/workspace/fix-ticket-review-service.sh` 让用户用 sudo 修复 (改 Type=simple + PIDFile + uvicorn 前台运行)
- **streaming.py 配合**: report gen 拿 `query_data` (即使 agent stream 提前停, 也能写报告)

### 整改 (2026-06-07 session)
- **改 `start-all.sh`**: 加 ollama 启停 + status/health/help/dry-run 子命令 + 统一健康检查
- **改 `stop-all.sh`**: 加 status/health/help 子命令 + `--dry-run` + `--force` 选项 + DRY-RUN 模式
- **写 `/home/czys/workspace/ticket-review-lite/README.md`**: 858 行系统全貌 (12 章节, 含 16 个核心问题解决方案)
- **写 `/home/czys/workspace/fix-ticket-review-service.sh`**: sudo 修 systemd service 脚本
- **前端智能问数侧栏加删除按钮** (api/www/index.html inline JS):
  - 用 DOM 结构特征找 session item 容器 (3 子元素 + 第 3 个 button + svg + 时间文本)
  - 强制显示 + 缩小到 12×12 (原来 24×24 一半)
  - 加 confirm 二次确认 (只拦截 data-fixed=1 的 button, 不误伤其他)
  - 通过 `props.onClick(fakeEvent)` 调 React 原 onClick (走 N → MU → DELETE /api/v1/chat/sessions/{id})
- **SPA fallback 路由** (api/main.py):
  - `/smart-query` `/ticket-review` `/agent-admin` `/dashboard` `/settings` 5 个 React 路由 fallback 返回 index.html
  - 之前 React 端 `<a href="/smart-query">` 直接访问 404

## [历史]

### 整改
- 移除冗余/死代码:
  - `services/aml_client.py` (Azure ML Client, 0 引用)
  - `_compile_worker.py` (Cython 编译 worker, 重复)
  - `.pid` 临时文件
  - 3 个 `.env.bak*` 备份
  - 2 个本地 `milvus.db` (实际连容器 Milvus)
  - 根目录 `app.log` 重复日志
- 新增文档: `README.md`, `LICENSE`, `.gitignore`, `CHANGELOG.md`
- 新增 `api/database/init.sql` (7 张作业票表 DDL)
- 新增 `scripts/` 目录: `build.sh`, `backup.sh`, `check.sh`
- 新增 `api/tests/` 基础 smoke test
- `scripts/` 收纳 3 个测试/训练 CLI 工具
- 改 `DEPLOY.md` 对齐实际代码:
  - 补充 ollama LLM provider
  - 补充外部服务启动说明 (start-all.sh)
  - 补充 uvicorn `--workers 2`
  - 补充双 RAG 体系 (Milvus 智能问数 + Wiki 作业票审查)
  - 补充 scripts/ 章节

### 修复
- 5100 启动: `model_config` 移到 Settings class 内部,pydantic-settings 2.5.2 正确读取 `.env`
- vLLM tool parser 用 `qwen3_xml` (下划线) 而非 `qwen3xml`
- `Milvus_VectorStore.metric_type` 默认改 COSINE 与 MyVanna 一致
- `get_training_data` 显式列 `output_fields` 修复 KeyError
- `llm_utils.extract_llm_content` 增加 JSON 截断自动修复
- `config.py` 加载 `.env` 强制显式 `_env_file=...` 双保险

### 性能
- uvicorn 启动加 `--workers 2`(用户并发)
- RAG 3 个 Milvus 检索用 `ThreadPoolExecutor` 并发(6s → 2s)
- vLLM `--max-num-seqs 16` 连续批处理

## 历史
- 2024-XX-XX: 初始版本
