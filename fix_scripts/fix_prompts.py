path = '/data/lvm_data_48T/wyuz/ai-document-review/app/api/services/lc_pipeline.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# === Fix 1: IssueTypeLiteral ===
old_literal = 'IssueTypeLiteral = Literal["Grammar & Spelling", "Definitive Language"]'
new_literal = 'IssueTypeLiteral = Literal["作业级别未标注", "气体分析不合格", "安全措施不完整", "审批签字缺失", "作业时间不合规", "人员资质不符", "信息冗余或矛盾", "其他不合规项"]'
if old_literal in content:
    content = content.replace(old_literal, new_literal)
    print("Fix 1: Updated IssueTypeLiteral")
else:
    print("Fix 1: SKIP - IssueTypeLiteral already changed or not found")

# === Fix 2: SYSTEM_PROMPT ===
old_prompt_start = 'SYSTEM_PROMPT = """你是专业的特殊作业票合规审核专家，严格依据 GB 30871-2022《危险化学品企业特殊作业安全规范》进行审核。'
old_prompt_end = '重要：original_text字段必须是从输入文本中逐字引用的原文片段（用于PDF精确定位高亮），不能改写或概括。text字段则是给用户看的问题描述。使用段落索引（如 [0], [1], ...）。按JSON格式输出。若全合规返回空列表。\n"""'

import re
prompt_pattern = r'SYSTEM_PROMPT = """[\s\S]*?"""'
prompt_match = re.search(prompt_pattern, content)
if prompt_match:
    new_prompt = '''SYSTEM_PROMPT = """你是专业的特殊作业票合规审核专家，严格依据 GB 30871-2022《危险化学品企业特殊作业安全规范》进行审核。

请尽可能多地找出所有不合规项，每发现一个问题就报告一条，不要遗漏。

重点审核项（包括但不限于）：
1. 气体分析：超标误判合格（LEL≥4%时≤0.5%，LEL<4%时≤0.2%；氢气≤0.5%），分析时间超30分钟（第5.3.2/5.3.3条）
2. 监护人：是否兼任动火人/审批人（第4.6条）
3. 安全措施：确认栏选'否'的项是否影响安全，气瓶间距、接地、置换等
4. 作业级别：是否勾选，是否与风险匹配
5. 人员信息：名单重复、证件错误
6. 审批流程：签字齐全性、时间逻辑、同一人签不同层级
7. 影像资料：特级动火是否配摄录设备（第5.2.11条）
8. 信息矛盾：作业方式与安全措施矛盾等
9. 以及GB 30871-2022的任何其他违规项

问题类型：
- 气体分析不合格
- 安全措施未落实
- 作业级别未标注
- 监护人角色冲突
- 审批签字缺失
- 作业时间不合规
- 人员资质不符
- 信息冗余或矛盾
- 其他不合规项

重要：original_text字段必须是从输入文本中逐字引用的原文片段（用于PDF精确定位高亮），不能改写或概括。text字段则是给用户看的问题描述。使用段落索引（如 [0], [1], ...）。按JSON格式输出。若全合规返回空列表。
"""'''
    content = content[:prompt_match.start()] + new_prompt + content[prompt_match.end():]
    print("Fix 2: Updated SYSTEM_PROMPT")
else:
    print("Fix 2: FAILED - could not find SYSTEM_PROMPT")

# === Fix 3: _build_system_prompt issue_types ===
old_issue_types = '''    issue_types = [
        "- 作业票编号缺失或错误",
        "- 作业类别不匹配",
        "- 作业内容描述不完整",
        "- 危险有害因素辨识不全",
        "- 安全措施缺失或不完善",
        "- 作业时间不合规",
        "- 审批签字缺失",
        "- 人员资质不符合要求",
        "- 影像资料缺失",
        "- 信息冗余或矛盾",
        "- 其他不合规项",
    ]'''

new_issue_types = '''    issue_types = [
        "- 气体分析不合格",
        "- 安全措施未落实",
        "- 作业级别未标注",
        "- 监护人角色冲突",
        "- 审批签字缺失",
        "- 作业时间不合规",
        "- 人员资质不符",
        "- 信息冗余或矛盾",
        "- 其他不合规项",
    ]'''

if old_issue_types in content:
    content = content.replace(old_issue_types, new_issue_types)
    print("Fix 3: Updated issue_types in _build_system_prompt")
else:
    print("Fix 3: SKIP - issue_types already changed or not found")

# === Fix 4: _build_guidance ===
guidance_pattern = r'def _build_guidance\([\s\S]*?\n    return "\\n"\.join\(lines\)\n'
guidance_match = re.search(guidance_pattern, content)
if guidance_match:
    new_guidance = '''def _build_guidance(custom_rules: List[ReviewRule] | None = None, rule_documents: List[RuleDocument] | None = None) -> str:
    """Build guidance section for GB 30871-2022 work ticket review."""
    lines = [
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
    ]

    if rule_documents:
        lines.append("")
        lines.append("参考标准文件：")
        for rdoc in rule_documents:
            snippet = (rdoc.extracted_text or "")[:settings.rule_context_max_chars]
            lines.append(f"- [{rdoc.name}]: {snippet}")

    if custom_rules:
        lines.append("")
        lines.append("自定义规则：")
        for rule in custom_rules:
            guidance = f"- {rule.name}: {rule.description}"
            if rule.examples:
                examples_str = "; ".join([f'"{ex.text}"' for ex in rule.examples[:3]])
                guidance += f" 示例: {examples_str}"
            lines.append(guidance)

    return "\\n".join(lines)
'''
    content = content[:guidance_match.start()] + new_guidance + content[guidance_match.end():]
    print("Fix 4: Updated _build_guidance")
else:
    print("Fix 4: FAILED - could not find _build_guidance")

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

import py_compile
try:
    py_compile.compile(path, doraise=True)
    print("Syntax check PASSED!")
except py_compile.PyCompileError as e:
    print(f"Syntax check FAILED: {e}")