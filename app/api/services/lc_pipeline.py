import uuid
from typing import Any, AsyncGenerator, Dict, List
from pathlib import Path
import json
from difflib import SequenceMatcher

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field
from typing import Literal
import fitz

from common.logger import get_logger
from common.models import Issue, IssueStatusEnum, IssueType, Location, ReviewRule, RiskLevel, RuleDocument
from config.config import settings
from services.bbox import bbox_to_quadpoints
from services.mineru_client import MinerUClient
from services.highlight_search import find_highlight_quadpoints

logging = get_logger(__name__)


class ReviewIssue(BaseModel):
    type: str  # 合规问题类型
    text: str = Field(description="问题描述：简要描述作业票中不合规的具体内容")
    original_text: str = Field(description="问题原文：请从输入文本中逐字引用存在问题的原文片段，必须与输入文字完全一致（用于PDF精确定位高亮）")
    explanation: str = Field(description="违反条款：引用GB 30871-2022中具体的条款编号或标准编号")
    suggested_fix: str = Field(description="整改建议：针对该问题提出的整改措施")
    para_index: int = Field(description="段落索引")


class ReviewOutput(BaseModel):
    issues: List[ReviewIssue]


# Default review focus items (used when no rules with prompts are selected)
_DEFAULT_FOCUS_LINES = [
    "1. 气体分析：超标误判合格（第5.3.2条）",
    "2. 监护人：是否兼做与监护无关的工作（第4.10条）",
    "3. 安全措施：确认栏选'否'的项是否影响安全。动火方式含气焊/气割时气瓶措施必须确认'是'(第5.2.13条），含电焊时接地措施必须确认'是'（第10.4条）",
    "4. 作业级别：是否勾选，是否与风险匹配（第5.1.1条）",
    "5. 人员信息：仔细检查名单中是否有重复姓名，证件号是否有错(第4.18条）",
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
        "【核心原则——只报告确定的不合规项】",
        "1. 你只能报告能在输入文本中找到确切证据的问题，禁止推测、脑补或臆想。",
        "2. explanation 字段必须引用 GB 30871-2022 中真实存在的条款编号（如第5.3.2条），不得编造条款。",
        "3. 如果你不确定某项是否违规，不要报告。宁可漏报也不要误报。",
        "4. 不要根据常识或经验自行推断合规要求，只能依据 GB 30871-2022 的明文规定。",
        "",
        "请找出输入文本中确定存在的不合规项。",
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
        '- explanation字段：引用GB 30871-2022中真实存在的具体条款编号（如"第5.3.2条"），必须是标准中实际存在的条款，禁止编造。',
        "- suggested_fix字段：提出具体的整改建议",
        "- 若没有明确的违规证据，返回空的 issues 列表。绝对不要为了凑数量而报告不确定的问题。",
        "",
        "使用输入中提供的段落索引（如 [0], [1], ...）。",
        "按照要求的 JSON 格式输出结果。",
    ]
    return "\n".join(p for p in parts if p is not None) + "\n"


