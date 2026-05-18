"""
作业票业务逻辑层。

核心流程：上传 PDF → MinerU 解析 → LLM 结构化提取 → 前端确认 → 入库。
"""

from __future__ import annotations

import httpx
import json
import os
import re
import tempfile
from pathlib import Path

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from config.config import settings
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
    """加载 GB 30871-2022 标准原文（MD 格式），启动时调用一次。"""
    global _GB_STANDARD_TEXT
    if _GB_STANDARD_TEXT is not None:
        return _GB_STANDARD_TEXT
    # 标准文件路径（按优先级排列）
    candidates = [
        '/data/lvm_data_48T/wyuz/ai-document-review/GB_30871-2022危险化学品企业特殊作业安全规范.md',
        os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'GB_30871-2022危险化学品企业特殊作业安全规范.md'),
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

    def _init_llm(self) -> ChatOpenAI:
        return ChatOpenAI(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            model=settings.deepseek_model,
            temperature=0.1,
            extra_body={"enable_thinking": False},
        )


    async def _extract_local_mineru(self, file_bytes: bytes, filename: str) -> str:
        """Call local MinerU API and return markdown text."""
        url = f"{settings.mineru_local_url.rstrip('/')}/file_parse"
        files = {"files": (filename, file_bytes, "application/pdf")}
        data = {"lang_list": "ch", "backend": "vlm-auto-engine"}
        logger.info(f"Calling local MinerU: url={url} backend={data["backend"]}")

        async with httpx.AsyncClient(timeout=300) as client:
            resp = await client.post(url, files=files, data=data)
            resp.raise_for_status()
            result = resp.json()

        if result.get("status") != "completed":
            raise RuntimeError(f"Local MinerU parse failed: {result.get('error')}")

        # Extract md_content from results
        results = result.get("results", {})
        for file_key, file_result in results.items():
            md = file_result.get("md_content", "")
            if md:
                logger.info(f"Local MinerU done, md length={len(md)}")
                return md

        raise RuntimeError("Local MinerU returned no md_content")

    async def upload_and_extract(self, file_bytes: bytes, filename: str, permit_type: str = "hot_work") -> dict:
        """Upload PDF → MinerU → LLM extract → structured data (not saved yet)."""

        # 1) Save to temp file for MinerU
        suffix = Path(filename).suffix or ".pdf"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name

        try:
            # 2) MinerU parse
            if settings.mineru_local_url:
                logger.info(f"MINERU_LOCAL_URL={settings.mineru_local_url}")
                logger.info(f"Local MinerU extracting: {filename}")
                md_text = await self._extract_local_mineru(file_bytes, filename)
            else:
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

    async def save_permit(
        self,
        permit: HotWorkPermit,
        gas_analyses: list[HotWorkGasAnalysis],
        safety_checks: list[ExtractedSafetyCheck] | None = None,
    ) -> HotWorkPermit:
        """Save or update permit. Uses UPDATE if permit.id exists (draft re-save)."""
        is_update = permit.id is not None
        if is_update:
            saved = await self._repo.update_permit(permit)
            # Re-save gas analyses: delete old, insert new
            await self._repo.delete_gas_analyses(saved.id)
            await self._repo.delete_safety_checks(saved.id)
        else:
            saved = await self._repo.insert_permit(permit)
        for ga in gas_analyses:
            ga.permit_id = saved.id
            await self._repo.insert_gas_analysis(ga)
        # Save safety checks - match against safety_check_items with fuzzy matching
        if safety_checks:
            all_items = await self._repo.list_safety_check_items()
            for sc in safety_checks:
                if not sc.description:
                    continue
                matched_id = None
                desc = sc.description.strip()
                # 1) Exact match
                for item in all_items:
                    if item.description and item.description.strip() == desc:
                        matched_id = item.id
                        break
                # 2) LLM description contains the standard item description
                if not matched_id:
                    for item in all_items:
                        if item.description and item.description.strip() in desc:
                            matched_id = item.id
                            break
                # 3) Standard item description contains LLM text
                if not matched_id:
                    for item in all_items:
                        if item.description and desc[:min(len(desc), 12)] in item.description:
                            matched_id = item.id
                            break
                if matched_id:
                    await self._repo.insert_safety_check(
                        saved.id, "HOT_WORK", matched_id,
                        sc.is_confirmed or False,
                        sc.confirmed_by,
                    )
        logger.info(f"Saved permit id={saved.id}, code={saved.permit_code}")
        return saved

    async def list_permits(self) -> list[HotWorkPermit]:
        return await self._repo.list_permits()

    async def get_permit(self, permit_id: int) -> dict | None:
        permit = await self._repo.get_permit(permit_id)
        if not permit:
            return None
        gas = await self._repo.get_gas_analyses(permit_id)
        safety = await self._repo.get_safety_checks(permit_id)
        return {"permit": permit, "gas_analyses": gas, "safety_checks": safety}

    async def delete_permit(self, permit_id: int) -> bool:
        await self._repo.delete_gas_analyses(permit_id)
        return await self._repo.delete_permit(permit_id)

    async def compliance_review(
        self,
        data: dict,
        permit_type: str = "hot_work",
    ) -> list[dict]:
        """调用 LLM 对作业票数据进行合规性审查。"""
        gb_text = _load_gb_standard()
        standard_context = f"## GB 30871-2022 标准原文\n\n{gb_text}" if gb_text else ""
        user_content = f"{standard_context}\n\n---\n\n## 待审查的作业票数据\n\n{json.dumps(data, ensure_ascii=False, indent=2)}"
        review_prompt = _load_prompt(permit_type, "review")
        messages = [
            SystemMessage(content=review_prompt),
            HumanMessage(content=f"请依据标准原文审查以下作业票数据的合规性：\n\n{user_content}"),
        ]
        resp = await self._llm.ainvoke(messages)
        raw = resp.content
        # qwen3.5-flash thinking model: content may be empty, check reasoning_content
        if not raw or not raw.strip():
            reasoning = getattr(resp, 'additional_kwargs', {}).get('reasoning_content', '')
            if reasoning:
                logger.info(f"LLM content empty, using reasoning_content (len={len(reasoning)})")
                raw = reasoning
        raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
        raw = re.sub(r"\s*```$", "", raw.strip())
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.error(f"Compliance review returned non-JSON: {raw[:500]}")
            return [{"category": "解析错误", "status": "fail", "issues": ["LLM 返回格式异常"]}]

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
        resp = await self._llm.ainvoke(messages)
        raw = resp.content
        # qwen3.5-flash thinking model: content may be empty, check reasoning_content
        if not raw or not raw.strip():
            reasoning = getattr(resp, 'additional_kwargs', {}).get('reasoning_content', '')
            if reasoning:
                logger.info(f"LLM content empty, using reasoning_content (len={len(reasoning)})")
                raw = reasoning
        # Strip markdown code fences if present
        raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
        raw = re.sub(r"\s*```$", "", raw.strip())
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.error(f"LLM returned non-JSON: {raw[:500]}")
            return {"permit_code": "", "raw_llm_output": raw}

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
