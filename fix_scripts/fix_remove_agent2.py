path = '/data/lvm_data_48T/wyuz/ai-document-review/app/api/services/lc_pipeline.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# === Replace the Agent 2 block + highlight search with direct highlight_search.py ===
old_block = '''        # === Agent 2: Intelligent highlight positioning ===
        highlight_mapping: Dict[int, tuple[str, int]] = {}
        if raw_issues:
            try:
                pdf_page_texts = _extract_pdf_page_text(pdf_path)
                highlight_mapping = await _run_highlight_agent(self.llm, raw_issues, pdf_page_texts)
                logging.info(f"Agent 2 returned {len(highlight_mapping)} highlight mappings for {len(raw_issues)} issues")
            except Exception as e:
                logging.error(f"Agent 2 failed, falling back: {e}")

        issues: List[Issue] = []
        for issue_index, raw in enumerate(raw_issues or []):
            # Use the type directly - it can be a built-in type or custom rule name
            issue_type = raw.type if isinstance(raw, ReviewIssue) else IssueType.GrammarSpelling.value

            # Determine risk level based on issue type
            risk_level = self._get_risk_level_for_type(issue_type, custom_rules)

            para_index = raw.para_index if isinstance(raw, ReviewIssue) else 0
            para = chunk[para_index] if 0 <= para_index < len(chunk) else chunk[0]

            page_num = int(para.get("page_num", 1) or 1)
            bbox = _find_pdf_quadpoints(
                pdf_path,
                page_num,
                needle=(raw.text if isinstance(raw, ReviewIssue) else None),
                fallback_sentence=para.get("content"),
            )
            if not bbox:
                bbox = _find_layout_quadpoints(
                    layout,
                    page_num,
                    page_size_points=page_sizes.get(page_num),
                    needle=(raw.text if isinstance(raw, ReviewIssue) else None),
                    fallback_sentence=para.get("content"),
                )

            if not bbox:
                space = page_bbox_space.get(page_num) or {}
                observed_max = space.get("observed_max")
                coverage = 1.0 if space.get("is_canvas") else settings.mineru_bbox_content_coverage
                bbox = bbox_to_quadpoints(
                    para.get("bbox"),
                    page_sizes.get(page_num),
                    origin=settings.mineru_bbox_origin,
                    units=settings.mineru_bbox_units,
                    observed_max=observed_max,
                    content_coverage=coverage,
                )
            if not bbox:
                bbox = [0, 0, 0, 0, 0, 0, 0, 0]'''

new_block = '''        # === Highlight positioning via semantic search (no Agent 2 LLM call) ===
        issues: List[Issue] = []
        for issue_index, raw in enumerate(raw_issues or []):
            issue_type = raw.type if isinstance(raw, ReviewIssue) else IssueType.GrammarSpelling.value
            risk_level = self._get_risk_level_for_type(issue_type, custom_rules)

            para_index = raw.para_index if isinstance(raw, ReviewIssue) else 0
            para = chunk[para_index] if 0 <= para_index < len(chunk) else chunk[0]
            page_num = int(para.get("page_num", 1) or 1)

            # Use original_text from Agent 1 for highlight search
            hl_text = raw.original_text if isinstance(raw, ReviewIssue) and raw.original_text else para.get("content", "")
            hl_page = page_num
            logging.info(f"Highlight search for issue {issue_index}: page={hl_page}, text={hl_text[:80]}...")

            bbox, actual_page = find_highlight_quadpoints(
                pdf_path, hl_text, hl_page, logging, mineru_payload=mineru_payload
            )
            if bbox:
                logging.info(f"  -> Found highlight at page {actual_page}")
                page_num = actual_page
            else:
                # Fallback to paragraph bbox
                space = page_bbox_space.get(page_num) or {}
                observed_max = space.get("observed_max")
                coverage = 1.0 if space.get("is_canvas") else settings.mineru_bbox_content_coverage
                bbox = bbox_to_quadpoints(
                    para.get("bbox"),
                    page_sizes.get(page_num),
                    origin=settings.mineru_bbox_origin,
                    units=settings.mineru_bbox_units,
                    observed_max=observed_max,
                    content_coverage=coverage,
                )
                if not bbox:
                    bbox = [0, 0, 0, 0, 0, 0, 0, 0]
                    logging.info(f"  -> No highlight found, using zero bbox")'''

if old_block in content:
    content = content.replace(old_block, new_block)
    print("Replaced Agent 2 + highlight block successfully")
else:
    print("ERROR: Could not find exact match")
    # Show what we're looking for vs what's there
    import re
    m = re.search(r'# === Agent 2', content)
    if m:
        print(f"Agent 2 block starts at position {m.start()}")
        print("Content around there:")
        print(repr(content[m.start():m.start()+200]))
    else:
        print("No 'Agent 2' block found at all")

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

import py_compile
try:
    py_compile.compile(path, doraise=True)
    print("Syntax check PASSED!")
except py_compile.PyCompileError as e:
    print(f"Syntax check FAILED: {e}")