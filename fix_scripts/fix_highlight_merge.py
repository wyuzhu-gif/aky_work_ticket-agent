  path = '/data/lvm_data_48T/wyuz/ai-document-review/app/api/services/highlight_search.py'
new_content = r'''import re as _re
from typing import List


def extract_key_phrases(text):
    """
    Extract meaningful search phrases from highlight text.
    Remove | and ... symbols, then split into distinct phrases.
    """
    cleaned = _re.sub(r'\.{2,}', '', text)
    parts = cleaned.split('|')
    phrases = []
    for part in parts:
        p = part.strip()
        if len(p) < 2:
            continue
        if _re.match(r'^[\d\s\-:]+$', p):
            continue
        phrases.append(p)
    return phrases


def rects_to_quadpoints_list(rects, page_height, gap_ratio=0.5):
    """
    Merge nearby rects into groups, return a list of quadpoints (one per group).

    Rects within gap_ratio * line_height of each other are merged into one group.
    Rects far apart remain as separate independent highlights.
    """
    if not rects:
        return []
    sorted_rects = sorted(rects, key=lambda r: (r.y0, r.x0))

    line_height = max(float(r.height) for r in sorted_rects[:3]) if sorted_rects else 12
    gap_threshold = line_height * gap_ratio

    groups = [[sorted_rects[0]]]
    for r in sorted_rects[1:]:
        last = groups[-1][-1]
        if (abs(float(r.y0) - float(last.y1)) < gap_threshold or
            abs(float(r.y0) - float(last.y0)) < gap_threshold):
            groups[-1].append(r)
        else:
            groups.append([r])

    results = []
    for group in groups:
        x0 = min(float(r.x0) for r in group)
        y0 = min(float(r.y0) for r in group)
        x1 = max(float(r.x1) for r in group)
        y1 = max(float(r.y1) for r in group)
        qp = [round(v, 2) for v in [
            x0, page_height - y0, x1, page_height - y0,
            x0, page_height - y1, x1, page_height - y1,
        ]]
        results.append(qp)
    return results


def find_highlight_quadpoints(
    pdf_path: str,
    highlight_text: str,
    page_num: int,
    logger,
    mineru_payload=None,
) -> tuple[list | None, int]:
    """
    Find highlight with progressive fallback, cleaning | and ... first.
    Returns (list_of_quadpoints, actual_page).
    Each quadpoint group covers a spatially close region; distant regions are separate.
    """
    if not highlight_text or not highlight_text.strip():
        return None, page_num
    needle = highlight_text.strip()
    import fitz
    try:
        doc = fitz.open(pdf_path)
        pages_to_try = [page_num - 1] if 1 <= page_num <= doc.page_count else []
        pages_to_try.extend(i for i in range(doc.page_count) if i not in pages_to_try)
        for pidx in pages_to_try:
            page = doc[pidx]
            ph = float(page.rect.height)

            # S1: Exact match on original text
            rects = page.search_for(needle)
            if rects:
                logger.info(f"[QuadPoints] S1 exact page {pidx+1}: {repr(needle[:60])}")
                doc.close()
                return rects_to_quadpoints_list(rects, ph), pidx + 1

            # S2: Strip | and ... then search as whole string
            cleaned_full = _re.sub(r'\.{2,}', '', needle)
            cleaned_full = _re.sub(r'[|\s]+', ' ', cleaned_full).strip()
            if cleaned_full != needle and len(cleaned_full) >= 2:
                rects = page.search_for(cleaned_full)
                if rects:
                    logger.info(f"[QuadPoints] S2 cleaned page {pidx+1}: {repr(cleaned_full[:60])}")
                    doc.close()
                    return rects_to_quadpoints_list(rects, ph), pidx + 1

            # S3: Extract key phrases (split by |, remove ...) and search each
            phrases = extract_key_phrases(needle)
            if phrases:
                found_rects = []
                for phrase in phrases:
                    phrase_clean = _re.sub(r'\s+', ' ', phrase).strip()
                    if len(phrase_clean) < 2:
                        continue
                    sr = page.search_for(phrase_clean)
                    if sr:
                        found_rects.extend(sr)
                        logger.info(f"[QuadPoints] S3 phrase matched: {repr(phrase_clean[:40])}")
                if found_rects:
                    logger.info(f"[QuadPoints] S3 phrases page {pidx+1}: {len(found_rects)} rects for {repr(needle[:60])}")
                    doc.close()
                    return rects_to_quadpoints_list(found_rects, ph), pidx + 1

            # S4: Shortened phrases - try progressively shorter versions
            found_rects = []
            for phrase in phrases:
                phrase_clean = _re.sub(r'\s+', ' ', phrase).strip()
                if len(phrase_clean) < 3:
                    continue
                for length in range(len(phrase_clean), 2, -1):
                    candidate = phrase_clean[:length]
                    sr = page.search_for(candidate)
                    if sr:
                        found_rects.extend(sr)
                        logger.info(f"[QuadPoints] S4 prefix matched: {repr(candidate[:40])}")
                        break
            if found_rects:
                logger.info(f"[QuadPoints] S4 prefix page {pidx+1}: {len(found_rects)} rects for {repr(needle[:60])}")
                doc.close()
                return rects_to_quadpoints_list(found_rects, ph), pidx + 1

            # S5: Distinctive keywords (CJK phrases, percentages, names)
            kw_list = []
            kw_list.extend(_re.findall(r'[一-鿿]{3,}', needle))
            kw_list.extend(_re.findall(r'[\d.]+\s*[%]', needle))
            kw_list.extend(_re.findall(r'[一-鿿]{2,4}(?=:)', needle))
            seen_kw = set()
            unique_kw = []
            for kw in sorted(kw_list, key=len, reverse=True):
                kw = kw.strip()
                if kw and kw not in seen_kw and len(kw) >= 2:
                    seen_kw.add(kw)
                    unique_kw.append(kw)
            found_rects = []
            for kw in unique_kw:
                kr = page.search_for(kw)
                if kr:
                    found_rects.extend(kr)
                    if len(found_rects) >= 3:
                        break
            if found_rects:
                logger.info(f"[QuadPoints] S5 keywords page {pidx+1}: {len(found_rects)} kw for {repr(needle[:60])}")
                doc.close()
                return rects_to_quadpoints_list(found_rects, ph), pidx + 1

        logger.warning(f"[QuadPoints] All strategies failed: {repr(needle[:80])}")
        doc.close()
    except Exception as e:
        logger.warning(f"[QuadPoints] Exception: {e}", exc_info=True)
    return None, page_num
'''

with open(path, 'w', encoding='utf-8') as f:
    f.write(new_content)

print("Rewritten highlight_search.py with smart grouping")