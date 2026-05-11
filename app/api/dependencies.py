import asyncio

from services.issues_service import IssuesService
from services.rules_service import RulesService
from services.rule_documents_service import RuleDocumentsService
from services.lc_pipeline import LangChainPipeline
from database.db_client import SQLiteClient
from database.issues_repository import IssuesRepository
from database.rules_repository import RulesRepository
from database.rule_documents_repository import RuleDocumentsRepository


_issues_service: IssuesService | None = None
_issues_service_lock = asyncio.Lock()

_rules_service: RulesService | None = None
_rules_service_lock = asyncio.Lock()

_rule_docs_service: RuleDocumentsService | None = None
_rule_docs_service_lock = asyncio.Lock()


async def get_issues_service() -> IssuesService:
    """
    Dependency that returns a singleton IssuesService.

    HITL uses an in-memory checkpointer keyed by thread_id. If we construct a new
    service/agent on every request, multi-step HITL (start -> resume) cannot work.
    """
    global _issues_service

    if _issues_service is not None:
        return _issues_service

    async with _issues_service_lock:
        if _issues_service is not None:
            return _issues_service

        db_client = SQLiteClient()
        repo = IssuesRepository(db_client)
        await repo.init()
        pipeline = LangChainPipeline()
        _issues_service = IssuesService(repo, pipeline)
        return _issues_service


async def get_rules_service() -> RulesService:
    """
    Dependency that returns a singleton RulesService.
    """
    global _rules_service

    if _rules_service is not None:
        return _rules_service

    async with _rules_service_lock:
        if _rules_service is not None:
            return _rules_service

        db_client = SQLiteClient()
        repo = RulesRepository(db_client)
        await repo.init()
        _rules_service = RulesService(repo)
        return _rules_service


async def get_rule_documents_service() -> RuleDocumentsService:
    """
    Dependency that returns a singleton RuleDocumentsService.
    """
    global _rule_docs_service

    if _rule_docs_service is not None:
        return _rule_docs_service

    async with _rule_docs_service_lock:
        if _rule_docs_service is not None:
            return _rule_docs_service

        db_client = SQLiteClient()
        rule_docs_repo = RuleDocumentsRepository(db_client)
        await rule_docs_repo.init()
        rules_repo = RulesRepository(db_client)
        await rules_repo.init()
        _rule_docs_service = RuleDocumentsService(rule_docs_repo, rules_repo)
        return _rule_docs_service
