"""
作业票业务逻辑层。

核心流程：上传 PDF → MinerU 解析 → LLM 结构化提取 → 前端确认 → 入库。
"""

from __future__ import annotations

import asyncio
import base64
import httpx
import json
import os
import re
import shutil
import tempfile
import time
import uuid
from io import BytesIO
from pathlib import Path

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from config.config import settings
from common.llm_utils import build_llm
from database.mysql_client import MysqlClient
from database.permits_repository import PermitsRepository
from services.mineru_client import MinerUClient
from services.permit_types import get_permit_type, list_permit_types
from common.permit_models import (
    ExtractedSafetyCheck,
    HotWorkPermit,
    HotWorkGasAnalysis,
    PermitUploadResponse,
)
from common.logger import get_logger
from common.llm_utils import extract_llm_content, strip_code_fences, llm_invoke_json

logger = get_logger(__name__)

# ─────────────── LLM 提取 prompt ───────────────


# ─────────────── Prompt loader ───────────────

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


def _load_prompt(permit_type: str, task: str) -> str:
    """Load a prompt file: prompts/{permit_type}_{task}.md"""
    path = _PROMPTS_DIR / f"{permit_type}_{task}.md"
    if not path.is_file():
        raise FileNotFoundError(f"Prompt file not found: {path}")
    return path.read_text(encoding="utf-8")


# ─────────────── 加载 GB 30871-2022 标准原文 ───────────────

_GB_STANDARD_TEXT: str | None = None


def _load_gb_standard() -> str:
    """加载 GB 30871-2022 标准原文（MD 格式），作为 wiki 的 fallback。"""
    global _GB_STANDARD_TEXT
    if _GB_STANDARD_TEXT is not None:
        return _GB_STANDARD_TEXT
    # 标准文件路径：项目根目录下的标准文件
    candidates = [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'GB_30871-2022危险化学品企业特殊作业安全规范.md')
    ]
    for p in candidates:
        p = os.path.normpath(p)
        if os.path.isfile(p):
            with open(p, 'r', encoding='utf-8') as f:
                _GB_STANDARD_TEXT = f.read()
            logger.info(f"Loaded GB 30871-2022 standard from {p}, length={len(_GB_STANDARD_TEXT)}")
            return _GB_STANDARD_TEXT
    logger.warning("GB 30871-2022 standard file not found, compliance review will use prompt rules only")
    _GB_STANDARD_TEXT = ""
    return _GB_STANDARD_TEXT


