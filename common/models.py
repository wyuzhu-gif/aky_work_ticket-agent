from pydantic import BaseModel
from enum import Enum
from typing import Optional


# ========== Location ==========
class Location(BaseModel):
    source_sentence: str
    page_num: int
    bounding_box: list[float]
    para_index: int


# ========== Issue Types ==========
class IssueType(str, Enum):
    GrammarSpelling = 'Grammar & Spelling'
    DefinitiveLanguage = 'Definitive Language'


# ========== Risk Level ==========
class RiskLevel(str, Enum):
    high = '高'
    medium = '中'
    low = '低'


# ========== Rule Status ==========
class RuleStatusEnum(str, Enum):
    active = 'active'
    inactive = 'inactive'


# ========== Rule Example ==========
class RuleExample(BaseModel):
    text: str
    explanation: str


# ========== Rule Folder ==========
class RuleFolder(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    is_default: bool = False
    created_at: str
    updated_at: Optional[str] = None


# ========== Review Rule ==========
class ReviewRule(BaseModel):
    id: str
    name: str
    description: str
    prompt: Optional[str] = None  # 完整的提示词正文，用于注入 LLM
    risk_level: RiskLevel
    examples: list[RuleExample] = []
    folder_id: Optional[str] = None  # 所属文件夹
    is_preset: bool = False  # 是否为预设规则（不可删除，仅可停用）
    status: RuleStatusEnum = RuleStatusEnum.active
    created_at: str
    updated_at: Optional[str] = None

    class Config:
        use_enum_values = True


# ========== Document Rule Association ==========
class DocumentRuleAssociation(BaseModel):
    doc_id: str
    rule_id: str
    enabled: bool = True




# ========== Rule Document Source Type ==========
class RuleDocumentSource(str, Enum):
    context = 'context'     # injected as raw context
    parsed = 'parsed'       # parsed into structured ReviewRules


# ========== Rule Document Status ==========
class RuleDocumentStatus(str, Enum):
    active = 'active'
    inactive = 'inactive'


# ========== Rule Document ==========
class RuleDocument(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    file_path: str
    file_type: str = 'pdf'
    source_type: RuleDocumentSource = RuleDocumentSource.context
    extracted_text: Optional[str] = None
    parsed_rule_ids: Optional[list[str]] = None
    status: RuleDocumentStatus = RuleDocumentStatus.active
    created_at: str
    updated_at: Optional[str] = None

    class Config:
        use_enum_values = True


# ========== Document Rule Document Association ==========
class DocumentRuleDocAssociation(BaseModel):
    doc_id: str
    rule_document_id: str
    enabled: bool = True

class SingleShotIssue(BaseModel):
    type: IssueType
    location: Location
    text: str
    explanation: str
    suggested_fix: str
    comment_id: str


class ConsolidatorIssue(BaseModel):
    comment_id: str
    score: int
    suggested_action: str
    reason_for_suggested_action: str


class CombinedIssue(SingleShotIssue, ConsolidatorIssue):
    pass


class AllSingleShotIssues(BaseModel):
    issues: list[SingleShotIssue]


class AllConsolidatorIssues(BaseModel):
    issues: list[ConsolidatorIssue]


class AllCombinedIssues(BaseModel):
    issues: list[CombinedIssue]


class BaseIssue(BaseModel):
    type: IssueType
    location: Location
    text: str
    explanation: str
    suggested_fix: str


class FlowOutputChunk(BaseModel):
    issues: list[BaseIssue]


class IssueStatusEnum(str, Enum):
    accepted = 'accepted'
    dismissed = 'dismissed'
    not_reviewed = 'not_reviewed'


class ModifiedFieldsModel(BaseModel):
    suggested_fix: Optional[str] = None
    explanation: Optional[str] = None
    text: Optional[str] = None


class DismissalFeedbackModel(BaseModel):
    reason: Optional[str] = None


class Issue(BaseModel):
    id: str
    doc_id: str
    text: str
    type: str  # IssueType value or custom rule name
    status: IssueStatusEnum
    suggested_fix: str
    explanation: str
    risk_level: Optional[RiskLevel] = None  # 风险等级：高/中/低
    location: Optional[Location] = None
    review_initiated_by: str
    review_initiated_at_UTC: str
    resolved_by: Optional[str] = None
    resolved_at_UTC: Optional[str] = None
    modified_fields: Optional[ModifiedFieldsModel] = None
    dismissal_feedback: Optional[DismissalFeedbackModel] = None

    class Config:
        use_enum_values = True
