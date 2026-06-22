# Hermes Skill 集成 - 回退预案

## 版本 Tag

| Tag                             | 说明                                                | 集成位置               |
|---------------------------------|-----------------------------------------------------|------------------------|
| v1.0.0-stable-pre-hermes-skill  | 集成前稳定基线（前端、后端、LangChain agent 全不变） | —                      |
| v1.1.0-hermes-skill-b           | B 方案：hermes skill 集成 ticket-review /api/v1/chat | ~/.hermes/skills/ticket-nl2sql/SKILL.md |

## B 方案说明

**核心改动**：仅在 `~/.hermes/skills/` 下新增 1 个文件（ticket-nl2sql/SKILL.md，~60 行）。
ticket-review 仓库**零代码改动**。前端**零代码改动**。LangChain agent + 339 行 SYSTEM_PROMPT + 5 铁律 + chartconfig **完整保留**。

**调用链**：
```
hermes CLI / Chat
    ↓ 看到 ticket-nl2sql skill
LLM 决定调它（业务数据问答）
    ↓
LLM 写 curl 调 ticket-review /api/v1/chat (非流式)
    ↓
LangChain agent + 339 行 prompt 跑完整 5 步 NL2SQL
    ↓
内嵌 hermes subprocess (call_hermes_sync) 增强 wiki
    ↓
返完整 answer (含 chartconfig + 数据 + 法规引用 + 建议)
    ↓
hermes 拿 answer 给用户
```

## 回退步骤

**如果 B 方案有问题需要回退**（任何一步可选）：

### 完整回退（删除 hermes skill）

```bash
rm -rf ~/.hermes/skills/ticket-nl2sql
hermes skills list 2>&1 | grep ticket-nl2sql   # 应该找不到
```

### ticket-review 代码回退（如未来真有代码改动）

```bash
cd /home/czys/workspace/ticket-review-lite
git fetch origin
git checkout v1.0.0-stable-pre-hermes-skill
# 或
git reset --hard v1.0.0-stable-pre-hermes-skill
```

## 回退影响范围

| 组件             | 回退成本    | 影响                                  |
|-----------------|------------|--------------------------------------|
| ticket-review 代码 | 5 分钟     | 零（本次集成未改任何代码）             |
| hermes skill    | 1 分钟      | 删除 SKILL.md 即可                    |
| 前端 UI          | 0          | 零改动                                |
| 数据库 / 训练数据 | 0          | 零影响                                |
| LangChain agent  | 0          | 完整保留                              |

## 验证回退成功

```bash
# 1. ticket-review 端点工作
curl http://localhost:5100/api/wiki?q=动火

# 2. 前端浏览器访问 /smart-query 正常
# 浏览器: http://localhost:5100/smart-query

# 3. hermes 不再调 ticket-nl2sql skill
hermes skills list 2>&1 | grep ticket-nl2sql   # 应该找不到

# 4. 原 SSE 流式端点正常
curl -N -X POST http://localhost:5100/api/v1/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"question": "echo TEST"}'
```

## 当前版本

**v1.1.0-hermes-skill-b**（2026-06-22）

- 集成方式：hermes skill 调 ticket-review /api/v1/chat 非流式端点
- NL2SQL 准**确**率：100%（不丢，339 行 prompt 完整保留）
- ticket-review 代码改动：0
- 前端改动：0
- 实测耗时：~17s（hermes subprocess + ticket-review LangChain agent 一次完整跑）
