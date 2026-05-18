"""
作业票类型配置 - 每种作业票的表名、字段、提示词映射。
"""
from __future__ import annotations

# 八类特殊作业票
PERMIT_TYPES = {
    "hot_work": {
        "label": "动火作业",
        "table": "hot_work_permits",
        "gas_table": "hot_work_gas_analysis",
        "has_gas_analyses": True,
        "has_safety_checks": True,
    },
    "confined_space": {
        "label": "受限空间",
        "table": "confined_space_permits",
        "gas_table": "confined_space_gas_analysis",
        "has_gas_analyses": True,
        "has_safety_checks": False,
    },
    "blind_plate": {
        "label": "盲板抽堵",
        "table": "permit_blind_plate",
        "gas_table": None,
        "has_gas_analyses": False,
        "has_safety_checks": False,
    },
    # "高处作业": {"label": "高处作业", "table": "", "gas_table": None, "has_gas_analyses": False, "has_safety_checks": False},
    # "临时用电": {"label": "临时用电", "table": "", "gas_table": None, "has_gas_analyses": False, "has_safety_checks": False},
    # "吊装":    {"label": "吊装作业", "table": "", "gas_table": None, "has_gas_analyses": False, "has_safety_checks": False},
    # "动土":    {"label": "动土作业", "table": "", "gas_table": None, "has_gas_analyses": False, "has_safety_checks": False},
    # "断路":    {"label": "断路作业", "table": "", "gas_table": None, "has_gas_analyses": False, "has_safety_checks": False},
}


def get_permit_type(permit_type: str) -> dict:
    """Get config for a permit type, raise if not found."""
    cfg = PERMIT_TYPES.get(permit_type)
    if not cfg:
        raise ValueError(f"Unknown permit type: {permit_type}. Available: {list(PERMIT_TYPES.keys())}")
    return cfg


def list_permit_types() -> list[dict]:
    """Return all types for frontend selector."""
    return [{"key": k, "label": v["label"]} for k, v in PERMIT_TYPES.items()]
