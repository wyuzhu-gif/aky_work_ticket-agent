#!/usr/bin/env python3
"""
回归测试 - Hermes 智能问答
基于 26 道题测试集, 验证 Phase 3 数据驱动架构

跑: python tests/regression/run_regression.py
     python tests/regression/run_regression.py --phase A  # 只跑 Phase A
     python tests/regression/run_regression.py --quick     # 快速模式 (Phase A only)

输出: tests/regression/results/latest.json (含每题详情 + 阶段耗时)
      tests/regression/results/history.jsonl (历史基线, append-only)

对照: tests/regression/expected.json (基线)
"""
import json
import time
import sys
import argparse
import os
import re
from pathlib import Path
from datetime import datetime

# 路径
REGRESSION_DIR = Path(__file__).parent
PROJECT_ROOT = REGRESSION_DIR.parent.parent.parent  # api/tests/regression -> api -> ticket-review-lite
RESULTS_DIR = REGRESSION_DIR / "results"
RESULTS_DIR.mkdir(exist_ok=True)

try:
    import requests
    import yaml
except ImportError as e:
    print(f"❌ 缺依赖: {e}. 跑: pip install requests pyyaml")
    sys.exit(1)

API_BASE = os.environ.get("API_BASE", "http://127.0.0.1:5100")


