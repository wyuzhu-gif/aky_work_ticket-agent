"""
Patch 7: Add Agent 2 for intelligent highlight positioning.
Agent 1 reviews compliance, Agent 2 maps issues to exact PDF text locations.
"""
FILE = "/data/lvm_data_48T/wyuz/ai-document-review/app/api/services/lc_pipeline.py"
content = open(FILE, encoding="utf-8").read()

# ============================================================
# 1. Add new Pydantic models for Agent 2 output
# ============================================================
OLD_MODELS = """class ReviewOutput(BaseModel):
    issues: List[ReviewIssue]"""

NEW_MODELS = """class ReviewOutput(BaseModel):
    issues: List[ReviewIssue]


class HighlightLocation(BaseModel):
    \"\"\"Agent 2 output: exact highlight position for each issue.\"\"\"
    issue_index: int = Field(description="问题在issues列表中的索引（从0开始）")
    page: int = Field(description="该问题原文所在的PDF页码（1-based）")
    highlight_text: str = Field(
        description="从PDF页面文本中找到的完整原文片段。"
        "必须与PDF中的文字完全一致，包含完整的内容，"
        "如人名必须包含完整姓名，不能截断。"
    )


class HighlightOutput(BaseModel):
    highlights: List[HighlightLocation]"""

content = content.replace(OLD_MODELS, NEW_MODELS)

# ============================================================
# 2. Add helper functions before _init_deepseek_model
# ============================================================
HELPER_FUNCTIONS = r'''
def _extract_pdf_page_text(pdf_path: str) -> Dict[int, str]:
    """Extract text from each page of the PDF using fitz."""
    page_texts: Dict[int, str] = {}
    try:
        doc = fitz.open(pdf_path)
        for i in range(doc.page_count):
            page = doc[i]
            text = page.get_text("text")
            if text.strip():
                page_texts[i + 1] = text
        doc.close()
    except Exception as e:
        logging.warning(f"Failed to extract PDF page text: {e}")
    return page_texts


async def _run_highlight_agent(
    llm,
    raw_issues: List[ReviewIssue],
    pdf_page_texts: Dict[int, str],
) -> Dict[int, tuple[str, int]]:
    """
    Agent 2: Given Agent 1's issues and actual PDF page text,
    determine exact highlight text and page for each issue.
    Returns: {issue_index: (highlight_text, page_number)}
    """
    if not raw_issues:
        return {}

    # Build the issues list for the prompt
    issues_desc = []
    for i, issue in enumerate(raw_issues):
        issues_desc.append(f"[{i}] 类型: {issue.type}")
        issues_desc.append(f"    问题描述: {issue.text}")
        issues_desc.append(f"    Agent1引用原文: {issue.original_text}")
        issues_desc.append("")

    # Build PDF page text section
    pages_desc = []
    for page_num in sorted(pdf_page_texts.keys()):
        text = pdf_page_texts[page_num]
        # Truncate very long pages to avoid token limits
        if len(text) > 3000:
            text = text[:3000] + "...(截断)"
        pages_desc.append(f"=== 第{page_num}页 ===")
        pages_desc.append(text)
        pages_desc.append("")

    highlight_parser = PydanticOutputParser(pydantic_object=HighlightOutput)

    system = """你是PDF高亮定位专家。你的任务是根据审核问题列表和PDF各页面的实际文本，找到每个问题在PDF中对应的精确原文位置。

关键要求：
1. highlight_text 必须是从PDF页面文本中逐字复制的完整片段，不能截断、不能改写
2. 人名必须完整（如"刘士金"不能只写"刘"或"刘士"）
3. 优先搜索包含问题关键信息的完整短语
4. 如果Agent1引用原文在PDF中能找到，直接使用它
5. 如果Agent1引用原文在PDF中找不到（可能因为OCR/格式差异），在PDF文本中找到最接近的完整片段
6. page 必须是highlight_text实际出现的页码"""

    human = f"""请为以下审核问题确定PDF高亮位置：

## 审核问题列表：
{chr(10).join(issues_desc)}

## PDF各页面实际文本：
{chr(10).join(pages_desc)}

请为每个问题找到在PDF中对应的完整原文片段和所在页码。

{highlight_parser.get_format_instructions()}"""

    try:
        messages = [
            SystemMessage(content=system),
            HumanMessage(content=human),
        ]
        resp = await llm.ainvoke(messages)
        out = resp.content if hasattr(resp, "content") else resp
        if isinstance(out, list):
            out = "".join(
                [c.get("text", "") if isinstance(c, dict) else str(c) for c in out]
            )
        result = highlight_parser.parse(str(out))

        mapping = {}
        for h in result.highlights:
            mapping[h.issue_index] = (h.highlight_text, h.page)
        return mapping
    except Exception as e:
        logging.error(f"Highlight agent failed: {e}")
        return {}


def _find_highlight_quadpoints(
    pdf_path: str,
    highlight_text: str,
    page_num: int,
) -> tuple[List[float] | None, int]:
    """
    Use fitz search_for to find ALL matching rects for highlight_text.
    For multi-line text, merges all rects into enclosing bbox.
    Returns (quadpoints, actual_page) or (None, page_num).
    """
    if not highlight_text:
        return None, page_num

    try:
        doc = fitz.open(pdf_path)

        # Try exact page first, then all pages
        pages_to_try = [page_num - 1] if 1 <= page_num <= doc.page_count else []
        pages_to_try.extend(i for i in range(doc.page_count) if i not in pages_to_try)

        for pidx in pages_to_try:
            page = doc[pidx]
            rects = page.search_for(highlight_text)
            if rects:
                ph = float(page.rect.height)
                all_x0 = min(float(r.x0) for r in rects)
                all_y0 = min(float(r.y0) for r in rects)
                all_x1 = max(float(r.x1) for r in rects)
                all_y1 = max(float(r.y1) for r in rects)
                quadpoints = [round(v, 2) for v in [
                    all_x0, ph - all_y0, all_x1, ph - all_y0,
                    all_x0, ph - all_y1, all_x1, ph - all_y1,
                ]]
                doc.close()
                return quadpoints, pidx + 1

        doc.close()
    except Exception as e:
        logging.warning(f"_find_highlight_quadpoints failed: {e}")
    return None, page_num

'''

