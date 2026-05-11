"""
fix_rule_folders.py
添加规则文件夹功能：
1. models.py — 新增 RuleFolder 模型，ReviewRule 添加 folder_id
2. db_client.py — 新增 rule_folders 表，rules 表添加 folder_id 列
3. rules_repository.py — 文件夹 CRUD + 按文件夹查询规则
4. rules_service.py — 文件夹 service 方法
5. rules.py router — 文件夹 CRUD API + 批量启用文件夹内规则
"""
from pathlib import Path

BASE = Path("/data/lvm_data_48T/wyuz/ai-document-review")


def patch_file(rel_path: str, patches: list[tuple[str, str]]):
    fp = BASE / rel_path
    text = fp.read_text(encoding="utf-8")
    for old, new in patches:
        if old not in text:
            print(f"  WARNING: not found in {rel_path}: {old[:80]}...")
            continue
        text = text.replace(old, new, 1)
    fp.write_text(text, encoding="utf-8")
    print(f"  PATCHED: {rel_path}")


def main():
    print("=== Step 1: common/models.py ===")
    patch_file("common/models.py", [
        # Add RuleFolder model before ReviewRule
        (
            """# ========== Review Rule ==========""",
            """# ========== Rule Folder ==========
class RuleFolder(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    created_at: str
    updated_at: Optional[str] = None


# ========== Review Rule ==========""",
        ),
        # Add folder_id to ReviewRule
        (
            """    is_preset: bool = False  # 是否为预设规则（不可删除，仅可停用）
    status: RuleStatusEnum = RuleStatusEnum.active""",
            """    folder_id: Optional[str] = None  # 所属文件夹
    is_preset: bool = False  # 是否为预设规则（不可删除，仅可停用）
    status: RuleStatusEnum = RuleStatusEnum.active""",
        ),
    ])

    print("=== Step 2: app/api/database/db_client.py ===")
    patch_file("app/api/database/db_client.py", [
        # Add rule_folders table creation
        (
            """CREATE_DOCUMENT_RULES_TABLE = \"\"\"""",
            """CREATE_RULE_FOLDERS_TABLE = \"\"\"
CREATE TABLE IF NOT EXISTS rule_folders (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT
);
\"\"\"

CREATE_DOCUMENT_RULES_TABLE = \"\"\"""",
        ),
        # Add folder_id to rules table
        (
            """    is_preset INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    updated_at TEXT
);
\"\"\"

CREATE_DOCUMENT_RULES_TABLE""",
            """    folder_id TEXT,
    is_preset INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    updated_at TEXT
);
\"\"\"

CREATE_DOCUMENT_RULES_TABLE""",
        ),
        # Add init_db for rule_folders table and migration
        (
            """            await db.execute(CREATE_DOCUMENT_RULES_TABLE)
            await db.execute(CREATE_RULE_DOCUMENTS_TABLE)
            await db.execute(CREATE_DOCUMENT_RULE_DOCUMENTS_TABLE)""",
            """            await db.execute(CREATE_RULE_FOLDERS_TABLE)
            await db.execute(CREATE_DOCUMENT_RULES_TABLE)
            await db.execute(CREATE_RULE_DOCUMENTS_TABLE)
            await db.execute(CREATE_DOCUMENT_RULE_DOCUMENTS_TABLE)""",
        ),
        # Add folder_id migration
        (
            """                except Exception:
                    pass

    async def store_item""",
            """                except Exception:
                    pass

            # Migration: Add folder_id to rules table
            try:
                await db.execute("ALTER TABLE rules ADD COLUMN folder_id TEXT")
                await db.commit()
                logging.info("Migration: Added folder_id to rules table")
            except Exception:
                pass

    async def store_item""",
        ),
    ])

    print("=== Step 3: app/api/database/rules_repository.py ===")
    patch_file("app/api/database/rules_repository.py", [
        # Import RuleFolder
        (
            """from common.models import ReviewRule, DocumentRuleAssociation""",
            """from common.models import ReviewRule, DocumentRuleAssociation, RuleFolder""",
        ),
        # Add folder CRUD methods before Serialization section
        (
            """    # ========== Serialization ==========""",
            """    # ========== Folder CRUD ==========

    async def get_all_folders(self) -> List[RuleFolder]:
        items = await self.db_client.retrieve_items_by_values("rule_folders", {})
        return [RuleFolder(**item) for item in items]

    async def get_folder(self, folder_id: str) -> RuleFolder:
        item = await self.db_client.retrieve_item_by_id("rule_folders", folder_id)
        if not item:
            raise ValueError(f"Folder {folder_id} not found.")
        return RuleFolder(**item)

    async def create_folder(self, folder: RuleFolder) -> RuleFolder:
        await self.db_client.store_item("rule_folders", folder.model_dump())
        return folder

    async def update_folder(self, folder_id: str, fields: Dict[str, Any]) -> RuleFolder:
        existing = await self.db_client.retrieve_item_by_id("rule_folders", folder_id)
        if not existing:
            raise ValueError(f"Folder {folder_id} not found.")
        existing.update(fields)
        await self.db_client.store_item("rule_folders", existing)
        return RuleFolder(**existing)

    async def delete_folder(self, folder_id: str) -> None:
        # Unlink all rules in this folder
        rules = await self.db_client.execute_query(
            "SELECT id FROM rules WHERE folder_id = ?", (folder_id,)
        )
        for r in rules:
            await self.db_client.execute_query(
                "UPDATE rules SET folder_id = NULL WHERE id = ?", (r["id"],)
            )
        await self.db_client.delete_item("rule_folders", folder_id)

    async def get_rules_by_folder(self, folder_id: str) -> List[ReviewRule]:
        items = await self.db_client.retrieve_items_by_values("rules", {"folder_id": folder_id})
        return [ReviewRule(**self._deserialize_rule(item)) for item in items]

    # ========== Serialization ==========""",
        ),
    ])

    print("=== Step 4: app/api/services/rules_service.py ===")
    patch_file("app/api/services/rules_service.py", [
        # Import RuleFolder
        (
            """from common.models import ReviewRule, DocumentRuleAssociation, RiskLevel, RuleExample, RuleStatusEnum""",
            """from common.models import ReviewRule, DocumentRuleAssociation, RiskLevel, RuleExample, RuleStatusEnum, RuleFolder""",
        ),
        # Add folder service methods
        (
            """    async def get_rules_by_ids""",
            """    # ========== Folder CRUD ==========

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

    async def delete_folder(self, folder_id: str) -> None:
        await self.rules_repository.delete_folder(folder_id)

    async def get_rules_by_folder(self, folder_id: str) -> List[ReviewRule]:
        return await self.rules_repository.get_rules_by_folder(folder_id)

    async def get_rules_by_ids""",
        ),
    ])

    print("=== Step 5: app/api/routers/rules.py ===")
    patch_file("app/api/routers/rules.py", [
        # Import RuleFolder
        (
            """from common.models import ReviewRule, DocumentRuleAssociation, RiskLevel, RuleExample""",
            """from common.models import ReviewRule, DocumentRuleAssociation, RiskLevel, RuleExample, RuleFolder""",
        ),
        # Add folder request models
        (
            """class SetDocumentRuleRequest(BaseModel):
    enabled: bool""",
            """class SetDocumentRuleRequest(BaseModel):
    enabled: bool


class CreateFolderRequest(BaseModel):
    name: str
    description: Optional[str] = None


class UpdateFolderRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class SetRuleFolderRequest(BaseModel):
    folder_id: Optional[str] = None  # null = remove from folder""",
        ),
        # Add UpdateRuleRequest folder_id support
        (
            """class UpdateRuleRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    prompt: Optional[str] = None
    risk_level: Optional[RiskLevel] = None
    examples: Optional[List[RuleExample]] = None
    status: Optional[str] = None""",
            """class UpdateRuleRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    prompt: Optional[str] = None
    risk_level: Optional[RiskLevel] = None
    examples: Optional[List[RuleExample]] = None
    folder_id: Optional[str] = None
    status: Optional[str] = None""",
        ),
        # Add folder endpoints before Document-Rule Association section
        (
            """# ========== Document-Rule Association Endpoints ==========""",
            """# ========== Folder CRUD Endpoints ==========

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


# ========== Document-Rule Association Endpoints ==========""",
        ),
    ])

    print("\nAll backend patches applied!")


if __name__ == "__main__":
    main()
