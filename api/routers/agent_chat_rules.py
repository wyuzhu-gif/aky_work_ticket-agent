"""
data_rules.py - 规则化分析 raw API 返回的 rows, 提取 topics (需查的法规主题)

设计原则 (2026-06-25 用户拍板):
- 完全确定性, 无 LLM
- 速度毫秒级
- 未来可扩展 (case_search, enterprise_sop, risk_db)

输入: rows (list of dict) + columns
输出: topics (list of str) + risk_flags (list of str) + metadata (dict)
"""
from typing import Any


# 主题到法规/工具的映射
TOPIC_REGISTRY = {
    # 业务主题 -> 需要查的法规 (从 llm-wiki)
    "动火": ["GB30871", "GB50016"],
    "消防": ["GB50016", "GB35181"],
    "受限空间": ["GB30871"],
    "高处作业": ["GB30871"],
    "临时用电": ["GB30871", "GB50054"],
    "动土": ["GB30871"],
    "断路": ["GB30871"],
    "盲板抽堵": ["GB30871"],
    "设备检维修": ["GB30871"],
    "粉尘": ["GB15577"],
    "危险化学品": ["GB18218", "GB15603"],
    "重大危险源": ["GB18218"],
    "重大隐患": ["AQ3067"],
    "应急": ["GB30077"],
    "事故": ["GB6441"],
    # 基础管理类 (2026-06-25 补充)
    "安全": ["GB/T 33000"],          # 企业安全生产标准化
    "设备": ["GB30871", "GB/T 33000"],
    "电气": ["GB50016", "GB50054"],  # 电气火灾 + 电气装置
    "工艺": ["AQ3034"],              # 化工工艺安全
    "仪表": ["AQ3034"],              # 仪表与自控
    "总图": ["GB50016"],              # 厂区布局/防火间距
    "安全培训": ["GB/T 33000"],
    "责任制": ["GB/T 33000"],
}


def _normalize_key(s: str) -> str:
    """统一 key: 去除空格/标点, lowercase"""
    return s.replace(" ", "").replace("-", "").replace("_", "").lower()


# 预 normalize 映射表
_NORMALIZED_TOPIC = {_normalize_key(k): k for k in TOPIC_REGISTRY}


def _match_topic(value: str) -> str | None:
    """从 value 字符串匹配主题"""
    v_norm = _normalize_key(str(value))
    for nk, orig in _NORMALIZED_TOPIC.items():
        if nk in v_norm:
            return orig
    return None


def _has_column(rows: list, col: str) -> bool:
    """rows 是否有指定列"""
    if not rows: return False
    return col in rows[0]


def _is_high_risk_danger_level(value: Any) -> bool:
    """隐患等级判断: 重大=20 / 重大隐患关键词"""
    s = str(value)
    if s in ("20", "重大", "重大隐患"):
        return True
    return "重大" in s


