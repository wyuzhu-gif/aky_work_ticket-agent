from common.logger import get_logger
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from common.models import ReviewRule, DocumentRuleAssociation, RiskLevel, RuleExample, RuleStatusEnum, RuleFolder
from database.rules_repository import RulesRepository

logging = get_logger(__name__)


class RulesService:
    def __init__(self, rules_repository: RulesRepository) -> None:
        self.rules_repository = rules_repository

    # ========== Rules CRUD ==========

    async def get_all_rules(self) -> List[ReviewRule]:
        return await self.rules_repository.get_all_rules()

    async def get_active_rules(self) -> List[ReviewRule]:
        return await self.rules_repository.get_active_rules()

    async def get_rule(self, rule_id: str) -> ReviewRule:
        return await self.rules_repository.get_rule(rule_id)

    async def create_rule(
        self,
        name: str,
        description: str,
        risk_level: RiskLevel,
        prompt: Optional[str] = None,
        examples: Optional[List[RuleExample]] = None,
    ) -> ReviewRule:
        rule = ReviewRule(
            id=str(uuid4()),
            name=name,
            description=description,
            prompt=prompt,
            risk_level=risk_level,
            examples=examples or [],
            is_preset=False,
            status=RuleStatusEnum.active,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        return await self.rules_repository.create_rule(rule)

    async def update_rule(self, rule_id: str, fields: Dict[str, Any]) -> ReviewRule:
        fields["updated_at"] = datetime.now(timezone.utc).isoformat()
        return await self.rules_repository.update_rule(rule_id, fields)

    async def delete_rule(self, rule_id: str) -> None:
        await self.rules_repository.delete_rule(rule_id)

    # ========== Document-Rule Associations ==========

    async def get_document_rules(self, doc_id: str) -> List[DocumentRuleAssociation]:
        return await self.rules_repository.get_document_rules(doc_id)

    async def get_enabled_rules_for_document(self, doc_id: str) -> List[ReviewRule]:
        return await self.rules_repository.get_enabled_rules_for_document(doc_id)

    async def set_document_rule(self, doc_id: str, rule_id: str, enabled: bool) -> None:
        # Verify rule exists
        await self.rules_repository.get_rule(rule_id)
        await self.rules_repository.set_document_rule(doc_id, rule_id, enabled)

    # ========== Folder CRUD ==========

    async def get_all_folders(self) -> List[RuleFolder]:
        return await self.rules_repository.get_all_folders()

    async def get_folder(self, folder_id: str) -> RuleFolder:
        return await self.rules_repository.get_folder(folder_id)

    async def create_folder(self, name: str, description: str | None = None) -> RuleFolder:
        folder = RuleFolder(
            id=str(uuid4()),
            name=name,
            description=description,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        return await self.rules_repository.create_folder(folder)

    async def update_folder(self, folder_id: str, fields: Dict[str, Any]) -> RuleFolder:
        fields["updated_at"] = datetime.now(timezone.utc).isoformat()
        return await self.rules_repository.update_folder(folder_id, fields)

    async def set_default_folder(self, folder_id: str) -> RuleFolder:
        """Set a folder as default. Clears any existing default first."""
        # Clear existing defaults
        all_folders = await self.rules_repository.get_all_folders()
        for f in all_folders:
            if f.is_default:
                await self.rules_repository.update_folder(f.id, {"is_default": False})
        # Set new default
        return await self.rules_repository.update_folder(folder_id, {"is_default": True})

    async def get_default_folder(self) -> Optional[RuleFolder]:
        folders = await self.rules_repository.get_all_folders()
        for f in folders:
            if f.is_default:
                return f
        return None

    async def delete_folder(self, folder_id: str) -> None:
        await self.rules_repository.delete_folder(folder_id)

    async def get_rules_by_folder(self, folder_id: str) -> List[ReviewRule]:
        return await self.rules_repository.get_rules_by_folder(folder_id)

    async def get_rules_by_ids(self, rule_ids: List[str]) -> List[ReviewRule]:
        """Get multiple rules by their IDs."""
        rules = []
        for rule_id in rule_ids:
            try:
                rule = await self.rules_repository.get_rule(rule_id)
                if rule.status == RuleStatusEnum.active:
                    rules.append(rule)
            except ValueError:
                logging.warning(f"Rule {rule_id} not found, skipping.")
        return rules
