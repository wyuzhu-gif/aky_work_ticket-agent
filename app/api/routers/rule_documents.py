from http import HTTPStatus
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from common.logger import get_logger
from common.models import RuleDocument, DocumentRuleDocAssociation
from services.rule_documents_service import RuleDocumentsService
from dependencies import get_rule_documents_service

router = APIRouter()
logging = get_logger(__name__)


# ========== Request/Response Models ==========

class SetDocumentRuleDocRequest(BaseModel):
    enabled: bool


# ========== Rule Documents CRUD Endpoints ==========

@router.get(
    "/api/v1/rule-documents",
    summary="Get all rule documents",
    response_model=List[RuleDocument],
)
async def get_rule_documents(
    service: RuleDocumentsService = Depends(get_rule_documents_service),
) -> List[RuleDocument]:
    """Get all rule documents."""
    logging.info("Retrieving all rule documents")
    return await service.get_all_rule_documents()


@router.post(
    "/api/v1/rule-documents/upload",
    summary="Upload a rule document",
    response_model=RuleDocument,
)
async def upload_rule_document(
    file: UploadFile = File(...),
    description: Optional[str] = None,
    service: RuleDocumentsService = Depends(get_rule_documents_service),
) -> RuleDocument:
    """Upload a rule document (PDF, DOCX, MD, TXT)."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    content = await file.read()
    try:
        return await service.upload_rule_document(file.filename, content, description)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get(
    "/api/v1/rule-documents/{rule_doc_id}",
    summary="Get a specific rule document",
    response_model=RuleDocument,
)
async def get_rule_document(
    rule_doc_id: str,
    service: RuleDocumentsService = Depends(get_rule_documents_service),
) -> RuleDocument:
    """Get a specific rule document by ID."""
    try:
        return await service.get_rule_document(rule_doc_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get(
    "/api/v1/rule-documents/{rule_doc_id}/text",
    summary="Get extracted text of a rule document",
)
async def get_rule_document_text(
    rule_doc_id: str,
    service: RuleDocumentsService = Depends(get_rule_documents_service),
) -> dict:
    """Get the extracted text of a rule document."""
    try:
        doc = await service.get_rule_document(rule_doc_id)
        return {"id": doc.id, "name": doc.name, "extracted_text": doc.extracted_text or ""}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post(
    "/api/v1/rule-documents/{rule_doc_id}/parse",
    summary="Parse a rule document into structured rules using AI",
    response_model=RuleDocument,
)
async def parse_rule_document(
    rule_doc_id: str,
    service: RuleDocumentsService = Depends(get_rule_documents_service),
) -> RuleDocument:
    """Trigger AI parsing of a rule document into structured rules."""
    try:
        return await service.parse_rule_document_with_llm(rule_doc_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete(
    "/api/v1/rule-documents/{rule_doc_id}",
    summary="Delete a rule document",
)
async def delete_rule_document(
    rule_doc_id: str,
    service: RuleDocumentsService = Depends(get_rule_documents_service),
) -> dict:
    """Delete a rule document."""
    try:
        await service.delete_rule_document(rule_doc_id)
        return {"message": "Rule document deleted", "rule_doc_id": rule_doc_id}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get(
    "/api/v1/rule-documents-template",
    summary="Download rule document template",
)
async def download_template():
    """Download the rule document template file."""
    from config.config import settings
    from pathlib import Path

    template_path = Path(settings.rule_docs_dir).parent / "rule_docs_template.md"
    if not template_path.exists():
        # Create default template
        template_content = """# 审核规则文档：[文档名称]

## 元信息
- 适用范围: [如：劳动合同、基金年报等]
- 版本: [1.0]

---

## 规则1：[规则名称]
- **风险等级**: 高/中/低
- **规则描述**: [描述该规则检测什么问题]
- **示例**:
  - 示例文本: "[包含问题的文本片段]"
    说明: "[为什么这是一个问题]"

## 规则2：[规则名称]
- **风险等级**: 高/中/低
- **规则描述**: [描述]
- **示例**:
  - 示例文本: "[文本]"
    说明: "[说明]"
"""
        template_path.parent.mkdir(parents=True, exist_ok=True)
        template_path.write_text(template_content, encoding='utf-8')

    return FileResponse(
        path=str(template_path),
        filename="规则文档模板.md",
        media_type="text/markdown",
    )


# ========== Document-RuleDocument Association Endpoints ==========

@router.get(
    "/api/v1/review/{doc_id}/rule-documents",
    summary="Get rule document associations for a document",
    response_model=List[DocumentRuleDocAssociation],
)
async def get_document_rule_docs(
    doc_id: str,
    service: RuleDocumentsService = Depends(get_rule_documents_service),
) -> List[DocumentRuleDocAssociation]:
    """Get all rule document associations for a document."""
    logging.info(f"Retrieving rule document associations for document {doc_id}")
    return await service.get_document_rule_docs(doc_id)


@router.put(
    "/api/v1/review/{doc_id}/rule-documents/{rule_doc_id}",
    summary="Enable or disable a rule document for a document",
)
async def set_document_rule_doc(
    doc_id: str,
    rule_doc_id: str,
    body: SetDocumentRuleDocRequest,
    service: RuleDocumentsService = Depends(get_rule_documents_service),
) -> dict:
    """Enable or disable a rule document for a specific document."""
    try:
        await service.set_document_rule_doc(doc_id, rule_doc_id, body.enabled)
        return {"message": "Association updated", "doc_id": doc_id, "rule_doc_id": rule_doc_id, "enabled": body.enabled}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
