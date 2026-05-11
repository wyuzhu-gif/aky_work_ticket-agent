import re

path = '/data/lvm_data_48T/wyuz/ai-document-review/app/api/services/lc_pipeline.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Fix 1: Update SYSTEM_PROMPT to add cross-check items
old_prompt = '''重点审核项（包括但不限于）：
1. 气体分析：超标误判合格（LEL≥4%时≤0.5%，LEL<4%时≤0.2%；氢气≤0.5%），分析时间超30分钟（第5.3.2/5.3.3条）
2. 监护人：是否兼任动火人/审批人（第4.6条）
3. 安全措施：确认栏选'否'的项是否影响安全，气瓶间距、接地、置换等
4. 作业级别：是否勾选，是否与风险匹配
5. 人员信息：名单重复、证件错误
6. 审批流程：签字齐全性、时间逻辑、同一人签不同层级
7. 影像资料：特级动火是否配摄录设备（第5.2.11条）
8. 信息矛盾：作业方式与安全措施矛盾等
9. 以及GB 30871-2022的任何其他违规项'''

new_prompt = '''重点审核项（包括但不限于）：
1. 气体分析：超标误判合格（LEL≥4%时≤0.5%，LEL<4%时≤0.2%；氢气≤0.5%），分析时间超30分钟（第5.3.2/5.3.3条）
2. 监护人：是否兼任动火人/审批人（第4.6条）
3. 安全措施：确认栏选'否'的项是否影响安全，气瓶间距、接地、置换等。特别要注意：动火方式与安全措施是否矛盾（如动火方式含气焊/气割，但气瓶安全措施确认'否'）
4. 作业级别：是否勾选，是否与风险匹配
5. 人员信息：名单重复、证件错误。特别检查动火人名单中是否有重复姓名
6. 审批流程：签字齐全性、时间逻辑、同一人签不同层级
7. 影像资料：特级动火是否配摄录设备（第5.2.11条）
8. 信息矛盾：作业方式与安全措施矛盾等
9. 以及GB 30871-2022的任何其他违规项

交叉检查要求：
- 对比动火方式与安全措施确认项：如果动火方式包含气焊/气割，对应气瓶安全措施必须确认；如果包含电焊，对应电焊机接地措施必须确认
- 检查所有人员名单（动火人、监护人、审批人、分析人）中是否有重复出现的姓名'''

if old_prompt in content:
    content = content.replace(old_prompt, new_prompt)
    print("Fix 1: Updated SYSTEM_PROMPT with cross-check items")
else:
    print("Fix 1: SKIP - SYSTEM_PROMPT already changed or not found")

# Fix 2: Update _build_guidance with the same additions
old_guidance_lines = '''    lines = [
        "重点审核项（包括但不限于）：",
        "1. 气体分析：超标误判合格（LEL≥4%时≤0.5%，LEL<4%时≤0.2%；氢气≤0.5%），分析时间超30分钟（第5.3.2/5.3.3条）",
        "2. 监护人：是否兼任动火人/审批人（第4.6条）",
        "3. 安全措施：确认栏选'否'的项是否影响安全，气瓶间距、接地、置换等",
        "4. 作业级别：是否勾选，是否与风险匹配",
        "5. 人员信息：名单重复、证件错误",
        "6. 审批流程：签字齐全性、时间逻辑、同一人签不同层级",
        "7. 影像资料：特级动火是否配摄录设备（第5.2.11条）",
        "8. 信息矛盾：作业方式与安全措施矛盾等",
        "9. 以及GB 30871-2022的任何其他违规项",
    ]'''

new_guidance_lines = '''    lines = [
        "重点审核项（包括但不限于）：",
        "1. 气体分析：超标误判合格（LEL≥4%时≤0.5%，LEL<4%时≤0.2%；氢气≤0.5%），分析时间超30分钟（第5.3.2/5.3.3条）",
        "2. 监护人：是否兼任动火人/审批人（第4.6条）",
        "3. 安全措施：确认栏选'否'的项是否影响安全。交叉检查：动火方式含气焊/气割时气瓶措施必须确认'是'，含电焊时接地措施必须确认'是'",
        "4. 作业级别：是否勾选，是否与风险匹配",
        "5. 人员信息：仔细检查动火人名单中是否有重复姓名，证件号是否有错",
        "6. 审批流程：签字齐全性、时间逻辑、同一人签不同层级",
        "7. 影像资料：特级动火是否配摄录设备（第5.2.11条）",
        "8. 信息矛盾：作业方式与安全措施矛盾等",
        "9. 以及GB 30871-2022的任何其他违规项",
    ]'''

if old_guidance_lines in content:
    content = content.replace(old_guidance_lines, new_guidance_lines)
    print("Fix 2: Updated _build_guidance with cross-check items")
else:
    print("Fix 2: SKIP - _build_guidance already changed or not found")

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

import py_compile
try:
    py_compile.compile(path, doraise=True)
    print("Syntax check PASSED!")
except py_compile.PyCompileError as e:
    print(f"Syntax check FAILED: {e}")