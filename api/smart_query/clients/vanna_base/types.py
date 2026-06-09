"""
Vanna types - 已精简 (2026-06 清理)

只保留 TrainingPlan / TrainingPlanItem (MyVanna.train 使用)
已删除 24 个未用 dataclass (Status, QuestionList, Organization, ApiKey, Connection, 等)
"""
from dataclasses import dataclass
from typing import List


@dataclass
class TrainingPlanItem:
    item_type: str
    item_group: str
    item_name: str
    item_value: str

    def __str__(self):
        if self.item_type == self.ITEM_TYPE_SQL:
            return f"Train on SQL: {self.item_group} {self.item_name}"
        elif self.item_type == self.ITEM_TYPE_DDL:
            return f"Train on DDL: {self.item_group} {self.item_name}"
        elif self.item_type == self.ITEM_TYPE_IS:
            return f"Train on Information Schema: {self.item_group} {self.item_name}"

    ITEM_TYPE_SQL = "sql"
    ITEM_TYPE_DDL = "ddl"
    ITEM_TYPE_IS = "is"


class TrainingPlan:
    """
    Training plan for batch training (MyVanna.train())
    """

    def __init__(self, plan: List[TrainingPlanItem] = None):
        self._plan = plan or []

    def get_items(self) -> List[TrainingPlanItem]:
        return self._plan