def load_questions():
    """加载 questions.yaml"""
    yaml_path = REGRESSION_DIR / "questions.yaml"
    with open(yaml_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def run_one(question, max_wait=60):
    """单题: 手工 SSE 解析 + 阶段耗时统计"""
    payload = {
        "question": question["text"],
        "stream": True,
        "messages": [{"role": "user", "content": question["text"]}],
        "skills": ["ticket-nl2sql", "llm-wiki"]
    }
    t0 = time.time()
    timing = {}
    result = {
        "question": question["text"],
        "expect_chart": question.get("expect_chart", False),
        "expect_tool_calls_zero": question.get("expect_tool_calls_zero", True),
    }
    try:
        r = requests.post(f"{API_BASE}/api/v1/agent/chat",
            json=payload, timeout=max_wait, stream=True)
        if r.status_code != 200:
            result["err"] = f"HTTP {r.status_code}"
            return result

        full_answer = ""
        tool_calls = 0
        chart_event = None
        response_event = None
        first_byte_at = None
        last_byte_at = None

        # ⚠️ 关键: 用 iter_content + buffer 累积, 不用 iter_lines
        buffer = ""
        # Phase 4.2: 调用链统计 (从 SSE 抓 llm_wiki 调用)
        llm_wiki_count = 0
        for chunk in r.iter_content(chunk_size=8192, decode_unicode=True):
            if not chunk: continue
            now = time.time()
            if first_byte_at is None:
                first_byte_at = now - t0
            last_byte_at = now - t0
            buffer += chunk
            while "\n\n" in buffer:
                event_block, buffer = buffer.split("\n\n", 1)
                current_event = None
                for line in event_block.split("\n"):
                    if line.startswith("event:"):
                        current_event = line[len("event:"):].strip()
                    elif line.startswith("data:"):
                        raw_data = line[len("data:"):].strip()
                        if raw_data == "[DONE]": continue
                        try:
                            ev = json.loads(raw_data)
                            for c in ev.get("choices", []):
                                d = c.get("delta", {})
                                if d.get("content"):
                                    full_answer += d["content"]
                            if ev.get("tool"):
                                tool_calls += 1
                                # Phase 4.2: 识别 LLM 调 wiki (SSE 里 tool=llm-wiki skill)
                                t_name = ev.get("tool", "")
                                if "llm-wiki" in t_name.lower() and "view" not in t_name.lower():
                                    llm_wiki_count += 1
                            if current_event == "chart" and chart_event is None:
                                chart_event = ev
                            elif current_event == "response" and response_event is None:
                                response_event = ev
                        except: pass

            result["elapsed"] = round(time.time() - t0, 2)
            result["ttfb"] = round(first_byte_at or 0, 2)  # Time To First Byte
            result["sse_duration"] = round((last_byte_at or 0) - (first_byte_at or 0), 2)

        # chart 抓取
        chart_cfg = None
        chart_src = None
        if chart_event and isinstance(chart_event.get("config"), dict):
            chart_cfg = chart_event["config"]
            chart_src = "event_chart"
        elif response_event and isinstance(response_event.get("chart_config"), dict):
            chart_cfg = response_event["chart_config"]
            chart_src = "response_payload"
        result["has_chart"] = chart_cfg is not None
        result["chart_type"] = chart_cfg.get("type") if chart_cfg else None
        result["chart_source"] = chart_src or "none"

        result["answer_len"] = len(full_answer)
        result["tool_calls"] = tool_calls
        result["trace_id"] = response_event.get("trace_id") if response_event else None
        # Phase 4.2: 调用链统计 (从 SSE 抓)
        result["llm_wiki_count"] = llm_wiki_count
        # agent_wiki_count 从 server log 读 (server-side 调用不出现在 SSE)
        # 暂留 0, 跑完由外部脚本从 log 统计
        result["agent_wiki_count"] = 0
        return result
    except Exception as e:
        result["err"] = str(e)[:100]
        result["elapsed"] = round(time.time() - t0, 2)
        return result


def phase_stats(phase_name, results):
    """单个 phase 的统计"""
    n = len(results)
    errs = [r for r in results if "err" in r]
    ok = n - len(errs)
    chart_ok = sum(1 for r in results if r.get("has_chart"))
    chart_expected = sum(1 for r in results if r.get("expect_chart"))
    chart_correct = sum(1 for r in ok_only(results) if r.get("has_chart") == r.get("expect_chart"))
    zero_tool_ok = sum(1 for r in ok_only(results) if r.get("expect_tool_calls_zero") and r.get("tool_calls", 1) == 0)
    zero_tool_total = sum(1 for r in ok_only(results) if r.get("expect_tool_calls_zero"))
    # Phase 4.2: 调用链统计
    llm_wiki_total = sum(r.get("llm_wiki_count", 0) for r in ok_only(results))
    agent_wiki_total = sum(r.get("agent_wiki_count", 0) for r in ok_only(results))
    llm_wiki_zero = sum(1 for r in ok_only(results) if r.get("llm_wiki_count", 1) == 0)
    agent_wiki_hit = sum(1 for r in ok_only(results) if r.get("agent_wiki_count", 0) > 0)
    ans_lens = [r.get("answer_len", 0) for r in ok_only(results)]
    elapsed = [r.get("elapsed", 0) for r in ok_only(results)]

    return {
        "phase": phase_name,
        "total": n,
        "success": ok,
        "errors": len(errs),
        "chart_ok": chart_ok,
        "chart_expected": chart_expected,
        "chart_correct": chart_correct,
        "zero_tool_ok": zero_tool_ok,
        "zero_tool_total": zero_tool_total,
        # Phase 4.2: 调用链
        "agent_wiki_total": agent_wiki_total,
        "agent_wiki_hit": agent_wiki_hit,
        "llm_wiki_total": llm_wiki_total,
        "llm_wiki_zero": llm_wiki_zero,
        "answer_len_avg": round(sum(ans_lens) / len(ans_lens), 0) if ans_lens else 0,
        "elapsed_avg": round(sum(elapsed) / len(elapsed), 1) if elapsed else 0,
        "elapsed_max": round(max(elapsed), 1) if elapsed else 0,
        "elapsed_p95": round(sorted(elapsed)[int(len(elapsed) * 0.95)], 1) if len(elapsed) >= 5 else 0,
    }


def ok_only(results):
    """只返回没 error 的"""
    return [r for r in results if "err" not in r]


def check_gates(phase_stats_list, gates):
    """检查 regression gates (Phase 4.2 加调用链 gate)"""
    failures = []
    # database_query gates
    a = next((s for s in phase_stats_list if "A" in s["phase"]), None)
    if a:
        rate = a["success"] / a["total"] if a["total"] > 0 else 0
        if rate < gates["database_query_success_min"]:
            failures.append(f"Phase A success {rate:.1%} < {gates['database_query_success_min']:.0%}")
        if a["elapsed_avg"] > gates["avg_elapsed_max_seconds"]:
            failures.append(f"Phase A avg elapsed {a['elapsed_avg']}s > {gates['avg_elapsed_max_seconds']}s")
        # Phase 4.2: database_query 必须 LLM 不调 wiki (0 次)
        if a["llm_wiki_total"] > 0:
            failures.append(f"Phase A llm_wiki {a['llm_wiki_total']}次 (应=0, agent 应接管)")
        # database_query 必须 agent 调过 wiki (至少 1 题)
        if a["agent_wiki_hit"] == 0:
            failures.append(f"Phase A agent_wiki 0题命中 (期望≥1题用 raw API semantic)")
    # safety_knowledge
    b = next((s for s in phase_stats_list if "B" in s["phase"]), None)
    if b:
        rate = b["success"] / b["total"] if b["total"] > 0 else 0
        if rate < gates["safety_knowledge_success_min"]:
            failures.append(f"Phase B success {rate:.1%} < {gates['safety_knowledge_success_min']:.0%}")
        # safety_knowledge 允许 LLM 调 wiki (符合预期)
    # mixed
    c = next((s for s in phase_stats_list if "C" in s["phase"]), None)
    if c:
        rate = c["success"] / c["total"] if c["total"] > 0 else 0
        if rate < gates["mixed_success_min"]:
            failures.append(f"Phase C success {rate:.1%} < {gates['mixed_success_min']:.0%}")
    # chart overall
    total_chart_expected = sum(s["chart_expected"] for s in phase_stats_list)
    total_chart_ok = sum(s["chart_ok"] for s in phase_stats_list)
    if total_chart_expected > 0:
        chart_rate = total_chart_ok / total_chart_expected
        if chart_rate < gates["chart_success_min"]:
            failures.append(f"Chart success {chart_rate:.1%} < {gates['chart_success_min']:.0%}")
    return failures


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=["A", "B", "C"], help="只跑某个 phase")
    parser.add_argument("--quick", action="store_true", help="只跑 Phase A")
    parser.add_argument("--update-baseline", action="store_true", help="更新 expected.json 基线")
    args = parser.parse_args()

    config = load_questions()
    gates = config.get("gates", {})

    # 决定跑哪些 phase
    if args.quick:
        phases = [p for p in config["phases"] if "A" in p["name"]]
    elif args.phase:
        phases = [p for p in config["phases"] if args.phase in p["name"]]
    else:
        phases = config["phases"]

    print(f"=== Hermes Regression Test ===")
    print(f"API: {API_BASE}")
    print(f"Phases: {len(phases)}")
    print(f"Total questions: {sum(len(p['questions']) for p in phases)}")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    all_stats = []
    all_results = []
    for phase in phases:
        print(f"\n--- {phase['name']} ({len(phase['questions'])} 题) ---")
        results = []
        for i, q in enumerate(phase["questions"], 1):
            r = run_one(q, max_wait=80)
            if "err" in r:
                print(f"  [{i:2}/{len(phase['questions'])}] ❌ {r['err'][:50]}  | {q['text'][:30]}")
            else:
                chart_status = "✅" if r["has_chart"] == r["expect_chart"] else "❌"
                print(f"  [{i:2}/{len(phase['questions'])}] {chart_status} chart={r['has_chart']}({r['chart_type']}) tools={r['tool_calls']} elapsed={r['elapsed']}s ans={r['answer_len']}  | {q['text'][:30]}")
            results.append(r)
            all_results.append({"phase": phase["name"], **r})

        stats = phase_stats(phase["name"], results)
        all_stats.append(stats)

    # 汇总
    print(f"\n{'='*60}")
    print(f"REGRESSION SUMMARY")
    print(f"{'='*60}")
    for s in all_stats:
        print(f"\n{s['phase']}:")
        print(f"  成功率: {s['success']}/{s['total']} ({s['errors']} errors)")
        print(f"  chart: {s['chart_ok']}/{s['chart_expected']} (正确: {s['chart_correct']})")
        print(f"  tool=0: {s['zero_tool_ok']}/{s['zero_tool_total']}")
        # Phase 4.2: 调用链
        print(f"  [调用链] agent_wiki: {s['agent_wiki_total']}次 ({s['agent_wiki_hit']}题命中), llm_wiki: {s['llm_wiki_total']}次 ({s['llm_wiki_zero']}题为0)")
        print(f"  answer avg: {s['answer_len_avg']} chars")
        print(f"  耗时: avg={s['elapsed_avg']}s, P95={s['elapsed_p95']}s, max={s['elapsed_max']}s")

    # Gates
    failures = check_gates(all_stats, gates)
    print(f"\n{'='*60}")
    print(f"REGRESSION GATES")
    print(f"{'='*60}")
    if failures:
        for f in failures:
            print(f"  ❌ {f}")
    else:
        print(f"  ✅ All gates passed")

    # 保存结果
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output = {
        "timestamp": timestamp,
        "api_base": API_BASE,
        "stats": all_stats,
        "results": all_results,
        "gates_passed": len(failures) == 0,
        "gate_failures": failures,
    }
    latest_path = RESULTS_DIR / "latest.json"
    with open(latest_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n  结果: {latest_path}")

    # history append
    history_path = RESULTS_DIR / "history.jsonl"
    with open(history_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(output, ensure_ascii=False) + "\n")

    if args.update_baseline:
        expected_path = REGRESSION_DIR / "expected.json"
        with open(expected_path, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"  📌 基线已更新: {expected_path}")

    return 0 if len(failures) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())