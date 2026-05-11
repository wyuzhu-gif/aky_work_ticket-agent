import re as _re
from typing import List

_PUNCT_MAP = str.maketrans({
    ',': '，', ';': '；', ':': '：', '(': '（', ')': '）', '!': '！', '?': '？',
})

def _normalize_punct(s):
    return s.translate(_PUNCT_MAP)

def extract_key_phrases(text):
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

def rects_to_quadpoints(rects, page_height):
    if not rects:
        return []
    if len(rects) == 1:
        r = rects[0]
        qp = [round(v, 2) for v in [
            float(r.x0), page_height - float(r.y0), float(r.x1), page_height - float(r.y0),
            float(r.x0), page_height - float(r.y1), float(r.x1), page_height - float(r.y1),
        ]]
        return [qp]
    sorted_rects = sorted(rects, key=lambda r: (r.y0, r.x0))
    groups = []
    current_group = [sorted_rects[0]]
    for r in sorted_rects[1:]:
        prev = current_group[-1]
        same_line = abs(r.y0 - prev.y0) < (prev.y1 - prev.y0) * 0.5
        close_vertically = (r.y0 - prev.y1) < (prev.y1 - prev.y0) * 2.0
        if same_line or close_vertically:
            current_group.append(r)
        else:
            groups.append(current_group)
            current_group = [r]
    groups.append(current_group)
    result = []
    for group in groups:
        x0 = min(float(r.x0) for r in group)
        y0 = min(float(r.y0) for r in group)
        x1 = max(float(r.x1) for r in group)
        y1 = max(float(r.y1) for r in group)
        qp = [round(v, 2) for v in [
            x0, page_height - y0, x1, page_height - y0,
            x0, page_height - y1, x1, page_height - y1,
        ]]
        result.append(qp)
    return result[:5]

def _try_search(page, phrase):
    sr = page.search_for(phrase)
    if sr:
        return sr
    normalized = _normalize_punct(phrase)
    if normalized != phrase:
        sr = page.search_for(normalized)
        if sr:
            return sr
    return []

def _progressive_shorten(page, phrase, logger, label=""):
    if not phrase or len(phrase) < 3:
        return []
    sr = _try_search(page, phrase)
    if sr:
        if logger:
            logger.info(f"[QuadPoints] {label}full match: {repr(phrase[:50])}")
        return sr
    shortened = phrase
    while len(shortened) > 3:
        shortened = shortened[:-2].strip()
        if len(shortened) < 3:
            break
        sr = _try_search(page, shortened)
        if sr:
            if logger:
                logger.info(f"[QuadPoints] {label}shortened: {shortened[:50]!r} (from {phrase[:30]!r})")
            return sr
    return []

def _search_all_pages_for_phrase(doc, pages_to_try, phrase, logger, label, use_progressive=False):
    """Search a phrase across all pages. Returns (quadpoints_list, page_num) or None."""
    for pidx in pages_to_try:
        page = doc[pidx]
        if use_progressive:
            sr = _progressive_shorten(page, phrase, logger, label)
        else:
            sr = _try_search(page, phrase)
        if sr:
            ph = float(page.rect.height)
            logger.info(f"[QuadPoints] {label}page {pidx+1}: {repr(phrase[:40])} -> {len(sr)} rects")
            return rects_to_quadpoints(sr, ph), pidx + 1
    return None

def find_highlight_quadpoints(
    pdf_path: str,
    highlight_text: str,
    page_num: int,
    logger,
    mineru_payload=None,
) -> tuple[list | None, int]:
    """
    Strategy-first, then pages: ensures long phrases are tried on ALL pages
    before falling back to short generic phrases on any page.
    """
    if not highlight_text or not highlight_text.strip():
        return None, page_num
    needle = highlight_text.strip()
    import fitz
    try:
        doc = fitz.open(pdf_path)
        pages_to_try = [page_num - 1] if 1 <= page_num <= doc.page_count else []
        pages_to_try.extend(i for i in range(doc.page_count) if i not in pages_to_try)

        # Prepare cleaned text and phrases once
        cleaned_full = _re.sub(r'\.{2,}', '', needle)
        cleaned_full = _re.sub(r'[|\s]+', ' ', cleaned_full).strip()
        phrases = extract_key_phrases(needle)
        phrases = [_re.sub(r'\s+', ' ', p).strip() for p in phrases]
        phrases = [p for p in phrases if len(p) >= 2]
        phrases.sort(key=len, reverse=True)
        LONG_THRESHOLD = 5
        long_phrases = [p for p in phrases if len(p) > LONG_THRESHOLD]
        short_phrases = [p for p in phrases if len(p) <= LONG_THRESHOLD]
        logger.info(f"[QuadPoints] phrases: long={long_phrases[:5]}, short={short_phrases[:5]}")

        # S1: Exact match on original text (all pages)
        result = _search_all_pages_for_phrase(doc, pages_to_try, needle, logger, "S1 ")
        if result:
            doc.close()
            return result

        # S2: Cleaned text (all pages)
        if cleaned_full != needle and len(cleaned_full) >= 2:
            result = _search_all_pages_for_phrase(doc, pages_to_try, cleaned_full, logger, "S2 ")
            if result:
                doc.close()
                return result

        # S3a: Long phrases with progressive shortening (ALL pages for EACH phrase)
        for phrase in long_phrases:
            result = _search_all_pages_for_phrase(doc, pages_to_try, phrase, logger, "S3a ", use_progressive=True)
            if result:
                doc.close()
                return result

        # S3b: Short phrases as fallback (ALL pages for EACH phrase)
        for phrase in short_phrases:
            result = _search_all_pages_for_phrase(doc, pages_to_try, phrase, logger, "S3b ")
            if result:
                doc.close()
                return result

        # S4: Full cleaned text progressive shortening (all pages)
        if cleaned_full and len(cleaned_full) > 4:
            result = _search_all_pages_for_phrase(doc, pages_to_try, cleaned_full, logger, "S4 ", use_progressive=True)
            if result:
                doc.close()
                return result

        # S5: Keywords (all pages)
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
        for pidx in pages_to_try:
            page = doc[pidx]
            ph = float(page.rect.height)
            found_rects = []
            for kw in unique_kw:
                kr = _try_search(page, kw)
                if kr:
                    found_rects.append(kr[0])
                    if len(found_rects) >= 3:
                        break
            if found_rects:
                logger.info(f"[QuadPoints] S5 keywords page {pidx+1}: {len(found_rects)} kw for {repr(needle[:60])}")
                doc.close()
                return rects_to_quadpoints(found_rects, ph), pidx + 1

        logger.warning(f"[QuadPoints] All strategies failed: {repr(needle[:80])}")
        doc.close()
    except Exception as e:
        logger.warning(f"[QuadPoints] Exception: {e}", exc_info=True)
    return None, page_num