def analyze_rows(rows: list, columns: list | None = None) -> dict:
    """
    分析 raw API 返回的 rows, 提取 topics + risk_flags + metadata

    返回: {
        "topics": ["动火", "消防", ...],  # 需要查 llm-wiki 的主题
        "risk_flags": ["有重大隐患", "连续增长", ...],  # 风险标记
        "metadata": {
            "row_count": int,
            "has_high_danger": bool,
            "dominant_topic": str | None,
            "topic_distribution": {"动火": 9, "消防": 18, ...},
            ...
        }
    }
    """
    topics: set[str] = set()
    risk_flags: list[str] = []
    metadata: dict = {
        "row_count": len(rows) if rows else 0,
        "has_high_danger": False,
        "dominant_topic": None,
        "topic_distribution": {},
    }

    if not rows:
        return {"topics": [], "risk_flags": [], "metadata": metadata}

    cols = columns or list(rows[0].keys())

    # 规则 1: 识别"类型列" (按列名猜)
    # 优先匹配: 隐患类型 / 作业类型 / 类型 / 类别 / 风险类型
    type_col = None
    for candidate in ["隐患类型", "作业类型", "类型", "类别", "风险类型", "topic", "category", "type"]:
        if candidate in cols:
            type_col = candidate
            break

    # 规则 2: 识别"数量列"
    count_col = None
    for candidate in ["数量", "count", "cnt", "总数", "频次"]:
        if candidate in cols:
            count_col = candidate
            break

    # 规则 3: 识别"等级/状态列"
    level_col = None
    for candidate in ["隐患等级", "等级", "danger_level", "风险等级", "level", "状态"]:
        if candidate in cols:
            level_col = candidate
            break

    # 规则 4: 识别"日期列"
    date_col = None
    for candidate in ["日期", "check_date", "发生日期", "整改日期", "date", "create_time"]:
        if candidate in cols:
            date_col = candidate
            break

    # ===== 主题提取 =====
    topic_dist: dict[str, float] = {}  # 主题 -> 累计数值
    if type_col and count_col:
        for r in rows:
            tval = r.get(type_col)
            cval = r.get(count_col, 0)
            topic = _match_topic(str(tval)) if tval else None
            if topic:
                topics.add(topic)
                # 累加数值 (如果数字)
                try:
                    topic_dist[topic] = topic_dist.get(topic, 0) + float(cval)
                except (TypeError, ValueError):
                    topic_dist[topic] = topic_dist.get(topic, 0) + 1
    elif type_col:
        # 只有类型列, 没有数量列 → 计数
        from collections import Counter
        type_counter = Counter(str(r.get(type_col, "")) for r in rows)
        for tval, cnt in type_counter.items():
            topic = _match_topic(tval) if tval else None
            if topic:
                topics.add(topic)
                topic_dist[topic] = topic_dist.get(topic, 0) + cnt

    # ===== 风险标志 =====
    # 重大隐患
    if level_col:
        for r in rows:
            if _is_high_risk_danger_level(r.get(level_col)):
                metadata["has_high_danger"] = True
                risk_flags.append("有重大隐患")
                break

    # 主导主题 (占比 > 50% 或单类最大)
    if topic_dist:
        dominant = max(topic_dist.items(), key=lambda x: x[1])
        metadata["dominant_topic"] = dominant[0]
        total = sum(topic_dist.values())
        if total > 0 and dominant[1] / total > 0.5:
            risk_flags.append(f"单一类型集中({dominant[0]}占{dominant[1]/total*100:.0f}%)")
        metadata["topic_distribution"] = topic_dist

    # 趋势: 只有日期 + 数量, 看是否连续增长
    if date_col and count_col and len(rows) >= 3:
        # 简单按时间排序, 看末尾 2-3 个点是否递增
        try:
            sorted_rows = sorted(rows, key=lambda r: str(r.get(date_col, "")))
            recent = sorted_rows[-3:]
            vals = []
            for r in recent:
                try:
                    vals.append(float(r.get(count_col, 0)))
                except (TypeError, ValueError):
                    pass
            if len(vals) >= 3 and vals[0] < vals[1] < vals[2]:
                risk_flags.append("连续增长趋势")
        except Exception:
            pass

    # 高频高发 (单类数量 > 总数 30%)
    if topic_dist:
        total = sum(topic_dist.values())
        if total > 0:
            for topic, cnt in topic_dist.items():
                if cnt / total > 0.3:
                    risk_flags.append(f"{topic}高发({cnt/total*100:.0f}%)")

    metadata["row_count"] = len(rows)
    metadata["topic_count"] = len(topics)
    metadata["risk_count"] = len(risk_flags)

    return {
        "topics": sorted(topics),
        "risk_flags": risk_flags,
        "metadata": metadata,
    }


def topics_to_wiki_queries(topics: list[str], question: str) -> list[str]:
    """
    把 topics 转换成 llm-wiki 搜索 query

    例: ["动火", "消防"] + "本月动火违规" -> ["动火作业安全要求", "消防安全管理"]
    """
    queries = []
    for t in topics:
        # 简单拼接: "<topic> + 安全要求/管理"
        queries.append(f"{t}作业安全要求")
    # 最多 2 个 query (避免 wiki 调用过慢)
    return queries[:2]


if __name__ == "__main__":
    # 单元测试
    test_rows_1 = [
        {"隐患类型": "消防", "数量": 18},
        {"隐患类型": "动火", "数量": 9},
        {"隐患类型": "其他", "数量": 1},
    ]
    result = analyze_rows(test_rows_1, ["隐患类型", "数量"])
    print("Test 1 (消防+动火):", result)
    # 期望: topics=['动火','消防'], dominant=消防(64%)

    test_rows_2 = [
        {"类型": "粉尘", "频次": 5},
        {"类型": "粉尘", "频次": 3},
    ]
    result = analyze_rows(test_rows_2, ["类型", "频次"])
    print("Test 2 (粉尘):", result)
    # 期望: topics=['粉尘'], dominant=粉尘(100%)

    test_rows_3 = [
        {"类型": "动火", "数量": 5, "隐患等级": "20"},
        {"类型": "受限空间", "数量": 3, "隐患等级": "10"},
    ]
    result = analyze_rows(test_rows_3, ["类型", "数量", "隐患等级"])
    print("Test 3 (动火+重大):", result)
    # 期望: topics=['动火','受限空间'], has_high_danger=True

    test_rows_4 = [
        {"日期": "2026-06-01", "数量": 5},
        {"日期": "2026-06-02", "数量": 7},
        {"日期": "2026-06-03", "数量": 9},
    ]
    result = analyze_rows(test_rows_4, ["日期", "数量"])
    print("Test 4 (连续增长):", result)
    # 期望: risk_flags=['连续增长趋势']