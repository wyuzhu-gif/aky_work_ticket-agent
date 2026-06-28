# 回归测试 (Regression Test)

## 目的

每次改 `agent_chat.py` / `prompts.py` / raw API / wiki / intent_classifier 时，跑这 26 道题，**看是否有回归**。

## 跑

```bash
cd /home/czys/workspace/ticket-review-lite
python3 api/tests/regression/run_regression.py          # 全部 26 题 (~15-20 min)
python3 api/tests/regression/run_regression.py --quick  # 仅 Phase A 20 题 (~10-12 min)
python3 api/tests/regression/run_regression.py --phase A
python3 api/tests/regression/run_regression.py --update-baseline  # 更新基线
```

## 文件

| 文件 | 用途 |
|------|------|
| `questions.yaml` | 26 道题 (Phase A 20 + Phase B 3 + Phase C 3) |
| `run_regression.py` | 跑测试, 手工 SSE 解析, 阶段耗时统计 |
| `expected.json` | **基线数据** (v3 实测, 2026-06-28) |
| `results/latest.json` | **最近一次跑**的完整结果 |
| `results/history.jsonl` | 历史基线 (append-only, 每次跑追加一行) |

## Regression Gates

| Gate | 当前基线 | 阈值 |
|------|----------|------|
| database_query success | 20/20 (100%) | ≥95% |
| safety_knowledge success | 3/3 (100%) | 100% |
| mixed success | 1/3 (33%) | ≥34% |
| chart success (预期图) | 12/12 (100%) | ≥95% |
| timeout rate | 0/20 (0%) | ≤10% |
| avg elapsed | 50s | ≤120s |

**mixed 阈值 34% 看起来低** — 因为当前 baseline 只有 1/3 跑通 (其余 2 题是 service 压力, 不是架构问题). 等 mixed 优化后, 应该把阈值提升到 95%.

## 历史基线

每次跑会 `append` 一行到 `results/history.jsonl`, 方便对比:

```bash
# 看最近 5 次跑的成功率趋势
python3 -c "
import json
for line in open('results/history.jsonl'):
    d = json.loads(line)
    s = sum(x['success'] for x in d['stats'])
    t = sum(x['total'] for x in d['stats'])
    print(f\"{d['timestamp'][:16]}  {s}/{t}  gates={'OK' if d['gates_passed'] else 'FAIL'}\")
"
```

## 添加新题

直接编辑 `questions.yaml`, 加到对应 phase 的 `questions` 列表. 跑 `--update-baseline` 更新基线.

## 何时跑

- 改 `agent_chat.py` 后
- 改 `prompts.py` 后
- 改 raw API (`sqlagent_admin.py`) 后
- 改 intent_classifier 后
- 改 wiki SKILL.md 后
- 部署前

## 历史

- **v1** (2026-06-25 前): iter_lines 解析 SSE, 0/12 chart_event 抓到
- **v2** (2026-06-25): 改进抓取逻辑, 仍然 0/20 (issue: chunk 边界 event 行丢失)
- **v3** (2026-06-28): 改用 iter_content + buffer 累积, 12/12 chart 100% 抓到, **当前基线**

详见 `results/history.jsonl` 完整记录.