def _build_guidance(custom_rules: List[ReviewRule] | None = None, rule_documents: List[RuleDocument] | None = None) -> str:
    """Build supplementary guidance: exclusion rules, custom rules, and rule documents."""
    lines = [
        "注意：以下情况不算不合规，不要报告：",
        "- 日期和时间之间缺少空格、格式不统一等纯排版问题",
        "- 表格中列宽、对齐、字体大小等显示问题",
        "- 没有明确 GB 30871-2022 条款依据的疑似问题",
        "- 你凭经验认为可能不合适但没有标准条文支撑的情况",
        "- 只报告有明确标准条款支撑的实质性安全合规问题。",
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

    return "\n".join(lines)


class LangChainPipeline:
    def __init__(self) -> None:
        # Prefer LangChain v1 provider-based initialization for DeepSeek.
        # This avoids OpenAI "response_format" structured output features that DeepSeek may not support.
        self.llm = _init_deepseek_model()
        self.parser = PydanticOutputParser(pydantic_object=ReviewOutput)
        self.mineru = MinerUClient()

    async def stream_issues(
        self,
        pdf_path: str,
        user_id: str,
        timestamp_iso: str,
        custom_rules: List[ReviewRule] | None = None,
        rule_documents: List[RuleDocument] | None = None,
    ) -> AsyncGenerator[List[Issue], None]:
        """End-to-end: MinerU parse -> chunk -> LLM -> yield Issue list per chunk."""
        payload = await self.mineru.extract(Path(pdf_path))
        meta = payload.get("meta") if isinstance(payload, dict) else None
        paragraphs = self.mineru.to_paragraphs(payload)
        doc_name = Path(pdf_path).name
        logging.info(f"MinerU paragraphs extracted: {len(paragraphs)} for {doc_name}")
        if custom_rules:
            logging.info(f"Custom rules enabled: {[r.name for r in custom_rules]}")
        if settings.debug and paragraphs:
            logging.debug(f"MinerU paragraph sample: {paragraphs[0].get('content', '')[:200]}")
        if not paragraphs:
            raise RuntimeError("MinerU 解析结果中未提取到段落文本（可能是返回 JSON 结构变化或解析字段不匹配）。")

        page_sizes = _get_pdf_page_sizes(pdf_path)
        page_bbox_space = _get_page_bbox_space(paragraphs)
        layout = _load_mineru_layout(meta, Path(pdf_path).stem)

        chunks = self._chunk_paragraphs(paragraphs, settings.pagination)
        logging.info(f"Chunk count: {len(chunks)} (pagination={settings.pagination})")
        seen_texts = set()
        for chunk_index, chunk in enumerate(chunks):
            issues = await self._process_chunk(
                chunk,
                chunk_index,
                user_id,
                timestamp_iso,
                doc_name,
                pdf_path,
                page_sizes,
                page_bbox_space,
                layout,
                custom_rules,
                rule_documents,
            )
            if issues:
                # Deduplicate by issue text
                unique = []
                for issue in issues:
                    key = issue.text.strip()
                    if key not in seen_texts:
                        seen_texts.add(key)
                        unique.append(issue)
                    else:
                        logging.info(f"Dedup issue: {key[:80]}")
                if unique:
                    yield unique

    def _chunk_paragraphs(self, paragraphs: List[Dict[str, Any]], size: int) -> List[List[Dict[str, Any]]]:
        if size == -1:
            return [paragraphs]
        return [paragraphs[i : i + size] for i in range(0, len(paragraphs), size)]

    def _get_risk_level_for_type(
        self,
        issue_type: str,
        custom_rules: List[ReviewRule] | None = None
    ) -> RiskLevel:
        """
        根据问题类型确定风险等级。
        - 预设类型 "Definitive Language" -> 高
        - 预设类型 "Grammar & Spelling" -> 低
        - 自定义规则 -> 使用规则定义的风险等级
        - 未知类型 -> 中
        """
        # 预设类型的风险等级映射
        preset_risk_levels = {
            IssueType.DefinitiveLanguage.value: RiskLevel.high,
            "Definitive Language": RiskLevel.high,
            IssueType.GrammarSpelling.value: RiskLevel.low,
            "Grammar & Spelling": RiskLevel.low,
        }
        
        # 先检查预设类型
        if issue_type in preset_risk_levels:
            return preset_risk_levels[issue_type]
        
        # 检查自定义规则
        if custom_rules:
            for rule in custom_rules:
                if rule.name == issue_type:
                    return rule.risk_level
        
        # 默认返回中等风险
        return RiskLevel.medium

    async def _process_chunk(
        self,
        chunk: List[Dict[str, Any]],
        chunk_index: int,
        user_id: str,
        timestamp_iso: str,
        doc_name: str,
        pdf_path: str,
        page_sizes: Dict[int, tuple[float, float]],
        page_bbox_space: Dict[int, Dict[str, Any]],
        layout: Dict[str, Any] | None,
        custom_rules: List[ReviewRule] | None = None,
        rule_documents: List[RuleDocument] | None = None,
    ) -> List[Issue]:
        prepared = "\n".join([f"[{i}]{p['content']}" for i, p in enumerate(chunk)])

        # Build dynamic prompts with custom rules
        system_prompt = _build_system_prompt(custom_rules, rule_documents)
        guidance = _build_guidance(custom_rules, rule_documents)

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(
                content=(
                    f"Chunk {chunk_index}. Paragraphs with indices:\n{prepared}\n\n"
                    f"{guidance}\n"
                    "Return issues; if none, return an empty list.\n\n"
                    f"{self.parser.get_format_instructions()}"
                )
            ),
        ]

        try:
            resp = await self.llm.ainvoke(messages)
            content = resp.content if hasattr(resp, "content") else resp
            if isinstance(content, list):
                content = "".join(
                    [c.get("text", "") if isinstance(c, dict) else str(c) for c in content]
                )
            # Log Agent 1 raw response
            logging.info(f"Agent 1 raw response length: {len(str(content))} chars")
            logging.info(f"Agent 1 response preview: {str(content)[:500]}")
            # Parse using PydanticOutputParser (no provider-side response_format).
            out = self.parser.parse(str(content))
            raw_issues = out.issues
            logging.info(f"Agent 1 parsed {len(raw_issues)} issues")
        except Exception as e:
            logging.error(f"LLM output parse failed: {e}")
            return []

        # === Highlight positioning via semantic search (no Agent 2 LLM call) ===
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

            bbox_list, actual_page = find_highlight_quadpoints(
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
                bbox_list = [fb]
            # Flatten all quadpoints groups into one bounding_box list
            # Format: [qp1_0..qp1_7, qp2_0..qp2_7, ...] (each group is 8 floats)
            flat_bbox = []
            for qp in bbox_list:
                flat_bbox.extend(qp)
            # Use LLM's original_text (exact quote) for source_sentence, fallback to paragraph
            source_text = raw.original_text if isinstance(raw, ReviewIssue) and raw.original_text else para["content"]
            location = Location(
                source_sentence=source_text,
                page_num=page_num,
                bounding_box=flat_bbox,
                para_index=para_index,
            )

            issues.append(
                Issue(
                    id=str(uuid.uuid4()),
                    doc_id=doc_name,
                    text=(raw.text if isinstance(raw, ReviewIssue) else para["content"][:120]),
                    type=issue_type,
                    status=IssueStatusEnum.not_reviewed,
                    suggested_fix=(raw.suggested_fix if isinstance(raw, ReviewIssue) else ""),
                    explanation=(raw.explanation if isinstance(raw, ReviewIssue) else ""),
                    risk_level=risk_level,
                    location=location,
                    review_initiated_by=user_id,
                    review_initiated_at_UTC=timestamp_iso,
                )
            )

        return issues


def _get_pdf_page_sizes(pdf_path: str) -> Dict[int, tuple[float, float]]:
    """Returns PDF page (width,height) in points, keyed by 1-based page number."""
    sizes: Dict[int, tuple[float, float]] = {}
    try:
        doc = fitz.open(pdf_path)
        for i in range(doc.page_count):
            page = doc.load_page(i)
            rect = page.rect
            sizes[i + 1] = (float(rect.width), float(rect.height))
        doc.close()
    except Exception as e:
        logging.warning(f"Unable to read PDF page sizes for bbox conversion: {e}")
    return sizes


def _get_page_bbox_space(paragraphs: List[Dict[str, Any]]) -> Dict[int, Dict[str, Any]]:
    """
    Compute bbox coordinate space per page.
    Prefer explicit canvas_size (pixel dimensions) if available from MinerU zip.
    """
    space_by_page: Dict[int, Dict[str, Any]] = {}
    for p in paragraphs:
        try:
            page_num = int(p.get("page_num", 1) or 1)
            canvas = p.get("canvas_size")
            if isinstance(canvas, (list, tuple)) and len(canvas) == 2:
                w, h = float(canvas[0]), float(canvas[1])
                if w > 0 and h > 0:
                    space_by_page[page_num] = {"observed_max": (w, h), "is_canvas": True}
                    continue

            bbox = p.get("bbox")
            if not bbox or not isinstance(bbox, list):
                continue
            if len(bbox) == 4:
                x1, y1, x2, y2 = [float(v) for v in bbox]
                mx = max(x1, x2)
                my = max(y1, y2)
            elif len(bbox) >= 8:
                coords = [float(v) for v in bbox[:8]]
                xs = coords[0::2]
                ys = coords[1::2]
                mx = max(xs)
                my = max(ys)
            else:
                continue
            cur = space_by_page.get(page_num, {}).get("observed_max")
            if not cur:
                space_by_page[page_num] = {"observed_max": (mx, my), "is_canvas": False}
            else:
                space_by_page[page_num]["observed_max"] = (max(cur[0], mx), max(cur[1], my))
        except Exception:
            continue
    if settings.debug:
        for pn, info in sorted(space_by_page.items())[:5]:
            mx, my = info.get("observed_max", (None, None))
            logging.debug(f"MinerU bbox space page {pn}: max=({mx}, {my}), canvas={info.get('is_canvas')}")
    return space_by_page


def _find_pdf_quadpoints(
    pdf_path: str,
    page_num: int,
    *,
    needle: str | None,
    fallback_sentence: str | None,
) -> List[float] | None:
    """
    Best-effort: use PDF text coordinates for accurate highlights.
    - If PDF has real text layer, PyMuPDF can locate text and return rectangles.
    - Returns quadpoints in PDF bottom-left coordinate space (annotpdf compatible), can include 8*n coords.
    """
    try:
        doc = fitz.open(pdf_path)
        if page_num < 1 or page_num > doc.page_count:
            doc.close()
            return None
        page = doc.load_page(page_num - 1)
        page_h = float(page.rect.height)

        candidates: list[str] = []
        if needle:
            candidates.append(needle.strip())
        if fallback_sentence:
            candidates.append(str(fallback_sentence).strip())
        # Also try removing spaces for CJK PDFs where extraction may omit spaces
        candidates.extend([c.replace(" ", "") for c in candidates if " " in c])

        rects: list[fitz.Rect] = []
        for c in candidates:
            if not c:
                continue
            rects = page.search_for(c)
            if rects:
                break

        # If still nothing, try a shorter needle (first 12 chars) to improve hit rate
        if not rects and needle:
            short = needle.strip()
            if len(short) > 12:
                rects = page.search_for(short[:12])

        doc.close()
        if not rects:
            return None

        # Convert rects (top-left origin) to PDF quadpoints (bottom-left origin).
        # Allow multi-quad highlights (8*n).
        quadpoints: list[float] = []
        for r in rects[:6]:
            x0, y0, x1, y1 = float(r.x0), float(r.y0), float(r.x1), float(r.y1)
            quadpoints.extend(
                [
                    x0,
                    page_h - y0,
                    x1,
                    page_h - y0,
                    x0,
                    page_h - y1,
                    x1,
                    page_h - y1,
                ]
            )
        return [round(v, 2) for v in quadpoints]
    except Exception:
        return None


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


def _init_deepseek_model():
    """
    Initialize chat model via ChatOpenAI (OpenAI-compatible).
    Works with DeepSeek, DashScope/Qwen, or any OpenAI-compatible endpoint.
    Uses DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL from settings/.env.
    """
    logging.info(
        f"Initializing LLM: base_url={settings.deepseek_base_url}, "
        f"model={settings.deepseek_model}"
    )
    return ChatOpenAI(
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
        model=settings.deepseek_model,
        temperature=0.2,
    )


def _load_mineru_layout(meta: Dict[str, Any] | None, pdf_stem: str) -> Dict[str, Any] | None:
    """
    Load MinerU layout.json (line/span-level bboxes) for better highlights on PDFs without text layer.
    Prefer cached `layout_path` from MinerU meta; fall back to cache dir lookup.
    """
    try:
        layout_path = None
        if isinstance(meta, dict):
            lp = meta.get("layout_path")
            if isinstance(lp, str) and lp:
                layout_path = Path(lp)
        if not layout_path:
            cache_key = None
            if isinstance(meta, dict):
                ck = meta.get("cache_key")
                if isinstance(ck, str) and ck:
                    cache_key = ck
            if not cache_key:
                cache_key = "".join([c if c.isalnum() or c in ("-", "_") else "_" for c in pdf_stem])
            layout_path = Path(settings.mineru_cache_dir) / f"{cache_key}.layout.json"
        if not layout_path.exists():
            return None
        return json.loads(layout_path.read_text(encoding="utf-8"))
    except Exception as e:
        logging.warning(f"Failed to load MinerU layout: {e}")
        return None


def _normalize_for_match(text: str) -> str:
    return (
        text.replace("\u3000", " ")
        .replace("\r", "")
        .replace("\n", "")
        .replace("\t", "")
        .strip()
    )


def _char_weight(ch: str) -> float:
    """计算字符的相对宽度权重，用于估算子串在行内的位置"""
    if not ch:
        return 0.0
    if ch.isspace():
        return 0.3
    o = ord(ch)
    # CJK 字符（中文、日文、韩文）占用更多宽度
    if 0x4E00 <= o <= 0x9FFF or 0x3400 <= o <= 0x4DBF:  # CJK Unified Ideographs
        return 1.0
    if 0x3000 <= o <= 0x303F:  # CJK Symbols and Punctuation
        return 1.0
    if 0xFF00 <= o <= 0xFFEF:  # Fullwidth Forms
        return 1.0
    if o < 128:  # ASCII
        return 0.55
    return 0.8


def _substring_bbox_from_line(line_text: str, line_bbox: list[float], start: int, end: int) -> list[float] | None:
    """基于字符权重计算子串在行内的精确 bbox"""
    if not line_bbox or len(line_bbox) != 4:
        return None
    x0, y0, x1, y1 = [float(v) for v in line_bbox]
    if x1 <= x0 or y1 <= y0:
        return None
    if start < 0 or end <= start or end > len(line_text):
        return None

    weights = [_char_weight(c) for c in line_text]
    total = sum(weights) or float(len(line_text))
    prefix = [0.0]
    for w in weights:
        prefix.append(prefix[-1] + w)

    a = prefix[start] / total
    b = prefix[end] / total
    sx0 = x0 + (x1 - x0) * a
    sx1 = x0 + (x1 - x0) * b

    # 确保最小宽度
    min_width = (x1 - x0) * 0.02  # 至少占行宽的 2%
    if sx1 - sx0 < min_width:
        mid = (sx0 + sx1) / 2.0
        sx0 = max(x0, mid - min_width / 2)
        sx1 = min(x1, mid + min_width / 2)

    return [round(sx0, 2), round(y0, 2), round(sx1, 2), round(y1, 2)]


def _find_span_match(
    spans: list[dict],
    needle: str,
    line_bbox: list[float],
) -> tuple[list[float] | None, float]:
    """
    在 spans 中查找精确匹配，返回 (bbox, score)。
    优先匹配单个 span，然后尝试跨 span 匹配。
    """
    if not spans or not needle:
        return None, 0.0

    needle_norm = _normalize_for_match(needle)
    needle_ns = needle_norm.replace(" ", "")

    # 1. 尝试在单个 span 中精确匹配
    for span in spans:
        if not isinstance(span, dict):
            continue
        content = str(span.get("content", ""))
        span_bbox = span.get("bbox")
        if not content or not isinstance(span_bbox, list) or len(span_bbox) != 4:
            continue

        content_norm = _normalize_for_match(content)

        # 完全匹配
        if content_norm == needle_norm:
            return span_bbox, 1.0

        # 子串匹配
        idx = content_norm.find(needle_norm)
        if idx >= 0:
            sub_bbox = _substring_bbox_from_line(content_norm, span_bbox, idx, idx + len(needle_norm))
            return sub_bbox or span_bbox, 0.95

        # 无空格匹配
        content_ns = content_norm.replace(" ", "")
        if needle_ns in content_ns:
            return span_bbox, 0.9

    # 2. 尝试跨 span 匹配 - 拼接所有 span 内容
    full_text = ""
    span_ranges = []  # [(start, end, span_bbox), ...]
    for span in spans:
        if not isinstance(span, dict):
            continue
        content = str(span.get("content", ""))
        span_bbox = span.get("bbox")
        if content and isinstance(span_bbox, list) and len(span_bbox) == 4:
            start = len(full_text)
            full_text += content
            span_ranges.append((start, len(full_text), span_bbox))

    full_norm = _normalize_for_match(full_text)
    idx = full_norm.find(needle_norm)
    if idx >= 0:
        # 找到匹配，计算覆盖的 span 范围
        match_end = idx + len(needle_norm)
        covered_bboxes = []
        for start, end, bbox in span_ranges:
            if start < match_end and end > idx:
                covered_bboxes.append(bbox)
        if covered_bboxes:
            # 合并覆盖的 bbox
            min_x = min(b[0] for b in covered_bboxes)
            min_y = min(b[1] for b in covered_bboxes)
            max_x = max(b[2] for b in covered_bboxes)
            max_y = max(b[3] for b in covered_bboxes)
            return [min_x, min_y, max_x, max_y], 0.85

    return None, 0.0


def _find_layout_quadpoints(
    layout: Dict[str, Any] | None,
    page_num: int,
    *,
    page_size_points: tuple[float, float] | None,
    needle: str | None,
    fallback_sentence: str | None,
) -> List[float] | None:
    """
    使用 MinerU layout.json 的 span 级别 bbox 生成精确的 quadpoints。
    优先在 span 级别匹配，然后回退到行级别。
    """
    if not layout or not isinstance(layout, dict) or not page_size_points:
        return None
    pdf_info = layout.get("pdf_info")
    if not isinstance(pdf_info, list) or page_num < 1:
        return None

    page_obj = next((p for p in pdf_info if isinstance(p, dict) and int(p.get("page_idx", -1)) == page_num - 1), None)
    if not page_obj:
        return None

    page_size_px = page_obj.get("page_size")
    if not isinstance(page_size_px, (list, tuple)) or len(page_size_px) != 2:
        return None
    observed_max = (float(page_size_px[0]), float(page_size_px[1]))

    blocks = page_obj.get("para_blocks") or []
    if not isinstance(blocks, list):
        return None

    candidates = []
    if needle:
        candidates.append(str(needle))
    if fallback_sentence:
        candidates.append(str(fallback_sentence))
    candidates = [c for c in candidates if c and c.strip()]
    if not candidates:
        return None

    best_bbox = None
    best_score = 0.0

    # 1. 优先在 span 级别精确匹配
    for cand in candidates:
        for b in blocks:
            if not isinstance(b, dict):
                continue
            for ln in b.get("lines") or []:
                if not isinstance(ln, dict):
                    continue
                spans = ln.get("spans") or []
                line_bbox = ln.get("bbox") or b.get("bbox")
                if not isinstance(spans, list) or not line_bbox:
                    continue

                bbox, score = _find_span_match(spans, cand, line_bbox)
                if score > best_score:
                    best_score = score
                    best_bbox = bbox

                if best_score >= 0.95:
                    break
            if best_score >= 0.95:
                break
        if best_score >= 0.95:
            break

    # 2. 如果 span 匹配不够好，回退到行级别匹配
    if best_score < 0.7:
        lines: list[dict[str, Any]] = []
        for b in blocks:
            if not isinstance(b, dict):
                continue
            for ln in b.get("lines") or []:
                if not isinstance(ln, dict):
                    continue
                spans = ln.get("spans") or []
                if not isinstance(spans, list):
                    continue
                text = "".join([str(s.get("content", "")) for s in spans if isinstance(s, dict)])
                bbox = ln.get("bbox") or b.get("bbox")
                if not text or not isinstance(bbox, list) or len(bbox) != 4:
                    continue
                lines.append({"text": text, "bbox": bbox})

        for cand in candidates:
            cand_norm = _normalize_for_match(cand)
            cand_norm_ns = cand_norm.replace(" ", "")
            for line in lines:
                line_text = str(line["text"])
                line_bbox = line["bbox"]
                line_norm = _normalize_for_match(line_text)

                # 精确子串匹配
                idx = line_norm.find(cand_norm)
                if idx >= 0:
                    bbox_px = _substring_bbox_from_line(line_norm, line_bbox, idx, idx + len(cand_norm)) or line_bbox
                    if 0.85 > best_score:
                        best_bbox = bbox_px
                        best_score = 0.85
                    break

                # 无空格匹配
                line_ns = line_norm.replace(" ", "")
                if cand_norm_ns in line_ns:
                    if 0.75 > best_score:
                        best_bbox = line_bbox
                        best_score = 0.75
                    break

            if best_score >= 0.85:
                break

    # 3. 模糊匹配回退
    if best_score < 0.55 and needle:
        lines = []
        for b in blocks:
            if not isinstance(b, dict):
                continue
            for ln in b.get("lines") or []:
                if not isinstance(ln, dict):
                    continue
                spans = ln.get("spans") or []
                text = "".join([str(s.get("content", "")) for s in spans if isinstance(s, dict)])
                bbox = ln.get("bbox") or b.get("bbox")
                if text and isinstance(bbox, list) and len(bbox) == 4:
                    lines.append({"text": text, "bbox": bbox})

        cand_norm = _normalize_for_match(str(needle))
        for line in lines:
            line_norm = _normalize_for_match(str(line["text"]))
            ratio = SequenceMatcher(a=cand_norm, b=line_norm).ratio() if cand_norm and line_norm else 0.0
            if ratio > best_score:
                best_score = ratio
                best_bbox = line["bbox"]

        if best_score < 0.55:
            best_bbox = None

    if not best_bbox:
        return None

    if settings.debug:
        logging.debug(f"Layout match: score={best_score:.2f}, bbox={best_bbox}, needle={needle[:30] if needle else None}...")

    return bbox_to_quadpoints(
        best_bbox,
        page_size_points,
        origin="top-left",
        units="px",
        observed_max=observed_max,
        content_coverage=1.0,
    )
