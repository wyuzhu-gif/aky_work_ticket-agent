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
from pathlib import Path

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from config.config import settings
from common.llm_utils import build_llm
from database.pg_client import PgClient
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


    async def _extract_from_image(self, image_bytes: bytes, filename: str, permit_type: str) -> dict:
        """Extract structured data from image using vision LLM."""
        ext = Path(filename).suffix.lower()
        mime_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}
        mime = mime_map.get(ext, "image/jpeg")
        b64 = base64.b64encode(image_bytes).decode()
        logger.info(f"Vision LLM extracting from image: {filename}, size={len(image_bytes)}, mime={mime}")

        prompt = _load_prompt(permit_type, "extract_image")
        messages = [
            SystemMessage(content=prompt),
            HumanMessage(content=[
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                {"type": "text", "text": "请从这张作业票图片中提取所有结构化数据，输出 JSON。"},
            ]),
        ]
        resp = await self._vision_llm.ainvoke(messages)
        raw = extract_llm_content(resp)
        raw = strip_code_fences(raw)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.error(f"Vision LLM returned non-JSON: {raw[:500]}")
            return {"permit_code": "", "raw_llm_output": raw}

    async def upload_and_extract(self, file_bytes: bytes, filename: str, permit_type: str = "hot_work") -> dict:
        """Upload PDF/Image → extract → structured data (not saved yet)."""

        ext = Path(filename).suffix.lower()

        # Image path: vision LLM directly
        if ext in (".jpg", ".jpeg", ".png"):
            logger.info(f"Image upload detected: {filename}")
            extracted = await self._extract_from_image(file_bytes, filename, permit_type)
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
