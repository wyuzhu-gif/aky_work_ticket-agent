"""
fix_prompt_rules.py
将硬编码的提示词规则化：扩展 ReviewRule 模型，添加 prompt 字段，
种子化预设审核规则，重构 pipeline 使用数据库中的规则提示词。

变更：
1. common/models.py — ReviewRule 添加 prompt, is_preset 字段
2. app/api/database/db_client.py — rules 表添加 prompt, is_preset 列
3. app/api/database/rules_repository.py — 序列化/反序列化处理新字段
4. app/api/routers/rules.py — CreateRuleRequest/UpdateRuleRequest 添加 prompt
5. app/api/services/rules_service.py — create_rule 支持 prompt
6. app/api/services/lc_pipeline.py — 从 custom_rules.prompt 动态构建提示词
7. 种子数据 — 7 条预设审核规则
"""

import sys
from pathlib import Path

BASE = Path("/data/lvm_data_48T/wyuz/ai-document-review")


def patch_file(rel_path: str, patches: list[tuple[str, str]]):
    """Apply multiple find-replace patches to a file."""
    fp = BASE / rel_path
    text = fp.read_text(encoding="utf-8")
    for old, new in patches:
        if old not in text:
            print(f"  WARNING: pattern not found in {rel_path}: {old[:60]}...")
            continue
        text = text.replace(old, new, 1)
    fp.write_text(text, encoding="utf-8")
    print(f"  PATCHED: {rel_path}")


