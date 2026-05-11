"""
seed_preset_rules.py
将7条预设审核规则种子数据写入数据库。
直接使用 sqlite3 操作，不依赖项目模块。
"""

import sqlite3
from pathlib import Path
from datetime import datetime, timezone

DB_PATH = Path("/data/lvm_data_48T/wyuz/ai-document-review/app/api/data/review.db")
# Fallback: try to find the db
if not DB_PATH.exists():
    # Search for .db files
    for p in Path("/data/lvm_data_48T/wyuz/ai-document-review").rglob("*.db"):
        print(f"Found DB: {p}")
        DB_PATH = p
        break

PRESET_RULES = [
    {
        "id": "preset-gas-analysis",
        "name": "气体分析审核",
        "description": "检查气体分析结果是否超标误判合格，确认可燃气体、有毒气体、氧含量检测是否合规",
        "prompt": "重点审核气体分析结果：检查可燃气体、有毒气体、氧含量检测结果是否超标误判合格。依据GB 30871-2022第5.3.2条，气体分析结果不合格时不得进行作业。确认分析数据是否真实，取样位置和时间是否合理。",
        "risk_level": "高",
    },
    {
        "id": "preset-guardian",
        "name": "监护人审核",
        "description": "检查监护人是否履职，是否兼做与监护无关的工作",
        "prompt": "检查监护人职责：监护人是否兼做与监护无关的工作。依据GB 30871-2022第4.10条，监护人必须全程在现场监护，不得擅自离开或从事其他工作。确认监护人是否具备相应资质。",
        "risk_level": "高",
    },
    {
        "id": "preset-safety-measures",
        "name": "安全措施审核",
        "description": "检查安全措施落实情况，交叉验证动火方式与安全措施确认项",
        "prompt": "检查安全措施落实情况：确认栏选'否'的项是否影响安全。交叉检查动火方式与安全措施确认项——如果动火方式包含气焊/气割，对应气瓶安全措施必须确认'是'；如果包含电焊，对应电焊机接地措施必须确认'是'。依据GB 30871-2022第5.2条。",
        "risk_level": "高",
    },
    {
        "id": "preset-work-level",
        "name": "作业级别审核",
        "description": "检查作业级别是否正确标注，是否与实际风险匹配",
        "prompt": "检查作业级别标注：是否已勾选作业级别，级别是否与实际风险匹配。特级、一级、二级动火作业的审批权限和安全管理要求不同，确认级别选择是否正确。依据GB 30871-2022第5.1条。",
        "risk_level": "中",
    },
    {
        "id": "preset-personnel",
        "name": "人员信息审核",
        "description": "检查人员名单是否有重复，证件号是否正确",
        "prompt": "仔细检查所有人员名单（动火人、监护人、审批人、分析人）中是否有重复出现的姓名，证件号是否有错误。同一个人不应在不同角色中出现冲突（如既是动火人又是监护人），特种作业人员应持有有效证件。",
        "risk_level": "中",
    },
    {
        "id": "preset-approval",
        "name": "审批流程审核",
        "description": "检查审批签字齐全性和时间逻辑",
        "prompt": "检查审批流程完整性：各级审批签字是否齐全（申请部门、安全部门、主管领导等），审批时间逻辑是否合理（申请时间应早于审批时间，审批时间应早于作业开始时间）。依据GB 30871-2022第4.6条。",
        "risk_level": "中",
    },
    {
        "id": "preset-other-gb30871",
        "name": "GB 30871-2022 其他合规审核",
        "description": "检查GB 30871-2022的其他违规项，包括作业时间、信息冗余等",
        "prompt": "检查是否存在GB 30871-2022的其他违规项，包括但不限于：作业时间是否在有效期内、作业内容与票面是否一致、是否存在信息冗余或矛盾（如同一内容重复填写、前后信息不一致等）、作业票有效期是否合规。",
        "risk_level": "低",
    },
]


def main():
    print(f"Using DB: {DB_PATH}")
    if not DB_PATH.exists():
        print("ERROR: Database not found!")
        return

    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")

    # Ensure columns exist
    for col_sql in [
        "ALTER TABLE rules ADD COLUMN prompt TEXT",
        "ALTER TABLE rules ADD COLUMN is_preset INTEGER NOT NULL DEFAULT 0",
    ]:
        try:
            conn.execute(col_sql)
            conn.commit()
            print(f"  Migration: {col_sql}")
        except sqlite3.OperationalError:
            pass

    now = datetime.now(timezone.utc).isoformat()
    created = 0
    skipped = 0

    for item in PRESET_RULES:
        # Check if already exists
        row = conn.execute("SELECT id FROM rules WHERE id = ?", (item["id"],)).fetchone()
        if row:
            print(f"  SKIP (exists): {item['name']}")
            skipped += 1
            continue

        conn.execute(
            """INSERT OR REPLACE INTO rules (id, name, description, prompt, risk_level, examples, is_preset, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (item["id"], item["name"], item["description"], item["prompt"],
             item["risk_level"], "[]", 1, "active", now),
        )
        print(f"  SEEDED: {item['name']}")
        created += 1

    conn.commit()
    conn.close()
    print(f"\nDone: {created} created, {skipped} skipped")


if __name__ == "__main__":
    main()
