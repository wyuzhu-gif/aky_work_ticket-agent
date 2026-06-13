"""
作业票业务逻辑层。

核心流程：上传 PDF → MinerU 解析 → LLM 结构化提取 → 前端确认 → 入库。
"""

from __future__ import annotations

import base64
import httpx
import json
import os
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
from common.llm_utils import extract_llm_content, strip_code_fences, llm_invoke_json

logger = get_logger(__name__)

# ─────────────── 存库开关（客户只读部署：不存库） ───────────────
# 客户服务器只给只读权限，作业票不进数据库。
# 关闭后：list/get 返回空，save/delete 直接返回 200 不实际写入。
# upload_and_extract 和 compliance_review 仍正常工作（这两个是核心功能）。
DB_DISABLED = os.getenv("DISABLE_PERMIT_STORAGE", "true").lower() in ("1", "true", "yes")


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
        return ChatOpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            model=settings.llm_vision_model,
            temperature=0.1,
        )

    def _init_llm(self) -> ChatOpenAI:
        return ChatOpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            model=settings.llm_model,
            temperature=0.1,
            extra_body={"enable_thinking": False},
        )


    async def _extract_local_mineru(self, file_bytes: bytes, filename: str) -> str:
        """Call local MinerU API and return markdown text."""
        url = f"{settings.mineru_local_url.rstrip('/')}/file_parse"
        files = {"files": (filename, file_bytes, "application/pdf")}
        data = {"lang_list": "ch", "backend": "vlm-auto-engine"}
        backend = data["backend"]
        logger.info(f"Calling local MinerU: url={url} backend={backend}")

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

    async def _extract_from_json(self, file_bytes: bytes, filename: str, permit_type_query: str) -> dict:
        """JSON 透传：直接解析前端/客户系统上传的结构化数据，跳过 MinerU/LLM。

        Q2=C 双支持：JSON 里的 permit_type 字段优先，缺则用 query 参数。
        Q1=B 宽松模式：Pydantic 默认 extra='ignore'，多余字段自动忽略，缺字段用 None。
        Q4=B 顶层支持 gas_analyses / safety_checks 数组。
        """
        try:
            data = json.loads(file_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            raise ValueError(f"JSON 解析失败: {e}") from e
        if not isinstance(data, dict):
            raise ValueError(f"JSON 必须是对象类型，实际为 {type(data).__name__}")

        # permit_type 双支持
        actual_type = data.get("permit_type") or permit_type_query
        try:
            get_permit_type(actual_type)
        except ValueError as e:
            raise ValueError(str(e)) from e

        # 提取子表（缺则空列表）
        gas_data = data.pop("gas_analyses", [])
        safety_data = data.pop("safety_checks", [])
        # 移除已用过的 permit_type 字段，避免污染主表
        data.pop("permit_type", None)

        # 列表字段逗号拼接（与 PDF/Image 路径保持一致）
        for k in ("related_permit_ids", "related_permits"):
            if k in data and isinstance(data[k], list):
                data[k] = ", ".join(str(x) for x in data[k])

        # code_key 默认值
        code_key = "permit_code" if "permit_code" in data else "ticket_code"
        if not data.get(code_key):
            data[code_key] = Path(filename).stem
        if "work_id" in data and not data.get("work_id"):
            data["work_id"] = data.get(code_key, Path(filename).stem)

        return {
            "permit_type": actual_type,
            "permit": {k: v for k, v in data.items() if v is not None},
            "gas_analyses": gas_data if isinstance(gas_data, list) else [],
            "safety_checks": safety_data if isinstance(safety_data, list) else [],
            "raw_md": None,
            "source": "json",
        }

    async def upload_and_extract(self, file_bytes: bytes, filename: str, permit_type: str = "hot_work") -> dict:
        """Upload PDF/Image/JSON → extract → structured data (not saved yet)."""

        ext = Path(filename).suffix.lower()

        # JSON 透传路径（Q3=A：跳过 LLM）
        if ext == ".json":
            logger.info(f"JSON upload detected: {filename}")
            return await self._extract_from_json(file_bytes, filename, permit_type)

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

    async def save_permit(
        self,
        permit: HotWorkPermit,
        gas_analyses: list[HotWorkGasAnalysis],
        safety_checks: list[ExtractedSafetyCheck] | None = None,
    ) -> HotWorkPermit:
        """Save or update permit. Uses UPDATE if permit.id exists (draft re-save)."""
        if DB_DISABLED:
            logger.info("[DB_DISABLED] 跳过 hot_work 入库")
            permit.id = None
            return permit
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
        if DB_DISABLED:
            logger.info(f"[DB_DISABLED] 跳过入库 permit_type={permit_type} (客户只读部署)")
            permit_data.pop("id", None)
            return {
                **permit_data,
                "id": None,
                "_db_disabled": True,
                "_message": "数据库禁用模式：作业票未持久化，仅返回前端回显",
            }
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
        if DB_DISABLED:
            return []
        cfg = get_permit_type(permit_type)
        return await self._repo.generic_list(cfg["table"])

    async def get_permit_typed(self, permit_type: str, permit_id: int) -> dict | None:
        """Get a permit with gas analyses from the correct tables."""
        if DB_DISABLED:
            return None
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
        if DB_DISABLED:
            return True
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