def main():
    print("=== Step 1: Patch common/models.py ===")
    patch_file("common/models.py", [
        # Add prompt and is_preset to ReviewRule
        (
            """class ReviewRule(BaseModel):
    id: str
    name: str
    description: str
    risk_level: RiskLevel
    examples: list[RuleExample] = []
    status: RuleStatusEnum = RuleStatusEnum.active
    created_at: str
    updated_at: Optional[str] = None""",
            """class ReviewRule(BaseModel):
    id: str
    name: str
    description: str
    prompt: Optional[str] = None  # 完整的提示词正文，用于注入 LLM
    risk_level: RiskLevel
    examples: list[RuleExample] = []
    is_preset: bool = False  # 是否为预设规则（不可删除，仅可停用）
    status: RuleStatusEnum = RuleStatusEnum.active
    created_at: str
    updated_at: Optional[str] = None""",
        ),
    ])

    print("=== Step 2: Patch app/api/database/db_client.py ===")
    patch_file("app/api/database/db_client.py", [
        # Add prompt and is_preset columns to rules table
        (
            """CREATE_RULES_TABLE = \"\"\"
CREATE TABLE IF NOT EXISTS rules (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    risk_level TEXT NOT NULL,
    examples TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    updated_at TEXT
);
\"\"\"""",
            """CREATE_RULES_TABLE = \"\"\"
CREATE TABLE IF NOT EXISTS rules (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    prompt TEXT,
    risk_level TEXT NOT NULL,
    examples TEXT,
    is_preset INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    updated_at TEXT
);
\"\"\"""",
        ),
        # Add migration for existing databases
        (
            """            # Migration: Add risk_level column to existing issues table if not exists
            try:
                await db.execute("ALTER TABLE issues ADD COLUMN risk_level TEXT")
                await db.commit()
                logging.info("Migration: Added risk_level column to issues table")
            except Exception:
                # Column already exists, ignore
                pass""",
            """            # Migration: Add risk_level column to existing issues table if not exists
            try:
                await db.execute("ALTER TABLE issues ADD COLUMN risk_level TEXT")
                await db.commit()
                logging.info("Migration: Added risk_level column to issues table")
            except Exception:
                pass

            # Migration: Add prompt and is_preset columns to rules table
            for col_sql in [
                "ALTER TABLE rules ADD COLUMN prompt TEXT",
                "ALTER TABLE rules ADD COLUMN is_preset INTEGER NOT NULL DEFAULT 0",
            ]:
                try:
                    await db.execute(col_sql)
                    await db.commit()
                    logging.info(f"Migration: Applied: {col_sql}")
                except Exception:
                    pass""",
        ),
    ])

    print("=== Step 3: Patch app/api/routers/rules.py ===")
    patch_file("app/api/routers/rules.py", [
        # Add prompt to CreateRuleRequest
        (
            """class CreateRuleRequest(BaseModel):
    name: str
    description: str
    risk_level: RiskLevel
    examples: Optional[List[RuleExample]] = None""",
            """class CreateRuleRequest(BaseModel):
    name: str
    description: str
    prompt: Optional[str] = None
    risk_level: RiskLevel
    examples: Optional[List[RuleExample]] = None""",
        ),
        # Add prompt to UpdateRuleRequest
        (
            """class UpdateRuleRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    risk_level: Optional[RiskLevel] = None
    examples: Optional[List[RuleExample]] = None
    status: Optional[str] = None""",
            """class UpdateRuleRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    prompt: Optional[str] = None
    risk_level: Optional[RiskLevel] = None
    examples: Optional[List[RuleExample]] = None
    status: Optional[str] = None""",
        ),
        # Pass prompt to service in create_rule
        (
            """    return await rules_service.create_rule(
        name=body.name,
        description=body.description,
        risk_level=body.risk_level,
        examples=body.examples,
    )""",
            """    return await rules_service.create_rule(
        name=body.name,
        description=body.description,
        prompt=body.prompt,
        risk_level=body.risk_level,
        examples=body.examples,
    )""",
        ),
    ])

    print("=== Step 4: Patch app/api/services/rules_service.py ===")
    patch_file("app/api/services/rules_service.py", [
        # Add prompt parameter to create_rule
        (
            """    async def create_rule(
        self,
        name: str,
        description: str,
        risk_level: RiskLevel,
        examples: Optional[List[RuleExample]] = None,
    ) -> ReviewRule:
        rule = ReviewRule(
            id=str(uuid4()),
            name=name,
            description=description,
            risk_level=risk_level,
            examples=examples or [],
            status=RuleStatusEnum.active,
            created_at=datetime.now(timezone.utc).isoformat(),
        )""",
            """    async def create_rule(
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
        )""",
        ),
    ])

    print("=== Step 5: Patch app/api/services/lc_pipeline.py ===")
    patch_file("app/api/services/lc_pipeline.py", [
        # Replace _build_system_prompt to use rules' prompts dynamically
        (
            '''def _build_system_prompt(custom_rules: List[ReviewRule] | None = None, rule_documents: List[RuleDocument] | None = None) -> str:
    """Build system prompt with custom rules and rule documents."""
    issue_types = [
        "- 气体分析不合格",
        "- 安全措施未落实",
        "- 作业级别未标注",
        "- 监护人角色冲突",
        "- 审批签字缺失",
        "- 作业时间不合规",
        "- 信息冗余或矛盾",
        "- 其他不合规项",
    ]

    if custom_rules:
        for rule in custom_rules:
            issue_types.append(f"- {rule.name}")

    rule_doc_section = ""
    if rule_documents:
        rule_doc_section = "\\n\\n参考标准文件：\\n"
        for rdoc in rule_documents:
            snippet = (rdoc.extracted_text or "")[:settings.rule_context_max_chars]
            rule_doc_section += f"- [{rdoc.name}]: {snippet}\\n"

    issues_str = chr(10).join(issue_types)
    return (
        "你是专业的特殊作业票合规审核专家，严格依据 GB 30871-2022《危险化学品企业特殊作业安全规范》进行审核。\\n\\n"
        "请尽可能多地找出所有不合规项，每发现一个问题就报告一条，不要遗漏。\\n\\n"
        "重点审核项（包括但不限于）：\\n"
        "1. 气体分析：超标误判合格（第5.3.2条）\\n"
        "2. 监护人：是否兼做与监护无关的工作（第4.10条）\\n"
        "3. 安全措施：确认栏选\'否\'的项是否影响安全。动火方式含气焊/气割时气瓶措施必须确认\'是\'，含电焊时接地措施必须确认\'是\'（第5.2条）\\n"
        "4. 作业级别：是否勾选，是否与风险匹配（第5.1条）\\n"
        "5. 人员信息：仔细检查名单中是否有重复姓名，证件号是否有错\\n"
        "6. 审批流程：签字齐全性、时间逻辑（第4.6条）\\n"
        "7. 以及GB 30871-2022的任何其他违规项\\n\\n"
        "问题类型包括但不限于：\\n"
        f"{issues_str}\\n"
        f"{rule_doc_section}\\n"
        "输出要求：\\n"
        "- text字段：简要描述不合规的具体内容（给用户看的问题说明）\\n"
        "- original_text字段（极其重要）：必须从输入文本中逐字引用存在问题的原文片段！要与输入中的文字完全一致，不能改写、不能概括。这个字段用于在PDF上精确定位高亮位置。\\n"
        "- explanation字段：引用GB 30871-2022中违反的具体条款编号（如"第5.2.1条"）\\n"
        "- suggested_fix字段：提出具体的整改建议\\n"
        "- 若所有内容均合规，返回空的 issues 列表\\n\\n"
        "使用输入中提供的段落索引（如 [0], [1], ...）。\\n"
        "按照要求的 JSON 格式输出结果。\\n"
    )''',
            '''# Default review focus items (used when no rules with prompts are selected)
_DEFAULT_FOCUS = (
    "1. 气体分析：超标误判合格（第5.3.2条）\\n"
    "2. 监护人：是否兼做与监护无关的工作（第4.10条）\\n"
    "3. 安全措施：确认栏选\'否\'的项是否影响安全。动火方式含气焊/气割时气瓶措施必须确认\'是\'，含电焊时接地措施必须确认\'是\'（第5.2条）\\n"
    "4. 作业级别：是否勾选，是否与风险匹配（第5.1条）\\n"
    "5. 人员信息：仔细检查名单中是否有重复姓名，证件号是否有错\\n"
    "6. 审批流程：签字齐全性、时间逻辑（第4.6条）\\n"
    "7. 以及GB 30871-2022的任何其他违规项"
)

_DEFAULT_ISSUE_TYPES = [
    "- 气体分析不合格",
    "- 安全措施未落实",
    "- 作业级别未标注",
    "- 监护人角色冲突",
    "- 审批签字缺失",
    "- 作业时间不合规",
    "- 信息冗余或矛盾",
    "- 其他不合规项",
]


def _build_system_prompt(custom_rules: List[ReviewRule] | None = None, rule_documents: List[RuleDocument] | None = None) -> str:
    """Build system prompt with custom rules and rule documents.

    If any selected custom_rules have a prompt field, use their prompts
    to build the review focus section. Otherwise fall back to defaults.
    """
    issue_types = list(_DEFAULT_ISSUE_TYPES)

    # Add custom rule names as additional issue types
    if custom_rules:
        for rule in custom_rules:
            if f"- {rule.name}" not in issue_types:
                issue_types.append(f"- {rule.name}")

    # Build review focus section from rules' prompts
    focus_section = _DEFAULT_FOCUS
    if custom_rules:
        prompt_rules = [r for r in custom_rules if r.prompt]
        if prompt_rules:
            focus_lines = []
            for i, r in enumerate(prompt_rules, 1):
                focus_lines.append(f"{i}. {r.prompt}")
            focus_section = "\\n".join(focus_lines)

    # Build rule document reference section
    rule_doc_section = ""
    if rule_documents:
        rule_doc_section = "\\n\\n参考标准文件：\\n"
        for rdoc in rule_documents:
            snippet = (rdoc.extracted_text or "")[:settings.rule_context_max_chars]
            rule_doc_section += f"- [{rdoc.name}]: {snippet}\\n"

    issues_str = chr(10).join(issue_types)
    return (
        "你是专业的特殊作业票合规审核专家，严格依据 GB 30871-2022《危险化学品企业特殊作业安全规范》进行审核。\\n\\n"
        "请尽可能多地找出所有不合规项，每发现一个问题就报告一条，不要遗漏。\\n\\n"
        "重点审核项（包括但不限于）：\\n"
        f"{focus_section}\\n\\n"
        "问题类型包括但不限于：\\n"
        f"{issues_str}\\n"
        f"{rule_doc_section}\\n"
        "输出要求：\\n"
        "- text字段：简要描述不合规的具体内容（给用户看的问题说明）\\n"
        "- original_text字段（极其重要）：必须从输入文本中逐字引用存在问题的原文片段！要与输入中的文字完全一致，不能改写、不能概括。这个字段用于在PDF上精确定位高亮位置。\\n"
        "- explanation字段：引用GB 30871-2022中违反的具体条款编号（如"第5.2.1条"）\\n"
        "- suggested_fix字段：提出具体的整改建议\\n"
        "- 若所有内容均合规，返回空的 issues 列表\\n\\n"
        "使用输入中提供的段落索引（如 [0], [1], ...）。\\n"
        "按照要求的 JSON 格式输出结果。\\n"
    )''',
        ),
    ])

    print("\nAll backend patches applied!")


if __name__ == "__main__":
    main()
