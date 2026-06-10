"""
Unit tests for two-step resolve 拦截逻辑.
跑: cd api && source venv/bin/activate && python tests/test_two_step_resolve.py
"""
import sys
from pathlib import Path

# 跳过 @tool 装饰器, 直接 import 函数
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
# 避开 import 整个 smart_query 触发的 vanna 链, 只读函数定义
import importlib.util
spec = importlib.util.spec_from_file_location(
    "database_tools_test",
    Path(__file__).resolve().parent.parent / "smart_query" / "tools" / "database_tools.py"
)

# 我们只测纯函数, 不实际跑 @tool 装饰后的 execute_sql (那要数据库)
# 所以直接 exec 模块, 然后只 import 我们要的函数
import re
import threading
from typing import Optional

# 复制我们写的关键函数 (避免 import 时初始化 vanna)
ORAL_FIELDS = {
    'company_name', 'task_part', 'homework_content', 'ticket_position',
    'name_of_guardian', 'task_supervisor', 'construction_workers_name',
}
_oral_cache = threading.local()

def _get_oral_cache():
    if not hasattr(_oral_cache, 'data'):
        _oral_cache.data = {}
    return _oral_cache.data

def _clear_oral_cache():
    if hasattr(_oral_cache, 'data'):
        _oral_cache.data = {}

def _is_distinct_resolve_sql(sql):
    sql_l = sql.lower()
    if 'select distinct' not in sql_l:
        return False
    if not any(op in sql_l for op in (' like ', ' instr(', ' regexp ', ' rlike ')):
        return False
    return True

def _extract_oral_field_filters(sql):
    """从 SQL 提取口语化字段的 WHERE 过滤 (field_name, op, value).

    只扫顶层 WHERE, 不进 CTE/子查询. 容忍表别名.
    跳过 SELECT DISTINCT 反查本身 (那是合法操作).
    """
    # 反查 SQL 自身不视为"过滤", 放行
    if _is_distinct_resolve_sql(sql):
        return []
    sql_l = sql.lower()
    hits = []
    for f in ORAL_FIELDS:
        # 匹配 field_name (=|<>|!=|LIKE|REGEXP|RLIKE) 'value'
        # IN 操作符: field IN ('a', 'b', 'c') - 取第一个作为代表
        # 容忍任意空白
        # 普通形式: =/LIKE/REGEXP/RLIKE
        pattern_simple = rf"\b{f}\b\s*(=|<>|!=|like|regexp|rlike)\s*(['\"])([^'\"]+)\2"
        for m in re.finditer(pattern_simple, sql_l):
            op = m.group(1).upper()
            value = m.group(3)
            hits.append((f, op, value))
        # IN 形式: field IN ('a', 'b', 'c')
        pattern_in = rf"\b{f}\b\s*\bin\b\s*\(([^)]+)\)"
        for m in re.finditer(pattern_in, sql_l):
            in_list = m.group(1)
            # 提取第一个字符串值
            vm = re.search(r"['\"]([^'\"]+)['\"]", in_list)
            if vm:
                hits.append((f, 'IN', vm.group(1)))
    return hits

def _check_oral_field_resolved(sql):
    filters = _extract_oral_field_filters(sql)
    if not filters:
        return None
    cache = _get_oral_cache()
    for field, op, value in filters:
        cached = cache.get(field, [])
        if not cached:
            return f"❌ 拦截: {field} 未反查"
        if op == '=' and not any(value in c or c in value for c in cached):
            return f"❌ 拦截: {field}={value} 不在 cache {cached}"
    return None

# 跑 case
def run(name, sql, expect_intercepted=False, expect_filters=None, setup_cache=None):
    _clear_oral_cache()
    if setup_cache:
        for k, v in setup_cache.items():
            _get_oral_cache()[k] = v

    actual = _extract_oral_field_filters(sql)
    actual_intercept = _check_oral_field_resolved(sql)

    is_intercepted = actual_intercept is not None
    if expect_filters is not None:
        if sorted([(f, v) for f, _, v in actual]) != sorted(expect_filters):
            print(f"❌ {name}: filters 不匹配")
            print(f"  期望: {expect_filters}")
            print(f"  实际: {actual}")
            return False
    if is_intercepted != expect_intercepted:
        print(f"❌ {name}: 拦截判断错")
        print(f"  期望拦截: {expect_intercepted}, 实际拦截: {is_intercepted}")
        print(f"  拦截信息: {actual_intercept}")
        return False
    print(f"✅ {name}")
    return True

# Case 1: 口语化字段 + 等值过滤 + 没反查 → 拦截
r1 = run("1. WHERE company_name = '博航染料企业' (无反查)",
         "SELECT * FROM special_task_view WHERE company_name = '博航染料企业'",
         expect_intercepted=True,
         expect_filters=[('company_name', '博航染料企业')])