class PermitsService:
    def __init__(self, repo: PermitsRepository):
        self._repo = repo
        self._mineru = MinerUClient()
        self._llm = self._init_llm()
        self._vision_llm = self._init_vision_llm()


    def _init_vision_llm(self) -> ChatOpenAI:
        # 视觉模型 (PDF 图片) - 走 build_llm 统一工厂 (ollama 禁思考 / 温度 0.2)
        if not settings.llm_vision_model:
            return None
        return build_llm(
            model=settings.llm_vision_model,
            temperature=0.1,
        )

    def _init_llm(self) -> ChatOpenAI:
        # 走 build_llm 统一工厂, ollama qwen3.6 思考过程被禁掉
        return build_llm(
            model=settings.llm_model,
            temperature=0.1,
            max_tokens=3000,  # JSON extraction: 3000 tokens 够完整生成 permit 字段 (之前 1500 时 done=length 缺字段)
        )


    async def _extract_local_mineru(self, file_bytes: bytes, filename: str) -> str:
        """
        Call local MinerU (Docker container `mineru-openai-server`) via the
        `mineru` CLI in vlm-http-client mode and return markdown text.

        Flow:
          1. Stage a unique work dir under /tmp, copy the PDF into the
             `mineru-openai-server` container at /work/input/<stem>/<file>
          2. Run `mineru -p <input> -o <output> -b vlm-http-client
                            -u http://localhost:30000` inside the container
             (this hits the in-container vLLM EngineCore serving
              OpenDataLab/MinerU2___5-Pro-2604-1___2B on port 30000)
          3. mineru writes <output>/<stem>/<stem>.md (and an `auto/` subdir
             with layout.json etc.). Copy it back to the host and read.
        """
        # 1) Stage files -----------------------------------------------------
        run_id = uuid.uuid4().hex[:12]
        stem = Path(filename).stem or "document"
        # Sanitize stem so it only contains [A-Za-z0-9_-]
        safe_stem = re.sub(r"[^A-Za-z0-9_-]", "_", stem)[:64] or "document"
        host_tmp = Path(tempfile.gettempdir()) / f"mineru_{run_id}_{safe_stem}"
        host_input_dir = host_tmp / "input"
        host_output_dir = host_tmp / "output"
        host_input_dir.mkdir(parents=True, exist_ok=True)
        host_output_dir.mkdir(parents=True, exist_ok=True)

        # Use a sanitized filename inside the container to avoid shell quoting issues
        safe_filename = f"{safe_stem}{Path(filename).suffix.lower() or '.pdf'}"
        host_input_file = host_input_dir / safe_filename
        host_input_file.write_bytes(file_bytes)

        container_name = "mineru-openai-server"
        container_input = f"/work/input/{safe_filename}"
        container_output = "/work/output"
        server_url = (settings.mineru_local_url or "http://localhost:30000").rstrip("/")

        logger.info(
            f"Local MinerU: container={container_name} backend=vlm-http-client "
            f"server={server_url} file={safe_filename}"
        )

        t0 = time.time()

        # 2) Copy input file into the container -------------------------------
        proc = await asyncio.create_subprocess_exec(
            "docker", "cp", str(host_input_file), f"{container_name}:{container_input}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, err = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(
                f"docker cp input failed (rc={proc.returncode}): "
                f"{err.decode(errors='replace').strip()[:300]}"
            )

        # 3) Clean any stale output for this stem ----------------------------
        await asyncio.create_subprocess_exec(
            "docker", "exec", container_name, "rm", "-rf",
            f"{container_output}/{safe_stem}",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.create_subprocess_exec(
            "docker", "exec", container_name, "mkdir", "-p", container_output,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )

        # 4) Run mineru CLI inside the container ------------------------------
        # Note: vlm-http-client means mineru itself is the client that
        # POSTs to the in-container vLLM server. This is the highest-
        # quality path (formulas/LaTeX, tables as Markdown, image
        # captions) — ~43s for typical hot-work permit PDFs.
        mineru_cmd = [
            "docker", "exec", container_name,
            "mineru",
            "-p", container_input,
            "-o", container_output,
            "-b", "vlm-http-client",
            "-u", server_url,
        ]
        logger.info(f"Running: {' '.join(mineru_cmd)}")
        try:
            proc = await asyncio.create_subprocess_exec(
                *mineru_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=900
            )
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except Exception:
                pass
            raise RuntimeError("Local MinerU parse timeout (900s)")

        elapsed = time.time() - t0
        if proc.returncode != 0:
            tail = (stderr or b"").decode(errors="replace").strip().splitlines()[-12:]
            raise RuntimeError(
                f"Local MinerU parse failed (rc={proc.returncode}, "
                f"elapsed={elapsed:.1f}s): {' | '.join(tail)[:600]}"
            )

        # 5) Copy result dir back from the container -------------------------
        # mineru 3.1.0 in vlm-http-client mode writes to:
        #   /work/output/<stem>/<stem>.md   (and <stem>/auto/...)
        container_result_dir = f"{container_output}/{safe_stem}"
        host_result_dir = host_output_dir / safe_stem
        host_result_dir.mkdir(parents=True, exist_ok=True)

        proc = await asyncio.create_subprocess_exec(
            "docker", "cp",
            f"{container_name}:{container_result_dir}/.",
            str(host_result_dir) + "/",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, err = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(
                f"docker cp result failed (rc={proc.returncode}): "
                f"{err.decode(errors='replace').strip()[:300]}"
            )

        # 6) Find the .md (prefer the top-level one mineru 3.1 writes) -------
        md_candidates = sorted(host_result_dir.rglob("*.md"))
        if not md_candidates:
            # List contents for debugging
            contents = [str(p.relative_to(host_result_dir)) for p in host_result_dir.rglob("*")]
            raise RuntimeError(
                f"Local MinerU produced no .md file. Output dir contents: "
                f"{contents[:20]}"
            )

        # Prefer the md whose name matches the input stem (the canonical one)
        primary = next(
            (p for p in md_candidates if p.stem == safe_stem),
            md_candidates[0],
        )
        md_text = primary.read_text(encoding="utf-8", errors="replace")
        logger.info(
            f"Local MinerU done in {elapsed:.1f}s, "
            f"md={primary.relative_to(host_output_dir)} length={len(md_text)}"
        )

        # 7) Best-effort cleanup ---------------------------------------------
        try:
            shutil.rmtree(host_tmp, ignore_errors=True)
        except Exception:
            pass
        await asyncio.create_subprocess_exec(
            "docker", "exec", container_name, "rm", "-rf",
            container_input, container_result_dir,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )

        return md_text


    async def _extract_from_image(self, image_bytes: bytes, filename: str, permit_type: str) -> tuple[dict, str, list]:
        """
        提取结构化数据 from 图片 (OCR + LLM 双层).

        Returns:
            (extracted_dict, permit_type, warnings_list)

        流程 (2026-06-10 新加):
          [1] PIL 压图 2MB → 500KB (防 glm-ocr vision encoder 慢)
          [2] glm-ocr OCR 跑图 → 纯文本 markdown
          [3] OCR 自动检测 permit_type, 覆盖前端传的 (前端 bug 兜底)
          [4] qwen3.6:35b 拿 OCR 文本 + per-type extract 模板 → JSON

        之前是 vision LLM 单层 (qwen3-vl 5.7B), 2MB 图要 200-300s 超时
        现在 OCR + LLM 双层, 200KB 图 glm-ocr 5-30s, LLM 10-30s, 总 15-60s

        Returns:
            (extracted_dict, actual_permit_type) - 实际用的 permit_type (OCR 检测的)
        """
        ext = Path(filename).suffix.lower()
        mime_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}
        mime = mime_map.get(ext, "image/jpeg")
        logger.info(f"Image extract start: {filename}, size={len(image_bytes)}, mime={mime}, permit_type={permit_type}")

        # [1] 压图 (防 glm-ocr 编码慢, 2MB→500KB)
        compressed_bytes, compressed_mime = self._compress_image_for_ocr(image_bytes, mime, max_size_kb=500, max_dim=1024)
        logger.info(f"Image compressed: {len(image_bytes)} -> {len(compressed_bytes)} bytes ({(len(compressed_bytes) / max(len(image_bytes), 1) * 100):.0f}%)")

        # [2] glm-ocr OCR 跑图 → 纯文本 markdown
        b64 = base64.b64encode(compressed_bytes).decode()
        ocr_prompt = (
            "你是一个专业的 OCR 助手。请仔细识别图片中所有文字内容 (包括标题、表格、签名、印章、勾选框等), "
            "保留原始的层级和布局, 用 markdown 表格 + 列表形式输出。\n"
            "重要要求:\n"
            "1. 表格用 markdown 表格语法 (|---|) 保留行列结构\n"
            "2. 勾选框用 [✓] 表示已勾选, [ ] 表示未勾选\n"
            "3. 签名栏直接写出可见的姓名文字 (看不清写 null)\n"
            "4. 印章内容用 [印章: XXX] 表示\n"
            "5. 不要做任何总结或解释, 只输出 OCR 识别出的原文\n"
            "6. ⚠️ 去重: 作业票底部经常有『安全措施/安全制度/安全交底』列表 (1-20 条), "
            "识别出后**只输出你实际看到的内容, 禁止编造或重复**. "
            "如果你看不清某条, 直接跳过, 不要因为上下文一致就补一条相同的."
        )
        ocr_messages = [
            SystemMessage(content=ocr_prompt),
            HumanMessage(content=[
                {"type": "image_url", "image_url": {"url": f"data:{compressed_mime};base64,{b64}"}},
                {"type": "text", "text": "请 OCR 识别这张图片。"},
            ]),
        ]
        try:
            ocr_resp = await self._vision_llm.ainvoke(ocr_messages)
            ocr_text = extract_llm_content(ocr_resp)
            logger.info(f"OCR done: {len(ocr_text)} chars")
        except Exception as e:
            logger.error(f"OCR failed: {e}")
            ocr_text = ""

        # [3] qwen3.6:35b 拿 OCR 文本 + per-type extract 模板 → JSON
        if not ocr_text or len(ocr_text) < 20:
            # OCR 失败 / 太短, 走 vision LLM 单层 fallback
            logger.warning("OCR result too short, falling back to vision LLM direct")
            fallback_result = await self._extract_from_image_vision_fallback(compressed_bytes, compressed_mime, permit_type)
            return fallback_result, permit_type, []

        # [3.0] OCR 自动检测 permit_type (前端 bug 兜底)
        # 2026-06-11: 用户要求"选的什么就用什么", 不再 OCR 兜底覆盖
        # 检测到 mismatch 只 warning, 不动 permit_type
        # OCR 检测函数保留 (以后 debug / 校验 用)
        detected_type = self._detect_permit_type_from_ocr(ocr_text)
        if detected_type and detected_type != permit_type:
            logger.warning(
                f"Permit type mismatch detected (NOT overriding): frontend says '{permit_type}', "
                f"OCR detected '{detected_type}', using frontend value '{permit_type}'"
            )
        elif not detected_type:
            logger.debug(f"OCR could not detect permit type, using frontend value '{permit_type}'")

        # [用户要求 2026-06-11] OCR 文本检测到与前端选择不一致, 返警告给前端
        # 不修改响应字段, 只附加 _warnings 让前端展示
        warnings = []
        if detected_type and detected_type != permit_type:
            warnings.append({
                "type": "permit_type_mismatch",
                "level": "warning",
                "message": f"前端选择 {permit_type}, 但作业票内容看起来是 {detected_type}, 请确认图片是否正确",
                "frontend_type": permit_type,
                "ocr_detected_type": detected_type,
            })

        extract_prompt = _load_prompt(permit_type, "extract_image")
        # 模板说"图片", 但 LLM 实际拿到 OCR 文本, 替换说明
        extract_prompt = extract_prompt.replace("【图片】", "【OCR 文本】")
        extract_prompt = extract_prompt.replace("【图片】", "【OCR 文本】")  # 双重保险
        # 加 OCR 文本作为上下文
        full_prompt = f"{extract_prompt}\n\n## OCR 识别出的作业票文本 (markdown 格式)\n\n{ocr_text}"
        struct_messages = [
            SystemMessage(content=full_prompt),
            HumanMessage(content="请从上述 OCR 文本中提取所有结构化数据, 输出严格的 JSON。"),
        ]
        try:
            resp = await self._llm.ainvoke(struct_messages)
            raw = extract_llm_content(resp)
            raw = strip_code_fences(raw)
            return json.loads(raw), permit_type, warnings
        except json.JSONDecodeError as e:
            logger.error(f"LLM extraction json parse failed: {e}, raw[:500]={raw[:500]}")
            # LaTeX 容错 (_try_fix_latex_escape 在 common.llm_utils)
            from common.llm_utils import _try_fix_latex_escape
            try:
                fixed = _try_fix_latex_escape(raw)
                obj = json.loads(fixed)
                return obj, permit_type, warnings
            except Exception as e2:
                logger.error(f"LLM extraction failed after LaTeX fix: {e2}")
                return {"permit_code": Path(filename).stem, "raw_llm_output": raw}, permit_type, warnings
                pass
            return {"permit_code": Path(filename).stem, "raw_llm_output": raw}, permit_type, warnings
        except Exception as e:
            logger.error(f"LLM extraction failed: {e}")
            return {"permit_code": Path(filename).stem, "raw_llm_output": str(e)}, permit_type, warnings

    async def _extract_from_image_vision_fallback(self, image_bytes: bytes, mime: str, permit_type: str) -> dict:
        """
        OCR 失败时的 fallback: 直接调 vision LLM (qwen3-vl 5.7B), 用 extract 模板
        比 OCR+LLM 慢 5-10x, 但 OCR 失败时不至于 0 数据
        """
        logger.warning(f"Using vision LLM fallback, mime={mime}")
        b64 = base64.b64encode(image_bytes).decode()
        extract_prompt = _load_prompt(permit_type, "extract")
        full_prompt = f"{extract_prompt}\n\n## 输入\n作业票图片 OCR 文本 (空, 走 vision LLM 模式): 本图通过 vision LLM 直接看图提取, 不依赖 OCR 预处理。"
        messages = [
            SystemMessage(content=full_prompt),
            HumanMessage(content=[
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                {"type": "text", "text": "请从这张作业票图片中提取所有结构化数据, 输出 JSON。"},
            ]),
        ]
        try:
            resp = await self._vision_llm.ainvoke(messages)
            raw = extract_llm_content(resp)
            raw = strip_code_fences(raw)
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"permit_code": "", "raw_llm_output": raw[:500]}
        except Exception as e:
            logger.error(f"Vision LLM fallback failed: {e}")
            return {"permit_code": "", "raw_llm_output": str(e)}

    def _detect_permit_type_from_ocr(self, ocr_text: str) -> str | None:
        """
        从 OCR 文本里检测作业票类型 (前端 bug 兜底).

        背景: 2026-06-10 实测前端 useState default = "hot_work", 即使用户选"受限空间",
             URL 仍可能传 hot_work. 后端 log: `permit_type=hot_work` + 文件名"受限空间作业票.png".
             结果 LLM 用动火模板跑受限空间作业票, 字段是动火的 (动火人/动火地点/动火级别),
             完全不对.

        修法: 后端从 OCR 文本里检测关键词, 覆盖前端传错的 permit_type.

        关键词 (按权重排序, 多个关键词同时匹配时按优先级):
          - "受限空间"        → confined_space  (GB 30871 附录 B)
          - "动火"            → hot_work  (GB 30871 附录 A)
          - "高处"            → high_above  (GB 30871 附录 D)
          - "吊装"            → lifting  (GB 30871 附录 F)
          - "临时用电"        → temp_power  (GB 30871 附录 E)
          - "盲板抽堵"        → blind_plate  (GB 30871 附录 C)
          - "动土"            → earthwork  (GB 30871 附录 G)
          - "断路"            → road_closure  (GB 30871 附录 H)

        Args:
            ocr_text: glm-ocr 识别出的纯文本 (2564 字符左右)

        Returns:
            permit_type 字符串 (e.g. "confined_space") 或 None (检测不到)
        """
        if not ocr_text:
            return None

        # 优先长关键词 (避免"动火"被"动火点"等子串误匹配, "临时用电"避免"临时"误匹配)
        priority_keywords = [
            ("受限空间", "confined_space"),
            ("临时用电", "temp_power"),
            ("盲板抽堵", "blind_plate"),
            ("高处", "high_above"),       # 单独的"高处"字符串
            ("吊装", "lifting"),
            ("动火", "hot_work"),
            ("动土", "earthwork"),
            ("断路", "road_closure"),
        ]
        # 注意: 关键词长度从长到短排, "受限空间" (4字符) 优先于 "动火" (2字符)
        priority_keywords.sort(key=lambda x: -len(x[0]))

        # 同时出现的关键词, 记录
        matches = []
        for keyword, ptype in priority_keywords:
            if keyword in ocr_text:
                matches.append(ptype)

        if not matches:
            return None
        if len(matches) == 1:
            return matches[0]
        # 多个匹配, 取**最优先**的 (按 priority_keywords 顺序)
        # 也就是说"高处" + "吊装" 出现, 取先匹配的那个
        for _, ptype in priority_keywords:
            if ptype in matches:
                return ptype
        return matches[0]

    def _compress_image_for_ocr(self, image_bytes: bytes, mime: str, max_size_kb: int = 200, max_dim: int = 1024) -> tuple[bytes, str]:
        """
        压图给 OCR 用, 防 glm-ocr vision encoder 编码慢.

        经验 (实测 2026-06-10 ~ 11):
          - glm-ocr 1.1B (旧): 130KB 5.7s 跑通, 406KB 编码 304s 超时, 2MB 编码 339s 超时
            编码时间跟像素数 强相关, 跟文件大小 关系小
          - glm-ocr-fix 1.1B (新, 2026-06-11): 用户测试 1024px 800+ 字符 准确 (无重复幻觉)
            OCR 准, 必须用 1024px 不用 512px (512px 截断 + 失真)

        修法: 缩到 max_dim (默认 1024) 像素长边, JPEG quality 80, 目标 ≤ 200KB

        Args:
            image_bytes: 原图字节
            mime: 原图 mime ('image/png' / 'image/jpeg')
            max_size_kb: 目标大小上限 (KB)

        Returns:
            (compressed_bytes, output_mime)
        """
        if not HAS_PIL:
            logger.warning("PIL not available, skip compression")
            return image_bytes, mime

        try:
            img = Image.open(BytesIO(image_bytes))
            # 转 RGB (PNG 含 alpha 通道时, JPEG 没法存)
            if img.mode in ('RGBA', 'LA', 'P'):
                img = img.convert('RGB')
            out_mime = 'image/jpeg'

            # 关键: 强制缩到 max_dim 像素长边 (默认 1024)
            # ⚠️ 之前用 512 失真, 用户测 glm-ocr-fix 1024 准
            img.thumbnail((max_dim, max_dim), Image.LANCZOS)

            # 质量迭代降低直到 < max_size_kb
            quality = 80
            while quality >= 30:
                buf = BytesIO()
                img.save(buf, 'JPEG', quality=quality, optimize=True)
                size = buf.tell()
                if size <= max_size_kb * 1024:
                    logger.info(f"Compressed to {size} bytes (quality={quality}, size=512px)")
                    return buf.getvalue(), out_mime
                quality -= 10

            # 30 还是超, 进一步压
            img.thumbnail((int(max_dim * 0.75), int(max_dim * 0.75)), Image.LANCZOS)
            buf = BytesIO()
            img.save(buf, 'JPEG', quality=50, optimize=True)
            logger.info(f"Compressed to {buf.tell()} bytes (quality=50, size=384px)")
            return buf.getvalue(), out_mime
        except Exception as e:
            logger.warning(f"Image compression failed: {e}, use original")
            return image_bytes, mime

    async def upload_and_extract(self, file_bytes: bytes, filename: str, permit_type: str = "hot_work") -> dict:
        """Upload PDF/Image → extract → structured data (not saved yet)."""

        ext = Path(filename).suffix.lower()

        # Image path: vision LLM directly
        if ext in (".jpg", ".jpeg", ".png"):
            logger.info(f"Image upload detected: {filename}")
            extracted, actual_permit_type, warnings = await self._extract_from_image(file_bytes, filename, permit_type)
            # OCR 兜底已关掉 (用户要求"选的什么就用什么"), actual_permit_type 等于 permit_type
            # warnings 仍返回, 让前端知道图跟模板可能不匹配
            _ = warnings  # 占位 (目前只 log, 不返回给前端)
            _ = actual_permit_type
            gas_data = extracted.pop("gas_analyses", [])
            safety_data = extracted.pop("safety_checks", [])
            for k in ("related_permit_ids", "related_permits"):
                if k in extracted and isinstance(extracted[k], list):
                    extracted[k] = ", ".join(str(x) for x in extracted[k])
            code_key = "permit_code" if "permit_code" in extracted else "ticket_code"
            if not extracted.get(code_key):
                extracted[code_key] = Path(filename).stem
            if "work_id" in extracted and not extracted.get("work_id"):
                extracted["work_id"] = extracted.get(code_key, Path(filename).stem)
            return {
                "permit_type": permit_type,
                "permit": {k: v for k, v in extracted.items() if v is not None},
                "gas_analyses": gas_data,
                "safety_checks": safety_data,
                "raw_md": None,
                "warnings": warnings,
            }

        # PDF path: MinerU + LLM
        suffix = ext or ".pdf"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name

        try:
            # 2) MinerU parse
            md_text = None
            if settings.mineru_local_url:
                logger.info(f"MINERU_LOCAL_URL={settings.mineru_local_url}")
                logger.info(f"Local MinerU extracting: {filename}")
                try:
                    md_text = await self._extract_local_mineru(file_bytes, filename)
                except (httpx.ConnectError, httpx.TimeoutException, ConnectionError, OSError) as e:
                    logger.warning(f"Local MinerU unreachable ({e}), falling back to cloud MinerU")
                    md_text = None
            if md_text is None:
                logger.info(f"Cloud MinerU extracting: {filename}")
                result = await self._mineru.extract(Path(tmp_path))
                md_text = self._extract_md_from_result(result)
                if not md_text or len(md_text) < 100:
                    md_text = self._to_markdown(result.get("content", {}))
                    logger.info(f"Fallback to JSON extraction, md length={len(md_text)}")
            logger.info(f"MinerU done, md length={len(md_text)}")

            # 3) LLM extraction
            extracted = await self._extract_with_llm(md_text, permit_type)

            # 4) Build response - generic dict-based
            gas_data = extracted.pop("gas_analyses", [])
            safety_data = extracted.pop("safety_checks", [])
            # Convert list values to comma-separated strings
            for k in ("related_permit_ids", "related_permits"):
                if k in extracted and isinstance(extracted[k], list):
                    extracted[k] = ", ".join(str(x) for x in extracted[k])

            # Set defaults for primary key fields
            code_key = "permit_code" if "permit_code" in extracted else "ticket_code"
            if not extracted.get(code_key):
                extracted[code_key] = Path(filename).stem
            if "work_id" in extracted and not extracted.get("work_id"):
                extracted["work_id"] = extracted.get(code_key, Path(filename).stem)

            return {
                "permit_type": permit_type,
                "permit": {k: v for k, v in extracted.items() if v is not None},
                "gas_analyses": gas_data,
                "safety_checks": safety_data,
                "raw_md": md_text,
            }
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    async def compliance_review(
        self,
        data: dict,
        permit_type: str = "hot_work",
    ) -> list[dict]:
        """调用 LLM 对作业票数据进行合规性审查。"""
        from services.wiki_search import get_wiki_search
        wiki = get_wiki_search()
        standard_context = wiki.get_permit_review_context(
            permit_type=permit_type,
            max_chars=6000,
        )
        if not standard_context:
            logger.warning("Wiki returned empty context for permit_type=%s, falling back to local GB file", permit_type)
            gb_text = _load_gb_standard()
            standard_context = f"## GB 30871-2022 标准原文\n\n{gb_text}" if gb_text else ""
        user_content = f"{standard_context}\n\n---\n\n## 待审查的作业票数据\n\n{json.dumps(data, ensure_ascii=False, indent=2)}"
        review_prompt = _load_prompt(permit_type, "review")
        messages = [
            SystemMessage(content=review_prompt),
            HumanMessage(content=f"请依据标准原文审查以下作业票数据的合规性：\n\n{user_content}"),
        ]
        resp_result = await llm_invoke_json(
            self._llm, messages, error_context="Compliance review"
        )
        if resp_result is None:
            return [{"category": "解析错误", "status": "fail", "issues": ["LLM 返回格式异常"]}]
        return resp_result

    @staticmethod
    def _extract_md_from_result(result: dict) -> str:
        """Extract full.md text from MinerU zip result if available."""
        meta = result.get("meta", {})
        zip_path = meta.get("zip_path")
        if not zip_path:
            return ""
        try:
            import zipfile as _zf
            with _zf.ZipFile(zip_path) as zf:
                for name in zf.namelist():
                    if name.lower().endswith(".md"):
                        return zf.read(name).decode("utf-8")
        except Exception:
            pass
        return ""

        # ─────────────── internal ───────────────


    async def save_permit_generic(self, permit_type: str, permit_data: dict,
                                   gas_analyses: list[dict] | None = None,
                                   safety_checks: list[dict] | None = None) -> dict:
        """Save a permit to the correct table based on type."""
        cfg = get_permit_type(permit_type)
        table = cfg["table"]

        # Upsert: update if has id, insert otherwise
        existing_id = permit_data.pop("id", None)
        if existing_id:
            saved = await self._repo.generic_update(table, existing_id, permit_data)
        else:
            saved = await self._repo.generic_insert(table, permit_data)

        saved_id = saved.get("id")
        if not saved_id:
            return saved

        # Save gas analyses
        if gas_analyses and cfg.get("gas_table"):
            gas_table = cfg["gas_table"]
            await self._repo.generic_delete_gas(gas_table, saved_id)
            for ga in gas_analyses:
                ga["permit_id"] = saved_id
                await self._repo.generic_insert_gas(gas_table, ga)

        # Save safety checks (hot_work only)
        if safety_checks and permit_type == "hot_work":
            await self._repo.delete_safety_checks(saved_id)
            all_items = await self._repo.list_safety_check_items()
            for sc in safety_checks:
                desc = sc.get("description", "").strip()
                if not desc:
                    continue
                matched_id = None
                for item in all_items:
                    if item.description and item.description.strip() == desc:
                        matched_id = item.id
                        break
                if not matched_id:
                    for item in all_items:
                        if item.description and item.description.strip() in desc:
                            matched_id = item.id
                            break
                if not matched_id:
                    for item in all_items:
                        if item.description and desc[:min(len(desc), 12)] in item.description:
                            matched_id = item.id
                            break
                if matched_id:
                    await self._repo.insert_safety_check(
                        saved_id, "HOT_WORK", matched_id,
                        sc.get("is_confirmed", False), sc.get("confirmed_by"),
                    )

        return saved

    async def list_permits_typed(self, permit_type: str) -> list[dict]:
        """List permits from the correct table."""
        cfg = get_permit_type(permit_type)
        return await self._repo.generic_list(cfg["table"])

    async def get_permit_typed(self, permit_type: str, permit_id: int) -> dict | None:
        """Get a permit with gas analyses from the correct tables."""
        cfg = get_permit_type(permit_type)
        permit = await self._repo.generic_get(cfg["table"], permit_id)
        if not permit:
            return None
        result = {"permit": permit, "gas_analyses": [], "safety_checks": []}
        if cfg.get("gas_table"):
            result["gas_analyses"] = await self._repo.generic_list_gas(cfg["gas_table"], permit_id)
        if permit_type == "hot_work":
            result["safety_checks"] = await self._repo.get_safety_checks(permit_id)
        return result

    async def delete_permit_typed(self, permit_type: str, permit_id: int) -> bool:
        """Delete a permit from the correct table."""
        cfg = get_permit_type(permit_type)
        # Delete gas analyses first
        if cfg.get("gas_table"):
            await self._repo.generic_delete_gas(cfg["gas_table"], permit_id)
        if permit_type == "hot_work":
            await self._repo.delete_safety_checks(permit_id)
        return await self._repo.generic_delete(cfg["table"], permit_id)

    async def _extract_with_llm(self, md_text: str, permit_type: str = "hot_work") -> dict:
        """Call LLM to extract structured fields from markdown text."""
        prompt = _load_prompt(permit_type, "extract")
        messages = [
            SystemMessage(content=prompt),
            HumanMessage(content=f"请从以下动火作业票文本中提取结构化数据：\n\n{md_text}"),
        ]
        resp_result = await llm_invoke_json(
            self._llm, messages, error_context="LLM extraction"
        )
        if resp_result is None or not isinstance(resp_result, dict):
            return {"permit_code": "", "raw_llm_output": str(resp_result)}
        return resp_result

    @staticmethod
    def _to_markdown(content: dict | list) -> str:
        """Convert MinerU parsed content to plain markdown text."""
        if isinstance(content, dict):
            # MinerU returns paragraphs as a list under various keys
            for key in ("paragraphs", "blocks", "content_list", "texts"):
                if key in content:
                    items = content[key]
                    if isinstance(items, list):
                        return "\n\n".join(
                            item.get("text", str(item)) if isinstance(item, dict) else str(item)
                            for item in items
                        )
            return json.dumps(content, ensure_ascii=False, indent=2)
        if isinstance(content, list):
            return "\n\n".join(
                item.get("text", str(item)) if isinstance(item, dict) else str(item)
                for item in content
            )
        return str(content)
