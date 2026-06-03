"""
Vanna 基础模块（从 vanna.legacy 本地化迁移）

完全解耦对 pip 包 vanna 的依赖，将需要的模块内嵌到项目中。
原路径映射：
  vanna.legacy.base         -> .base
  vanna.legacy.milvus       -> .milvus
  vanna.legacy.openai       -> .openai
  vanna.legacy.exceptions   -> .exceptions
  vanna.legacy.types        -> .types
  vanna.legacy.utils        -> .utils
"""

from .exceptions import ValidationError, DependencyError, ImproperlyConfigured
from .types import TrainingPlan, TrainingPlanItem
from .base.base import VannaBase
from .milvus.milvus_vector import Milvus_VectorStore
from .openai.openai_chat import OpenAI_Chat

__all__ = [
    "VannaBase",
    "Milvus_VectorStore",
    "OpenAI_Chat",
    "ValidationError",
    "DependencyError",
    "ImproperlyConfigured",
    "TrainingPlan",
    "TrainingPlanItem",
]