# Case 2: 口语化字段 + LIKE + 没反查 → 拦截 (LLM 应该先 DISTINCT)
r2 = run("2. WHERE company_name LIKE '博航染料企业' (无反查, 等值 LIKE 错)",
         "SELECT * FROM special_task_view WHERE company_name LIKE '博航染料企业'",
         expect_intercepted=True,
         expect_filters=[('company_name', '博航染料企业')])

# Case 3: 口语化字段 + 等值过滤 + 已反查 + value 在 cache → 通过
r3 = run("3. WHERE company_name = '博航染料化工有限公司' (反查后用真实名)",
         "SELECT * FROM special_task_view WHERE company_name = '博航染料化工有限公司'",
         expect_intercepted=False,
         expect_filters=[('company_name', '博航染料化工有限公司')],
         setup_cache={'company_name': ['博航染料化工有限公司', '博航新材料']})

# Case 4: 口语化字段 + 等值过滤 + 已反查 + value 不在 cache → 拦截
r4 = run("4. WHERE company_name = '完全不存在的公司' (反查过但 value 错)",
         "SELECT * FROM special_task_view WHERE company_name = '完全不存在的公司'",
         expect_intercepted=True,
         expect_filters=[('company_name', '完全不存在的公司')],
         setup_cache={'company_name': ['博航染料化工有限公司', '博航新材料']})

# Case 5: 非口语化字段 (top_level) → 放行
r5 = run("5. WHERE top_level = 1 (非口语化字段, 放行)",
         "SELECT * FROM special_task_view WHERE top_level = 1",
         expect_intercepted=False,
         expect_filters=[])

# Case 6: 多字段同时过滤 → 都得查过
r6 = run("6. WHERE company_name + task_part (只反查 1 个, 拦截)",
         "SELECT * FROM special_task_view WHERE company_name = '博航染料化工有限公司' AND task_part = '研发部'",
         expect_intercepted=True,
         expect_filters=[('company_name', '博航染料化工有限公司'), ('task_part', '研发部')],
         setup_cache={'company_name': ['博航染料化工有限公司']})  # task_part 没反查

# Case 7: LIKE '%子串%' (已经是模糊) → 即便 value 是真实名子串也通过
r7 = run("7. WHERE company_name LIKE '%博航%' (LIKE 模糊, 放行)",
         "SELECT * FROM special_task_view WHERE company_name LIKE '%博航%'",
         expect_intercepted=False,
         expect_filters=[('company_name', '%博航%')],
         setup_cache={'company_name': ['博航染料化工有限公司']})

# Case 8: 数字编码字段 (task_part = '3555') → 拦截 (没反查)
r8 = run("8. WHERE task_part = '3555' (没反查, 拦截)",
         "SELECT * FROM special_task_view WHERE task_part = '3555'",
         expect_intercepted=True,
         expect_filters=[('task_part', '3555')])

# Case 9: 反查 SQL 本身 (SELECT DISTINCT) → 不会被拦截 (没过滤, 放行)
r9 = run("9. 反查 SQL (SELECT DISTINCT, 放行不被拦截)",
         "SELECT DISTINCT company_name, COUNT(*) AS n FROM special_task_view WHERE company_name LIKE '%博航%' GROUP BY company_name ORDER BY n DESC LIMIT 5",
         expect_intercepted=False,
         expect_filters=[])

# Case 10: 没用口语化字段 (纯 top_level) → 放行
r10 = run("10. 纯 top_level 过滤 (放行)",
         "SELECT sub_level, COUNT(*) FROM special_task_view WHERE top_level = 5 AND YEAR(actual_start) = 2026 GROUP BY sub_level",
         expect_intercepted=False,
         expect_filters=[])

# Case 11: IN 操作符 (口语化字段) → 拦截
r11 = run("11. WHERE company_name IN ('X') (没反查, 拦截)",
         "SELECT * FROM special_task_view WHERE company_name IN ('博航染料企业')",
         expect_intercepted=True,
         expect_filters=[('company_name', '博航染料企业')])

# Case 12: homework_content 模糊 → 拦截
r12 = run("12. WHERE homework_content = '焊接' (没反查, 拦截)",
         "SELECT * FROM special_task_view WHERE homework_content = '焊接'",
         expect_intercepted=True,
         expect_filters=[('homework_content', '焊接')])

results = [r1, r2, r3, r4, r5, r6, r7, r8, r9, r10, r11, r12]
print()
print(f"通过 {sum(results)}/{len(results)}")
if all(results):
    print("✅ 全部通过")
else:
    print("❌ 有失败")
    sys.exit(1)
