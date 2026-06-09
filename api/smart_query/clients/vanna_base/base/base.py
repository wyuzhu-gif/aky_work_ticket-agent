"""
VannaBase - 已精简版 (2026-06 清理)

只保留:
  1. __init__: 保存 config + 4 个属性 (max_tokens/dialect/language/run_sql_is_set)
  2. log / _response_language: 兼容性保留, 实际未调用

已删除 (~1700 行):
  - generate_sql / extract_sql / is_sql_valid / should_generate_chart
  - generate_rewritten_question / generate_followup_questions / generate_questions / generate_summary
  - ask / train / get_sql_prompt / add_ddl_to_prompt / add_documentation_to_prompt / add_sql_to_prompt
  - connect_to_snowflake / connect_to_mysql / connect_to_postgres 等 18 个数据库连接
  - get_training_plan_generic / get_plotly_figure 等
  - 所有 @abstractmethod (子类已全部实现, 不需要继承契约)
  - 巨量示例/注释/import (sqlparse, plotly, requests, sqlite3, traceback, urllib 等)

子类的实际实现 (Milvus_VectorStore / OpenAI_Chat / MyVanna) 已覆盖所有功能,
本项目通过 langchain+langgraph 自定义 agent 调用, 不走 Vanna 的 ask/generate_sql 路径。
"""

import json
from typing import List


class VannaBase:
    def __init__(self, config=None):
        if config is None:
            config = {}
        self.config = config
        self.run_sql_is_set = False
        self.static_documentation = ""
        self.dialect = self.config.get("dialect", "SQL")
        self.language = self.config.get("language", None)
        self.max_tokens = self.config.get("max_tokens", 14000)

    def log(self, message: str, title: str = "Info"):
        print(f"{title}: {message}")

    def _response_language(self) -> str:
        if self.language is None:
            return ""
        return f"Respond in the {self.language} language."

    def str_to_approx_token_count(self, string: str) -> int:
        return len(string) / 4
