"""
fix_default_folder.py
给 RuleFolder 添加 is_default 功能：
1. models.py — RuleFolder 加 is_default
2. db_client.py — rule_folders 表加 is_default 列 + 迁移
3. rules.py router — updateFolder 支持 is_default，设置默认时清除其他默认
4. 前端类型、RuleLibrary 设为默认按钮、RulesPanel 自动选中默认文件夹
"""
from pathlib import Path

BASE = Path("/data/lvm_data_48T/wyuz/ai-document-review")
UI_BASE = BASE / "app/ui/src"


def patch_file(rel_path, patches):
    fp = BASE / rel_path
    text = fp.read_text(encoding="utf-8")
    for old, new in patches:
        if old not in text:
            print(f"  WARNING: not found in {rel_path}: {old[:70]}...")
            continue
        text = text.replace(old, new, 1)
    fp.write_text(text, encoding="utf-8")
    print(f"  PATCHED: {rel_path}")


def main():
    # ============ BACKEND ============
    print("=== Backend: models.py ===")
    patch_file("common/models.py", [
        (
            """class RuleFolder(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    created_at: str
    updated_at: Optional[str] = None""",
            """class RuleFolder(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    is_default: bool = False
    created_at: str
    updated_at: Optional[str] = None""",
        ),
    ])

    print("=== Backend: db_client.py ===")
    patch_file("app/api/database/db_client.py", [
        # Add is_default to CREATE TABLE
        (
            """CREATE TABLE IF NOT EXISTS rule_folders (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT
);""",
            """CREATE TABLE IF NOT EXISTS rule_folders (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    is_default INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT
);""",
        ),
        # Add migration after folder_id migration
        (
            """            # Migration: Add folder_id to rules table
            try:
                await db.execute("ALTER TABLE rules ADD COLUMN folder_id TEXT")
                await db.commit()
                logging.info("Migration: Added folder_id to rules table")
            except Exception:
                pass""",
            """            # Migration: Add folder_id to rules table
            try:
                await db.execute("ALTER TABLE rules ADD COLUMN folder_id TEXT")
                await db.commit()
                logging.info("Migration: Added folder_id to rules table")
            except Exception:
                pass

            # Migration: Add is_default to rule_folders table
            try:
                await db.execute("ALTER TABLE rule_folders ADD COLUMN is_default INTEGER NOT NULL DEFAULT 0")
                await db.commit()
                logging.info("Migration: Added is_default to rule_folders table")
            except Exception:
                pass""",
        ),
    ])

    print("=== Backend: rules_service.py — set_default_folder ===")
    patch_file("app/api/services/rules_service.py", [
        (
            """    async def delete_folder""",
            """    async def set_default_folder(self, folder_id: str) -> RuleFolder:
        \"\"\"Set a folder as default. Clears any existing default first.\"\"\"
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

    async def delete_folder""",
        ),
    ])

    print("=== Backend: rules.py router — default folder endpoints ===")
    patch_file("app/api/routers/rules.py", [
        # Add Optional import
        (
            "from typing import List, Optional",
            "from typing import List, Optional\nimport json",
        ),
        # Add default folder endpoints after folder CRUD
        (
            """# ========== Document-Rule Association Endpoints ==========""",
            """@router.put(
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


# ========== Document-Rule Association Endpoints ==========""",
        ),
    ])

    # Verify backend syntax
    import subprocess
    for f in ["common/models.py", "app/api/database/db_client.py", "app/api/services/rules_service.py", "app/api/routers/rules.py"]:
        r = subprocess.run(["python3", "-m", "py_compile", str(BASE / f)], capture_output=True, text=True)
        if r.returncode != 0:
            print(f"  SYNTAX ERROR in {f}: {r.stderr}")
        else:
            print(f"  SYNTAX OK: {f}")

    # ============ FRONTEND ============
    print("\n=== Frontend: types/rule.ts ===")
    fp = UI_BASE / "types/rule.ts"
    text = fp.read_text(encoding="utf-8")
    text = text.replace(
        "export interface RuleFolder {\n  id: string\n  name: string\n  description: string | null\n  created_at: string\n  updated_at?: string\n}",
        "export interface RuleFolder {\n  id: string\n  name: string\n  description: string | null\n  is_default: boolean\n  created_at: string\n  updated_at?: string\n}",
    )
    fp.write_text(text, encoding="utf-8")
    print("  PATCHED: types/rule.ts")

    print("=== Frontend: services/api.ts — add setDefaultFolder ===")
    fp = UI_BASE / "services/api.ts"
    text = fp.read_text(encoding="utf-8")
    text = text.replace(
        "export async function getFolderRules",
        """export async function setDefaultFolder(folderId: string): Promise<RuleFolder> {
  const response = await fetch(`${foldersApiUrl}/${folderId}/default`, {
    headers: { 'Content-Type': 'application/json' }, method: 'PUT'
  })
  if (!response.ok) throw new FatalError(await getErrorMessage(response))
  return response.json()
}

export async function getDefaultFolder(): Promise<RuleFolder | null> {
  const response = await fetch(`${foldersApiUrl}/default`, {
    headers: { 'Content-Type': 'application/json' }, method: 'GET'
  })
  if (!response.ok) throw new FatalError(await getErrorMessage(response))
  const data = await response.json()
  return data.default_folder
}

export async function getFolderRules""",
    )
    fp.write_text(text, encoding="utf-8")
    print("  PATCHED: services/api.ts")

    print("\nDone! Now update RuleLibrary.tsx and RulesPanel.tsx...")


if __name__ == "__main__":
    main()
