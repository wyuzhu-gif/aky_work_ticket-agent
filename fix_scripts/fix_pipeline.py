import re

path = '/data/lvm_data_48T/wyuz/ai-document-review/app/api/services/lc_pipeline.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

print("Searching for _build_system_prompt...")
start_pat = re.compile(r'^def _build_system_prompt\(', re.MULTILINE)
start_m = start_pat.search(content)
if start_m:
    print(f"Found _build_system_prompt at position {start_m.start()}")
    end_pat = re.compile(r'\n(?=def _build_guidance)', re.MULTILINE)
    end_m = end_pat.search(content, start_m.end())
    if end_m:
        print(f"Found end at position {end_m.start()}")

        new_func = r'''def _build_system_prompt(custom_rules: List[ReviewRule] | None = None, rule_documents: List[RuleDocument] | None = None) -> str:
    """Build system prompt with custom rules and rule documents."""
    issue_types = [
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
    ]

    if custom_rules:
        for rule in custom_rules:
            issue_types.append(f"- {rule.name}")

    rule_doc_section = ""
    if rule_documents:
        rule_doc_section = "\n\n参考标准文件：\n"
        for rdoc in rule_documents:
            snippet = (rdoc.extracted_text or "")[:settings.rule_context_max_chars]
            rule_doc_section += f"- [{rdoc.name}]: {snippet}\n"

    issues_str = chr(10).join(issue_types)
    return (
        "你是专业的特殊作业票合规审核专家，严格依据 GB 30871-2022《危险化学品企业特殊作业安全规范》进行审核。\n\n"
        "请尽可能多地找出所有不合规项，每发现一个问题就报告一条，不要遗漏。\n\n"
        "问题类型包括但不限于：\n"
        f"{issues_str}\n"
        f"{rule_doc_section}\n"
        "输出要求：\n"
        "- text字段：简要描述不合规的具体内容（给用户看的问题说明）\n"
        "- original_text字段（极其重要）：必须从输入文本中逐字引用存在问题的原文片段！要与输入中的文字完全一致，不能改写、不能概括。这个字段用于在PDF上精确定位高亮位置。\n"
        "- explanation字段：引用GB 30871-2022中违反的具体条款编号（如"第5.2.1条"）\n"
        "- suggested_fix字段：提出具体的整改建议\n"
        "- 若所有内容均合规，返回空的 issues 列表\n\n"
        "使用输入中提供的段落索引（如 [0], [1], ...）。\n"
        "按照要求的 JSON 格式输出结果。\n"
    )
'''
        content = content[:start_m.start()] + new_func + "\n" + content[end_m.start()+1:]
        print("Fix 1: Replaced _build_system_prompt")
    else:
        print("Fix 1: FAILED - could not find function end")
else:
    print("Fix 1: FAILED - could not find _build_system_prompt")

print("Searching for _build_guidance...")
start_pat2 = re.compile(r'^def _build_guidance\(', re.MULTILINE)
start_m2 = start_pat2.search(content)
if start_m2:
    print(f"Found _build_guidance at position {start_m2.start()}")
    end_pat2 = re.compile(r'\n(?=\nclass LangChainPipeline)', re.MULTILINE)
    end_m2 = end_pat2.search(content, start_m2.end())
    if end_m2:
        print(f"Found end at position {end_m2.start()}")

        new_guidance = r'''def _build_guidance(custom_rules: List[ReviewRule] | None = None, rule_documents: List[RuleDocument] | None = None) -> str:
    """Build guidance section for GB 30871-2022 work ticket review."""
    lines = [
        "审核指南（GB 30871-2022 特殊作业票合规审核）：",
        "",
        "请重点检查以下方面：",
        "1. 作业票基本信息：编号、作业类别、作业内容、作业地点",
        "2. 危险有害因素辨识是否完整",
        "3. 安全措施是否齐全且已落实",
        "4. 作业时间是否在有效期内",
        "5. 审批流程是否完整（申请、审核、批准签字）",
        "6. 作业人员资质是否符合要求",
        "7. 监护人是否指定且在岗",
        "8. 影像资料是否齐全",
        "",
        "注意：",
        "- 勾选框（口、□、○）属于表格格式，不是错误",
        "- 日期占位符（____年____月____日）属于模板格式，不是错误",
        "- 序号编号属于格式，不是错误",
        "- 仅报告真正的不合规项，不要报告格式问题",
        "",
        "如果不确定是否是错误，宁可不报告。",
    ]

    if custom_rules:
        lines.append("")
        lines.append("自定义规则：")
        for rule in custom_rules:
            guidance = f"- {rule.name}: {rule.description}"
            if rule.examples:
                examples_str = "; ".join([f'"{ex.text}"' for ex in rule.examples[:3]])
                guidance += f" 示例: {examples_str}"
            lines.append(guidance)

    return "\n".join(lines)
'''
        content = content[:start_m2.start()] + new_guidance + "\n" + content[end_m2.start()+1:]
        print("Fix 2: Replaced _build_guidance")
    else:
        print("Fix 2: FAILED - could not find function end")
else:
    print("Fix 2: FAILED - could not find _build_guidance")

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

import py_compile
try:
    py_compile.compile(path, doraise=True)
    print("Syntax check PASSED!")
except py_compile.PyCompileError as e:
    print(f"Syntax check FAILED: {e}")