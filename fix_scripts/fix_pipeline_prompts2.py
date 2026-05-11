"""
fix_pipeline_prompts2.py
修复 lc_pipeline.py 中 _DEFAULT_FOCUS 和 _build_system_prompt 的语法问题。
将转义字符正确处理。
"""

import re
from pathlib import Path

TARGET = Path("/data/lvm_data_48T/wyuz/ai-document-review/app/api/services/lc_pipeline.py")


def main():
    text = TARGET.read_text(encoding="utf-8")

    # Find everything from _DEFAULT_FOCUS to end of _build_system_prompt
    # (up to the blank line before _build_guidance)
    pattern = r'# Default review focus.*?(?=\ndef _build_guidance)'
    match = re.search(pattern, text, re.DOTALL)
    if not match:
        print("ERROR: Could not find the section to replace")
        return

    replacement = r'''# Default review focus items (used when no rules with prompts are selected)
_DEFAULT_FOCUS_LINES = [
    "1. 气体分析：超标误判合格（第5.3.2条）",
    "2. 监护人：是否兼做与监护无关的工作（第4.10条）",
    "3. 安全措施：确认栏选'否'的项是否影响安全。动火方式含气焊/气割时气瓶措施必须确认'是'，含电焊时接地措施必须确认'是'（第5.2条）",
    "4. 作业级别：是否勾选，是否与风险匹配（第5.1条）",
    "5. 人员信息：仔细检查名单中是否有重复姓名，证件号是否有错",
    "6. 审批流程：签字齐全性、时间逻辑（第4.6条）",
    "7. 以及GB 30871-2022的任何其他违规项",
]

_DEFAULT_ISSUE_TYPES = [
    "- 气体分析不合格",
    "- 安全措施未落实",
    "- 作业级别未标注",
    "- 监护人角色冲突",
    "- 审批签字缺失",
    "- 作业时间不合规",
    "- 信息冗余或矛盾",
    "- 其他不合规项",
]


def _build_system_prompt(custom_rules: List[ReviewRule] | None = None, rule_documents: List[RuleDocument] | None = None) -> str:
    """Build system prompt with custom rules and rule documents.

    If any selected custom_rules have a prompt field, use their prompts
    to build the review focus section. Otherwise fall back to defaults.
    """
    issue_types = list(_DEFAULT_ISSUE_TYPES)

    if custom_rules:
        for rule in custom_rules:
            if f"- {rule.name}" not in issue_types:
                issue_types.append(f"- {rule.name}")

    # Build review focus section from rules' prompts
    if custom_rules:
        prompt_rules = [r for r in custom_rules if r.prompt]
        if prompt_rules:
            focus_lines = [f"{i}. {r.prompt}" for i, r in enumerate(prompt_rules, 1)]
        else:
            focus_lines = list(_DEFAULT_FOCUS_LINES)
    else:
        focus_lines = list(_DEFAULT_FOCUS_LINES)

    focus_section = "\n".join(focus_lines)

    # Build rule document reference section
    rule_doc_section = ""
    if rule_documents:
        doc_lines = []
        for rdoc in rule_documents:
            snippet = (rdoc.extracted_text or "")[:settings.rule_context_max_chars]
            doc_lines.append(f"- [{rdoc.name}]: {snippet}")
        rule_doc_section = "\n\n参考标准文件：\n" + "\n".join(doc_lines)

    issues_str = chr(10).join(issue_types)
    parts = [
        "你是专业的特殊作业票合规审核专家，严格依据 GB 30871-2022《危险化学品企业特殊作业安全规范》进行审核。",
        "",
        "请尽可能多地找出所有不合规项，每发现一个问题就报告一条，不要遗漏。",
        "",
        "重点审核项（包括但不限于）：",
        focus_section,
        "",
        "问题类型包括但不限于：",
        issues_str,
        rule_doc_section,
        "",
        "输出要求：",
        "- text字段：简要描述不合规的具体内容（给用户看的问题说明）",
        "- original_text字段（极其重要）：必须从输入文本中逐字引用存在问题的原文片段！要与输入中的文字完全一致，不能改写、不能概括。这个字段用于在PDF上精确定位高亮位置。",
        '- explanation字段：引用GB 30871-2022中违反的具体条款编号（如"第5.2.1条"）',
        "- suggested_fix字段：提出具体的整改建议",
        "- 若所有内容均合规，返回空的 issues 列表",
        "",
        "使用输入中提供的段落索引（如 [0], [1], ...）。",
        "按照要求的 JSON 格式输出结果。",
    ]
    return "\n".join(p for p in parts if p is not None) + "\n"


'''

    text = text[:match.start()] + replacement + text[match.end():]

    # Clean up extra blank lines
    text = re.sub(r'\n{4,}', '\n\n\n', text)

    TARGET.write_text(text, encoding="utf-8")
    print(f"SUCCESS: Patched _build_system_prompt in {TARGET}")


if __name__ == "__main__":
    main()
