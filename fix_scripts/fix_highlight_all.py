  path = '/data/lvm_data_48T/wyuz/ai-document-review/app/api/services/lc_pipeline.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Fix 1: Change bbox handling to support multiple quadpoints
old_block = '''            bbox, actual_page = find_highlight_quadpoints(
                pdf_path, hl_text, hl_page, logging
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

new_block = '''            bbox_list, actual_page = find_highlight_quadpoints(
                pdf_path, hl_text, hl_page, logging
            )
            if bbox_list:
                logging.info(f"  -> Found {len(bbox_list)} highlight region(s) at page {actual_page}")
                page_num = actual_page
            else:
                # Fallback to paragraph bbox
                space = page_bbox_space.get(page_num) or {}
                observed_max = space.get("observed_max")
                coverage = 1.0 if space.get("is_canvas") else settings.mineru_bbox_content_coverage
                fb = bbox_to_quadpoints(
                    para.get("bbox"),
                    page_sizes.get(page_num),
                    origin=settings.mineru_bbox_origin,
                    units=settings.mineru_bbox_units,
                    observed_max=observed_max,
                    content_coverage=coverage,
                )
                if not fb:
                    fb = [0, 0, 0, 0, 0, 0, 0, 0]
                    logging.info(f"  -> No highlight found, using zero bbox")
                bbox_list = [fb]'''

if old_block in content:
    content = content.replace(old_block, new_block)
    print("Fix 1: Updated highlight search call site")
else:
    print("Fix 1: FAILED - could not find highlight search block")

# Fix 2: Store bbox_list as flat list in bounding_box
old_location = '''            location = Location(
                source_sentence=para["content"],
                page_num=page_num,
                bounding_box=bbox,
                para_index=para_index,
            )'''

new_location = '''            # Flatten all quadpoints groups into one bounding_box list
            # Format: [qp1_0..qp1_7, qp2_0..qp2_7, ...] (each group is 8 floats)
            flat_bbox = []
            for qp in bbox_list:
                flat_bbox.extend(qp)
            location = Location(
                source_sentence=para["content"],
                page_num=page_num,
                bounding_box=flat_bbox,
                para_index=para_index,
            )'''

if old_location in content:
    content = content.replace(old_location, new_location)
    print("Fix 2: Updated location storage with flat bbox list")
else:
    print("Fix 2: FAILED - could not find location block")

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

import py_compile
try:
    py_compile.compile(path, doraise=True)
    print("Syntax check PASSED!")
except py_compile.PyCompileError as e:
    print(f"Syntax check FAILED: {e}")