"""
review_external.py
外部系统调用接口：上传 PDF/图片 → 审核 → 返回结果
"""
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from typing import List, Optional
import json
import shutil

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from dependencies import get_issues_service, get_rules_service, get_rule_documents_service
from common.logger import get_logger
from config.config import settings
from services.issues_service import IssuesService
from services.rules_service import RulesService
from services.rule_documents_service import RuleDocumentsService
from security.auth import validate_authenticated

router = APIRouter()
logging = get_logger(__name__)


def _issues_to_json(issues_list: list) -> list:
    """Convert Issue objects to plain dicts for JSON response."""
    results = []
    for issue in issues_list:
        d = {
            "id": issue.id,
            "text": issue.text,
            "type": issue.type,
            "explanation": issue.explanation,
            "suggested_fix": issue.suggested_fix,
            "risk_level": issue.risk_level,
        }
        if issue.location:
            d["location"] = {
                "source_sentence": issue.location.source_sentence,
                "page_num": issue.location.page_num,
                "bounding_box": issue.location.bounding_box,
                "para_index": issue.location.para_index,
            }
        results.append(d)
    return results


def _summary(issues_list: list) -> dict:
    total = len(issues_list)
    high = sum(1 for i in issues_list if i.risk_level == "高")
    medium = sum(1 for i in issues_list if i.risk_level == "中")
    low = sum(1 for i in issues_list if i.risk_level == "低")
    return {"total": total, "high": high, "medium": medium, "low": low}


@router.post(
    "/api/v1/review/upload-and-review",
    summary="Upload a PDF/image file and review it",
    tags=["External API"],
)
async def upload_and_review(
    file: UploadFile = File(..., description="PDF or image file (PDF/PNG/JPG)"),
    filename: Optional[str] = Form(None, description="Custom filename"),
    response_format: str = Form("stream", description="Response format: json or stream"),
    rule_ids: Optional[List[str]] = Query(None, description="Rule IDs to apply"),
    rule_doc_ids: Optional[List[str]] = Query(None, description="Rule document IDs to apply"),
    user=Depends(validate_authenticated),
    issues_service: IssuesService = Depends(get_issues_service),
    rules_service: RulesService = Depends(get_rules_service),
    rule_docs_service: RuleDocumentsService = Depends(get_rule_documents_service),
):
    """
    Upload a PDF or image file for review.

    - **json** mode: waits for full review, returns JSON with all issues.
    - **stream** mode: returns SSE events as issues are found.
    """
    # Validate file type
    allowed_ext = {".pdf", ".png", ".jpg", ".jpeg"}
    original_name = file.filename or "upload.pdf"
    ext = Path(original_name).suffix.lower()
    if ext not in allowed_ext:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext}. Allowed: {', '.join(allowed_ext)}")

    # Save uploaded file
    doc_filename = filename if filename else original_name
    # Ensure unique name to avoid collision
    if not doc_filename.endswith(ext):
        doc_filename += ext

    save_path = Path(settings.local_docs_dir) / doc_filename
    save_path.parent.mkdir(parents=True, exist_ok=True)

    with open(save_path, "wb") as f:
        content = await file.read()
        f.write(content)

    logging.info(f"Uploaded file saved: {save_path} ({len(content)} bytes)")

    # Get custom rules
    custom_rules = None
    if rule_ids:
        custom_rules = await rules_service.get_rules_by_ids(rule_ids)
        logging.info(f"Using {len(custom_rules)} custom rules")

    rule_documents = None
    if rule_doc_ids:
        rule_documents = await rule_docs_service.get_rule_documents_by_ids(rule_doc_ids)
        logging.info(f"Using {len(rule_documents)} rule documents")

    # === JSON mode: collect all issues then return ===
    if response_format == "json":
        date_time = datetime.now(timezone.utc)
        issues_stream = issues_service.initiate_review(
            str(save_path), user, date_time, custom_rules, rule_documents
        )

        all_issues = []
        try:
            async for batch in issues_stream:
                all_issues.extend(batch)
        except Exception as e:
            logging.error(f"Review failed: {e}")
            raise HTTPException(status_code=500, detail=f"Review failed: {str(e)}")

        result = {
            "doc_id": doc_filename,
            "status": "completed",
            "issues": _issues_to_json(all_issues),
            "summary": _summary(all_issues),
        }

        # Clean up uploaded file after review
        try:
            save_path.unlink()
            logging.info(f"Cleaned up uploaded file: {save_path}")
        except Exception:
            pass

        return JSONResponse(content=result)

    # === Stream mode: SSE ===
    else:
        date_time = datetime.now(timezone.utc)
        issues_stream = issues_service.initiate_review(
            str(save_path), user, date_time, custom_rules, rule_documents
        )

        async def sse_events():
            try:
                async for batch in issues_stream:
                    issue_dicts = _issues_to_json(batch)
                    yield f"event: issues\ndata: {json.dumps(issue_dicts, ensure_ascii=False)}\n\n"
                yield "event: complete\n\n"
            except Exception as e:
                logging.error(f"SSE stream error: {e}")
                yield f"event: error\ndata: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"
            finally:
                try:
                    save_path.unlink()
                except Exception:
                    pass

        return StreamingResponse(sse_events(), media_type="text/event-stream")