content = content.replace(
    "\ndef _init_deepseek_model():",
    HELPER_FUNCTIONS + "\ndef _init_deepseek_model():",
)

# ============================================================
# 3. Add Agent 2 call before the issues loop in _process_chunk
# ============================================================
OLD_BEFORE_LOOP = """        issues: List[Issue] = []
        for raw in raw_issues or []:"""

NEW_BEFORE_LOOP = """        # === Agent 2: Intelligent highlight positioning ===
        highlight_mapping: Dict[int, tuple[str, int]] = {}
        if raw_issues:
            try:
                pdf_page_texts = _extract_pdf_page_text(pdf_path)
                highlight_mapping = await _run_highlight_agent(self.llm, raw_issues, pdf_page_texts)
                logging.info(f"Agent 2 returned {len(highlight_mapping)} highlight mappings for {len(raw_issues)} issues")
            except Exception as e:
                logging.error(f"Agent 2 failed, falling back: {e}")

        issues: List[Issue] = []
        for issue_index, raw in enumerate(raw_issues or []):"""

content = content.replace(OLD_BEFORE_LOOP, NEW_BEFORE_LOOP)

# ============================================================
# 4. Replace highlight logic in the loop to use Agent 2 results
# ============================================================
OLD_HIGHLIGHT = """            logging.info(f"Issue highlight: type={issue_type}, original_text={repr((highlight_text or '')[:80])}, para_index={para_index}, page={page_num}")

            # === Highlight strategy ===
            # MinerU merges entire table into 1 paragraph, so bbox is useless.
            # Must extract short keywords from original_text and search PDF text layer.
            bbox, actual_page = _highlight_by_keywords(pdf_path, highlight_text, page_num)
            if bbox:
                page_num = actual_page  # Use actual found page, not MinerU's page_num
            if not bbox:
                bbox = _fallback_bbox(para, page_sizes.get(page_num), page_bbox_space.get(page_num))
            if not bbox:
                bbox = [0, 0, 0, 0, 0, 0, 0, 0]"""

NEW_HIGHLIGHT = """            logging.info(f"Issue highlight: type={issue_type}, original_text={repr((highlight_text or '')[:80])}, para_index={para_index}, page={page_num}")

            # === Highlight strategy (Agent 2) ===
            bbox = None
            if issue_index in highlight_mapping:
                hl_text, hl_page = highlight_mapping[issue_index]
                bbox, actual_page = _find_highlight_quadpoints(pdf_path, hl_text, hl_page)
                if bbox:
                    page_num = actual_page
                    logging.info(f"Agent2 highlight found: text={repr(hl_text[:50])}, page={page_num}")
            if not bbox:
                bbox = _fallback_bbox(para, page_sizes.get(page_num), page_bbox_space.get(page_num))
            if not bbox:
                bbox = [0, 0, 0, 0, 0, 0, 0, 0]"""

content = content.replace(OLD_HIGHLIGHT, NEW_HIGHLIGHT)

# ============================================================
# 5. Remove the FIRST duplicate _highlight_by_keywords (lines 412-488)
#    Keep the second copy (lines 490-566) as unused fallback.
# ============================================================
import re
# The first copy starts right after _find_mineru_bbox function
# Pattern: first "def _highlight_by_keywords(" ... until second "def _highlight_by_keywords("
# We match the first one and remove it
dup_pattern = (
    r'\n(def _highlight_by_keywords\([\s\S]*?'
    r'return None, page_num\n)'
    r'\n(def _highlight_by_keywords\()'
)
match = re.search(dup_pattern, content)
if match:
    # Remove the first copy, keep only the second function definition start
    content = content[:match.start()] + "\n" + "def _highlight_by_keywords(" + content[match.end():]
    print("Removed duplicate _highlight_by_keywords")
else:
    print("WARNING: Could not find duplicate _highlight_by_keywords to remove")

open(FILE, "w", encoding="utf-8").write(content)
print("Patch 7 (Agent 2 highlight positioning) applied successfully!")
