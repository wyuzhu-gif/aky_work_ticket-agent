from http import HTTPStatus
from typing import List, Optional
import json
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from common.logger import get_logger
from common.models import ReviewRule, DocumentRuleAssociation, RiskLevel, RuleExample, RuleFolder
from services.rules_service import RulesService
from dependencies import get_rules_service

router = APIRouter()
logging = get_logger(__name__)


# ========== Request/Response Models ==========

class CreateRuleRequest(BaseModel):
    name: str
    description: str
    prompt: Optional[str] = None
    risk_level: RiskLevel
    examples: Optional[List[RuleExample]] = None


class UpdateRuleRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    prompt: Optional[str] = None
    risk_level: Optional[RiskLevel] = None
    examples: Optional[List[RuleExample]] = None
    folder_id: Optional[str] = None
    status: Optional[str] = None


class SetDocumentRuleRequest(BaseModel):
    enabled: bool


class CreateFolderRequest(BaseModel):
    name: str
    description: Optional[str] = None


class UpdateFolderRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class SetRuleFolderRequest(BaseModel):
    folder_id: Optional[str] = None  # null = remove from folder


# ========== Rules CRUD Endpoints ==========

@router.get(
    "/api/v1/rules",
    summary="Get all review rules",
    response_model=List[ReviewRule],
    responses={
        HTTPStatus.OK: {"description": "Rules retrieved successfully"},
    },
)
async def get_rules(
    rules_service: RulesService = Depends(get_rules_service),
) -> List[ReviewRule]:
    """Get all review rules."""
    logging.info("Retrieving all rules")
    return await rules_service.get_all_rules()


@router.post(
    "/api/v1/rules",
    summary="Create a new review rule",
    response_model=ReviewRule,
    responses={
        HTTPStatus.OK: {"description": "Rule created successfully"},
        HTTPStatus.BAD_REQUEST: {"description": "Invalid data provided"},
    },
)
async def create_rule(
    body: CreateRuleRequest,
    rules_service: RulesService = Depends(get_rules_service),
) -> ReviewRule:
    """Create a new review rule."""
    logging.info(f"Creating rule: {body.name}")
    return await rules_service.create_rule(
        name=body.name,
        description=body.description,
        prompt=body.prompt,
        risk_level=body.risk_level,
        examples=body.examples,
    )


