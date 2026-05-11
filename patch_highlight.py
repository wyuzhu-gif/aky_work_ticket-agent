"""
Patch: Replace _find_highlight_quadpoints with multi-strategy search.
Strips table formatting (|) before searching, tries segments and keywords.
"""
import re

FILE = "/data/lvm_data_48T/wyuz/ai-document-review/app/api/services/lc_pipeline.py"
content = open(FILE, encoding="utf-8").read()

# 1. Add imports
if "import time" not in content:
    content = content.replace("import uuid", "import uuid\nimport time", 1)
    print("Added: import time")

# 2. Find and replace _find_highlight_quadpoints
marker = "def _find_highlight_quadpoints("
if marker not in content:
    print("ERROR: function not found")
    raise SystemExit(1)

start = content.index(marker)
rest = content[start + len(marker):]
m = re.search(r"\ndef [a-zA-Z_]", rest)
if not m:
    print("ERROR: cannot find end of function")
    raise SystemExit(1)
end = start + len(marker) + m.start()

old_func = content[start:end]
print(f"Old function: {len(old_func)} chars, lines {content[:start].count(chr(10))+1}-{content[:end].count(chr(10))+1}")

# New helper functions + replacement function
NEW_CODE = '''import re as _re


def _split_highlight_segments(text):
    """Split highlight text into searchable segments by stripping table formatting (|)."""
    cleaned = text.replace("|", " ")
    cleaned = _re.sub(r"[\t\r]+", " ", cleaned)
    cleaned = _re.sub(r" {2,}", " ", cleaned)
    segments = []
    for line in cleaned.split("\n"):
        s = line.strip()
        if len(s) >= 2:
            segments.append(s)
    return segments


def _rects_to_quadpoints(rects, page_height):
    """Merge multiple fitz.Rect into one quadpoints enclosing bbox."""
    if not rects:
        return []
    x0 = min(float(r.x0) for r in rects)
    y0 = min(float(r.y0) for r in rects)
    x1 = max(float(r.x1) for r in rects)
    y1 = max(float(r.y1) for r in rects)
    return [round(v, 2) for v in [
        x0, page_height - y0, x1, page_height - y0,
        x0, page_height - y1, x1, page_height - y1,
    ]]


def _find_highlight_quadpoints(
    pdf_path: str,
    highlight_text: str,
    page_num: int,
) -> tuple[List[float] | None, int]:
    """
    Find highlight location with progressive fallback:
    1. Exact text match
    2. Stripped match (remove |, normalize spaces)
    3. Semantic segments (split by | into parts, search each)
    4. Keyword match (distinctive CJK phrases, numbers)
    Returns (quadpoints, actual_page) or (None, page_num).
    """
    if not highlight_text or not highlight_text.strip():
        return None, page_num
    needle = highlight_text.strip()

    try:
        doc = fitz.open(pdf_path)
        pages_to_try = [page_num - 1] if 1 <= page_num <= doc.page_count else []
        pages_to_try.extend(i for i in range(doc.page_count) if i not in pages_to_try)

        for pidx in pages_to_try:
            page = doc[pidx]
            ph = float(page.rect.height)

            # --- Strategy 1: Exact match ---
            rects = page.search_for(needle)
            if rects:
                logging.info(f"[QuadPoints] S1 exact hit page {pidx+1}: {repr(needle[:60])}")
                doc.close()
                return _rects_to_quadpoints(rects, ph), pidx + 1

            # --- Strategy 2: Strip table formatting (|) ---
            stripped = _re.sub(r"[|\s]+", " ", needle).strip()
            if stripped != needle and len(stripped) >= 2:
                rects = page.search_for(stripped)
                if rects:
                    logging.info(f"[QuadPoints] S2 stripped hit page {pidx+1}: {repr(stripped[:60])}")
                    doc.close()
                    return _rects_to_quadpoints(rects, ph), pidx + 1

            # --- Strategy 3: Split by | into segments ---
            segments = _split_highlight_segments(needle)
            if segments:
                found = []
                for seg in segments:
                    seg_c = _re.sub(r"\s+", " ", seg).strip()
                    if len(seg_c) < 2:
                        continue
                    sr = page.search_for(seg_c)
                    if sr:
                        found.append(sr[0])
                if found:
                    logging.info(f"[QuadPoints] S3 segments hit page {pidx+1}: {len(found)}/{len(segments)} found for {repr(needle[:60])}")
                    doc.close()
                    return _rects_to_quadpoints(found, ph), pidx + 1

            # --- Strategy 4: Distinctive keywords ---
            kw_list = []
            # CJK phrases 3+ chars (most specific)
            kw_list.extend(_re.findall(r"[\u4e00-\u9fff]{3,}", needle))
            # Numbers with units (e.g. "1.00%", "10m")
            kw_list.extend(_re.findall(r"[\d.]+\s*[%]", needle))
            # Person names followed by colon
            kw_list.extend(_re.findall(r"[\u4e00-\u9fff]{2,4}(?=:)", needle))
            # Deduplicate, sort by length desc (longer = more specific first)
            seen = set()
            unique_kw = []
            for kw in sorted(kw_list, key=len, reverse=True):
                kw = kw.strip()
                if kw and kw not in seen and len(kw) >= 2:
                    seen.add(kw)
                    unique_kw.append(kw)

            found = []
            for kw in unique_kw:
                kr = page.search_for(kw)
                if kr:
                    found.append(kr[0])
                    if len(found) >= 3:
                        break
            if found:
                logging.info(f"[QuadPoints] S4 keywords hit page {pidx+1}: {len(found)} kw for {repr(needle[:60])}")
                doc.close()
                return _rects_to_quadpoints(found, ph), pidx + 1

        logging.warning(f"[QuadPoints] All strategies failed: {repr(needle[:80])}")
        doc.close()
    except Exception as e:
        logging.warning(f"[QuadPoints] Exception: {e}", exc_info=True)
    return None, page_num

'''

content = content[:start] + NEW_CODE + content[end:]

open(FILE, "w", encoding="utf-8").write(content)
print("File written successfully")

# Verify syntax
import py_compile
try:
    py_compile.compile(FILE, doraise=True)
    print("Syntax OK")
except py_compile.PyCompileError as e:
    print(f"Syntax error: {e}")
