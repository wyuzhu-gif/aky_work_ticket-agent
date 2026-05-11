"""
fix_cleanup_prompts.py
清理 lc_pipeline.py 中的重复提示词和死代码。

变更内容：
1. 删除未使用的 SYSTEM_PROMPT 静态常量
2. 删除未使用的 IssueTypeLiteral
3. 删除未使用的 HighlightLocation、HighlightOutput 类
4. 删除未使用的 _run_highlight_agent() 函数
5. 将 _build_guidance() 中的审核重点合并到 _build_system_prompt()
6. _build_guidance() 仅保留排除项说明和自定义规则
"""

import sys
from pathlib import Path

TARGET = Path("/data/lvm_data_48T/wyuz/ai-document-review/app/api/services/lc_pipeline.py")


def main():
    text = TARGET.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)

    result = []
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]
        stripped = line.strip()

        # ----------------------------------------------------------
        # 1. Skip IssueTypeLiteral (single line starting with it)
        # ----------------------------------------------------------
        if stripped.startswith("IssueTypeLiteral = Literal["):
            # skip this line and any continuation lines until we find the closing ]
            while i < n and "]" not in stripped:
                i += 1
                if i < n:
                    stripped = lines[i].strip()
            i += 1
            continue

        # ----------------------------------------------------------
        # 2. Skip SYSTEM_PROMPT = """..."""
        # ----------------------------------------------------------
        if stripped.startswith('SYSTEM_PROMPT = """'):
            # skip until closing """
            if stripped.count('"""') >= 2 and stripped.endswith('"""') and not stripped == 'SYSTEM_PROMPT = """':
                # single line case
                i += 1
                continue
            i += 1
            while i < n:
                if '"""' in lines[i].strip():
                    i += 1
                    break
                i += 1
            continue

        # ----------------------------------------------------------
        # 3. Skip class HighlightLocation / HighlightOutput
        # ----------------------------------------------------------
        if stripped.startswith("class HighlightLocation") or stripped.startswith("class HighlightOutput"):
            # skip until we hit a line that is not indented (or blank within class)
            i += 1
            while i < n:
                next_line = lines[i]
                next_stripped = next_line.strip()
                # top-level def/class/async def means class ended
                if next_stripped and not next_line[0] in (' ', '\t'):
                    break
                # blank line might be inside or outside — peek ahead
                if next_stripped == "":
                    # peek: if next non-blank line is top-level, class ended
                    j = i + 1
                    while j < n and lines[j].strip() == "":
                        j += 1
                    if j < n and not lines[j][0] in (' ', '\t'):
                        # class ended — skip trailing blank lines
                        i = j
                        break
                i += 1
            continue

        # ----------------------------------------------------------
        # 4. Rewrite _build_system_prompt — add review focus items
        # ----------------------------------------------------------
        if stripped.startswith("def _build_system_prompt("):
            # Read the entire function
            func_start = i
            func_lines = [line]
            i += 1
            while i < n:
                fline = lines[i]
                fstripped = fline.strip()
                # Detect end of function: next top-level def/class/async def
                if fstripped and not fline[0] in (' ', '\t') and (
                    fstripped.startswith("def ") or fstripped.startswith("class ") or fstripped.startswith("async def ")
                ):
                    break
                func_lines.append(fline)
                i += 1

            func_text = "".join(func_lines)

            # Check if it already has review focus items
            if "重点审核项" not in func_text:
                # Insert review focus items before "问题类型包括但不限于"
                insert_point = '        "问题类型包括但不限于：\\n"'
                new_section = (
                    '        "重点审核项（包括但不限于）：\\n"\n'
                    '        "1. 气体分析：超标误判合格（第5.3.2条）\\n"\n'
                    '        "2. 监护人：是否兼做与监护无关的工作（第4.10条）\\n"\n'
                    '        "3. 安全措施：确认栏选\'否\'的项是否影响安全。动火方式含气焊/气割时气瓶措施必须确认\'是\'，含电焊时接地措施必须确认\'是\'（第5.2条）\\n"\n'
                    '        "4. 作业级别：是否勾选，是否与风险匹配（第5.1条）\\n"\n'
                    '        "5. 人员信息：仔细检查名单中是否有重复姓名，证件号是否有错\\n"\n'
                    '        "6. 审批流程：签字齐全性、时间逻辑（第4.6条）\\n"\n'
                    '        "7. 以及GB 30871-2022的任何其他违规项\\n\\n"\n'
                )
                func_text = func_text.replace(insert_point, new_section + insert_point)

            result.append(func_text)
            continue

        # ----------------------------------------------------------
        # 5. Rewrite _build_guidance — remove review focus items
        # ----------------------------------------------------------
        if stripped.startswith("def _build_guidance("):
            func_start = i
            func_lines = [line]
            i += 1
            while i < n:
                fline = lines[i]
                fstripped = fline.strip()
                if fstripped and not fline[0] in (' ', '\t') and (
                    fstripped.startswith("def ") or fstripped.startswith("class ") or fstripped.startswith("async def ")
                ):
                    break
                func_lines.append(fline)
                i += 1

            func_text = "".join(func_lines)

            # Replace the review focus items section with just exclusion rules
            old_focus = '''    lines = [
        "重点审核项（包括但不限于）：",
        "1. 气体分析：超标误判合格第5.3.2条）",
        "2. 监护人：是否兼做与监护无关的工作。（第4.10条）",
        "3. 安全措施：确认栏选'否'的项是否影响安全。交叉检查：动火方式含气焊/气割时气瓶措施必须确认'是'，含电焊时接地措施必须确认'是'""(第5.2条)",
        "4. 作业级别：是否勾选，是否与风险匹配(第5.1条)",
        "5. 人员信息：仔细检查动火人名单中是否有重复姓名，证件号是否有错",
        "6. 审批流程：签字齐全性、时间逻辑 (第4.6条)",
        "8. 以及GB 30871-2022的任何其他违规项",
        ""
        "注意：以下情况不算不合规，不要报告："
        "- 日期和时间之间缺少空格、格式不统一等纯排版问题"
        "- 表格中列宽、对齐、字体大小等显示问题"
        "- 只关注实质性的安全合规问题（气体超标、措施未落实、人员冲突、审批缺失等）",
    ]'''

            new_focus = '''    lines = [
        "注意：以下情况不算不合规，不要报告：",
        "- 日期和时间之间缺少空格、格式不统一等纯排版问题",
        "- 表格中列宽、对齐、字体大小等显示问题",
        "- 只关注实质性的安全合规问题（气体超标、措施未落实、人员冲突、审批缺失等）",
    ]'''

            func_text = func_text.replace(old_focus, new_focus)

            # Also update docstring
            func_text = func_text.replace(
                '"""Build guidance section for GB 30871-2022 work ticket review."""',
                '"""Build supplementary guidance: exclusion rules, custom rules, and rule documents."""'
            )

            result.append(func_text)
            continue

        # ----------------------------------------------------------
        # 6. Skip _run_highlight_agent function
        # ----------------------------------------------------------
        if stripped.startswith("async def _run_highlight_agent("):
            i += 1
            while i < n:
                next_line = lines[i]
                next_stripped = next_line.strip()
                if next_stripped and not next_line[0] in (' ', '\t') and (
                    next_stripped.startswith("def ") or next_stripped.startswith("class ") or next_stripped.startswith("async def ")
                ):
                    break
                i += 1
            continue

        # ----------------------------------------------------------
        # Default: keep the line
        # ----------------------------------------------------------
        result.append(line)
        i += 1

    # Clean up excessive blank lines
    import re
    final = "".join(result)
    final = re.sub(r'\n{4,}', '\n\n\n', final)

    # Verify the file still has key functions
    assert "_build_system_prompt" in final, "ERROR: _build_system_prompt missing!"
    assert "_build_guidance" in final, "ERROR: _build_guidance missing!"
    assert "class LangChainPipeline" in final, "ERROR: LangChainPipeline missing!"
    assert "SYSTEM_PROMPT" not in final, "ERROR: SYSTEM_PROMPT still present!"
    assert "_run_highlight_agent" not in final, "ERROR: _run_highlight_agent still present!"

    TARGET.write_text(final, encoding="utf-8")
    print(f"SUCCESS: Cleaned up {TARGET}")
    print(f"  - Removed SYSTEM_PROMPT, IssueTypeLiteral, HighlightLocation, HighlightOutput, _run_highlight_agent")
    print(f"  - Merged review focus items into _build_system_prompt")
    print(f"  - Simplified _build_guidance to only contain exclusion rules + custom rules")


if __name__ == "__main__":
    main()