@router.get(
    "/api/v1/rules/{rule_id}",
    summary="Get a specific rule",
    response_model=ReviewRule,
    responses={
        HTTPStatus.OK: {"description": "Rule retrieved successfully"},
        HTTPStatus.NOT_FOUND: {"description": "Rule not found"},
    },
)
async def get_rule(
    rule_id: str,
    rules_service: RulesService = Depends(get_rules_service),
) -> ReviewRule:
    """Get a specific rule by ID."""
    try:
        return await rules_service.get_rule(rule_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.patch(
    "/api/v1/rules/{rule_id}",
    summary="Update a rule",
    response_model=ReviewRule,
    responses={
        HTTPStatus.OK: {"description": "Rule updated successfully"},
        HTTPStatus.NOT_FOUND: {"description": "Rule not found"},
    },
)
async def update_rule(
    rule_id: str,
    body: UpdateRuleRequest,
    rules_service: RulesService = Depends(get_rules_service),
) -> ReviewRule:
    """Update a rule."""
    try:
        fields = body.model_dump(exclude_none=True)
        # folder_id=None means "move to uncategorized", include it explicitly
        if body.folder_id is None and 'folder_id' not in fields:
            fields['folder_id'] = None
        if not fields:
            raise HTTPException(status_code=400, detail="No fields to update")
        return await rules_service.update_rule(rule_id, fields)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete(
    "/api/v1/rules/{rule_id}",
    summary="Delete a rule",
    responses={
        HTTPStatus.OK: {"description": "Rule deleted successfully"},
        HTTPStatus.NOT_FOUND: {"description": "Rule not found"},
    },
)
async def delete_rule(
    rule_id: str,
    rules_service: RulesService = Depends(get_rules_service),
) -> dict:
    """Delete a rule."""
    try:
        await rules_service.delete_rule(rule_id)
        return {"message": "Rule deleted", "rule_id": rule_id}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ========== Folder CRUD Endpoints ==========

@router.get(
    "/api/v1/rule-folders",
    summary="Get all rule folders",
    response_model=List[RuleFolder],
)
async def get_folders(
    rules_service: RulesService = Depends(get_rules_service),
) -> List[RuleFolder]:
    return await rules_service.get_all_folders()


@router.post(
    "/api/v1/rule-folders",
    summary="Create a rule folder",
    response_model=RuleFolder,
)
async def create_folder(
    body: CreateFolderRequest,
    rules_service: RulesService = Depends(get_rules_service),
) -> RuleFolder:
    return await rules_service.create_folder(name=body.name, description=body.description)


@router.patch(
    "/api/v1/rule-folders/{folder_id}",
    summary="Update a rule folder",
    response_model=RuleFolder,
)
async def update_folder(
    folder_id: str,
    body: UpdateFolderRequest,
    rules_service: RulesService = Depends(get_rules_service),
) -> RuleFolder:
    try:
        fields = body.model_dump(exclude_none=True)
        return await rules_service.update_folder(folder_id, fields)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete(
    "/api/v1/rule-folders/{folder_id}",
    summary="Delete a rule folder",
)
async def delete_folder(
    folder_id: str,
    rules_service: RulesService = Depends(get_rules_service),
) -> dict:
    try:
        await rules_service.delete_folder(folder_id)
        return {"message": "Folder deleted", "folder_id": folder_id}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get(
    "/api/v1/rule-folders/{folder_id}/rules",
    summary="Get all rules in a folder",
    response_model=List[ReviewRule],
)
async def get_folder_rules(
    folder_id: str,
    rules_service: RulesService = Depends(get_rules_service),
) -> List[ReviewRule]:
    return await rules_service.get_rules_by_folder(folder_id)


@router.put(
    "/api/v1/rule-folders/{folder_id}/default",
    summary="Set a folder as the default",
    response_model=RuleFolder,
)
async def set_default_folder(
    folder_id: str,
    rules_service: RulesService = Depends(get_rules_service),
) -> RuleFolder:
    try:
        return await rules_service.set_default_folder(folder_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get(
    "/api/v1/rule-folders/default",
    summary="Get the default folder",
)
async def get_default_folder(
    rules_service: RulesService = Depends(get_rules_service),
):
    folder = await rules_service.get_default_folder()
    if not folder:
        return {"default_folder": None}
    return {"default_folder": json.loads(folder.model_dump_json())}


# ========== Document-Rule Association Endpoints ==========

@router.get(
    "/api/v1/review/{doc_id}/rules",
    summary="Get rule associations for a document",
    response_model=List[DocumentRuleAssociation],
    responses={
        HTTPStatus.OK: {"description": "Associations retrieved successfully"},
    },
)
async def get_document_rules(
    doc_id: str,
    rules_service: RulesService = Depends(get_rules_service),
) -> List[DocumentRuleAssociation]:
    """Get all rule associations for a document."""
    logging.info(f"Retrieving rule associations for document {doc_id}")
    return await rules_service.get_document_rules(doc_id)


@router.put(
    "/api/v1/review/{doc_id}/rules/{rule_id}",
    summary="Enable or disable a rule for a document",
    responses={
        HTTPStatus.OK: {"description": "Association updated successfully"},
        HTTPStatus.NOT_FOUND: {"description": "Rule not found"},
    },
)
async def set_document_rule(
    doc_id: str,
    rule_id: str,
    body: SetDocumentRuleRequest,
    rules_service: RulesService = Depends(get_rules_service),
) -> dict:
    """Enable or disable a rule for a specific document."""
    try:
        await rules_service.set_document_rule(doc_id, rule_id, body.enabled)
        return {"message": "Association updated", "doc_id": doc_id, "rule_id": rule_id, "enabled": body.enabled}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
