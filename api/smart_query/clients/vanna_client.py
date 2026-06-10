"""
Vanna 客户端封装
提供批量优化的文本到SQL转换功能

迁移自 SQLAgent-dev: backend/vanna/src/Improve/clients/vanna_client.py
适配 vanna 2.x legacy 模块路径
"""

import logging
logger = logging.getLogger(__name__)
import os
import hashlib
from typing import List, Union, Literal

# 使用本地化的 vanna 基础模块，完全解耦对 pip 包 vanna 的依赖
from .vanna_base.milvus import Milvus_VectorStore
from .vanna_base.openai import OpenAI_Chat
from .vanna_base.exceptions import ValidationError
from .vanna_base.types import TrainingPlan, TrainingPlanItem
from pymilvus import MilvusClient
from openai import OpenAI

# 导入统一的嵌入向量接口
from .embedding_providers import EmbeddingBase, create_embedding_client

# 禁用遥测
os.environ['ANONYMIZED_TELEMETRY'] = 'False'
os.environ['CHROMA_TELEMETRY'] = 'False'


# ==================== pymysql % 格式化 bug 修复 (2026-06-10) ====================
# 背景: pymysql.cursors.Cursor.execute() 内部走 mogrify(query, args) -> query % self._escape_args(args, conn)
#       当 SQL 含中文 + % 通配符 (例如 "LIKE '%博航%'") 时, Python 把 % 当成字符串格式化符号,
#       "博" (0x535a) 被误识别为 format char, 抛 ValueError "unsupported format character"
# 修法: monkey-patch Cursor.mogrify, 如果 args 为空/None, 直接 query.encode() 返回, 跳过 % 格式化
#       (args 不空时才走原 mogrify, %s / %d 等 placeholder 仍正常工作)
import pymysql.cursors as _pymysql_cursors
_orig_pymysql_mogrify = _pymysql_cursors.Cursor.mogrify

def _safe_pymysql_mogrify(self, query, args=None):
    """pymysql Cursor.mogrify 的 safe 版本: args 为空时跳过 % 格式化"""
    if not args:
        # 没 args -> 直接 bytes(query) 返回, 不走 % 格式化
        # 原 Cursor.mogrify 返 str, 这里返 bytes (execute 接受 str 或 bytes)
        return query.encode() if isinstance(query, str) else query
    return _orig_pymysql_mogrify(self, query, args)

_pymysql_cursors.Cursor.mogrify = _safe_pymysql_mogrify
logger.info("pymysql.cursors.Cursor.mogrify monkey-patched to skip % formatting when args is empty")


# ==================== 优化版 Vanna 客户端 ====================

class MyVanna(Milvus_VectorStore, OpenAI_Chat):
    """
    批量优化的 Vanna 客户端
    - 支持批量训练（documentation, ddl）
    - 使用哈希 ID 自动去重
    - 批量向量化，提升 10-100 倍性能
    - 支持自定义向量相似度度量方式（cosine, L2, IP）
    """
    
    def __init__(self, config=None):
        Milvus_VectorStore.__init__(self, config=config)
        OpenAI_Chat.__init__(self, config=config)
        
        self.metric_type = config.get("metric_type", "COSINE") if config else "COSINE"
        
        valid_metrics = ["L2", "IP", "COSINE"]
        if self.metric_type.upper() not in valid_metrics:
            raise ValueError(f"Invalid metric_type: {self.metric_type}. Must be one of {valid_metrics}")
        
        self.metric_type = self.metric_type.upper()
        logger.info(f"Vector similarity metric type: {self.metric_type}")

    def _get_content_hash(self, text: str) -> str:
        """计算文本的 MD5 哈希值作为 ID"""
        return hashlib.md5(text.encode('utf-8')).hexdigest() + "-hash"
    
    def _check_exists_by_ids(self, collection_name: str, doc_ids: List[str]) -> dict:
        """批量检查多个 ID 是否存在"""
        if not doc_ids:
            return {}
        
        try:
            ids_str = ', '.join([f'"{id}"' for id in doc_ids])
            filter_expr = f'id in [{ids_str}]'
            
            result = self.milvus_client.query(
                collection_name=collection_name,
                filter=filter_expr,
                output_fields=["id"],
                limit=len(doc_ids)
            )
            
            existing_ids = {item['id'] for item in result}
            return {doc_id: doc_id in existing_ids for doc_id in doc_ids}
            
        except Exception as e:
            logger.warning(f"Batch query failed: {e}, falling back to individual queries")
            return {doc_id: self._check_exists_by_id(collection_name, doc_id) for doc_id in doc_ids}
    
    def _check_exists_by_id(self, collection_name: str, doc_id: str) -> bool:
        """单个 ID 检查（降级方案）"""
        try:
            result = self.milvus_client.query(
                collection_name=collection_name,
                filter=f'id == "{doc_id}"',
                output_fields=["id"],
                limit=1
            )
            return len(result) > 0
        except Exception as e:
            logger.warning(f"Query failed: {e}")
            return False
    
    # ==================== 批量插入核心方法 ====================
    
    def add_documentation(self, documentation: Union[str, List[str]], **kwargs) -> Union[str, List[str]]:
        """添加文档（支持单条或批量）"""
        is_single = isinstance(documentation, str)
        docs = [documentation] if is_single else documentation
        
        if not docs or (is_single and len(documentation) == 0):
            raise Exception("documentation can not be null")
        
        doc_ids = [self._get_content_hash(doc) for doc in docs]
        exists_map = self._check_exists_by_ids(self._doc_collection, doc_ids)
        
        to_insert = []
        for doc, doc_id in zip(docs, doc_ids):
            if exists_map.get(doc_id, False):
                logger.info(f"Document already exists: {doc_id[:20]}...")
            else:
                to_insert.append((doc, doc_id))
        
        if to_insert:
            texts = [doc for doc, _ in to_insert]
            logger.info(f"Generating {len(texts)} embeddings in batch...")
            embeddings = self.embedding_function.encode_documents(texts)
            
            insert_data = [
                {
                    "id": doc_id,
                    "doc": doc,
                    "vector": embedding.tolist() if hasattr(embedding, 'tolist') else embedding
                }
                for (doc, doc_id), embedding in zip(to_insert, embeddings)
            ]
            
            self.milvus_client.insert(collection_name=self._doc_collection, data=insert_data)
            logger.info(f"Successfully inserted {len(insert_data)} new documents in batch")
        
        return doc_ids[0] if is_single else doc_ids
    
    def add_ddl(self, ddl: Union[str, List[str]], **kwargs) -> Union[str, List[str]]:
        """添加 DDL（支持单条或批量）"""
        is_single = isinstance(ddl, str)
        ddls = [ddl] if is_single else ddl
        
        if not ddls or (is_single and len(ddl) == 0):
            raise Exception("ddl can not be null")
        
        ddl_ids = [self._get_content_hash(d) for d in ddls]
        exists_map = self._check_exists_by_ids(self._ddl_collection, ddl_ids)
        
        to_insert = []
        for d, ddl_id in zip(ddls, ddl_ids):
            if exists_map.get(ddl_id, False):
                logger.info(f"DDL already exists: {ddl_id[:20]}...")
            else:
                to_insert.append((d, ddl_id))
        
        if to_insert:
            texts = [d for d, _ in to_insert]
            logger.info(f"Generating {len(texts)} DDL embeddings in batch...")
            embeddings = self.embedding_function.encode_documents(texts)
            
            insert_data = [
                {
                    "id": ddl_id,
                    "ddl": d,
                    "vector": embedding.tolist() if hasattr(embedding, 'tolist') else embedding
                }
                for (d, ddl_id), embedding in zip(to_insert, embeddings)
            ]
            
            self.milvus_client.insert(collection_name=self._ddl_collection, data=insert_data)
            logger.info(f"Successfully inserted {len(insert_data)} new DDLs in batch")
        
        return ddl_ids[0] if is_single else ddl_ids
    
    # ==================== 重写 train 方法 ====================
    def train(
        self,
        question: str = None,
        sql: str = None,
        ddl: Union[str, List[str]] = None,
        documentation: Union[str, List[str]] = None,
        plan: TrainingPlan = None,
    ) -> Union[str, List[str], None]:
        """训练 Vanna（支持批量）"""
        if question and not sql:
            raise ValidationError("Please also provide a SQL query")

        if sql:
            if question is None:
                question = self.generate_question(sql)
                logger.info("Question generated with sql:", question, "\nAdding SQL...")
            return self.add_question_sql(question=question, sql=sql)
        
        if documentation is not None:
            is_list = isinstance(documentation, list)
            count = len(documentation) if is_list else 1
            logger.info(f"Adding {count} document(s)...")
            return self.add_documentation(documentation)
        
        if ddl is not None:
            is_list = isinstance(ddl, list)
            count = len(ddl) if is_list else 1
            logger.info(f"Adding {count} DDL(s)...")
            return self.add_ddl(ddl)
        
        if plan:
            logger.info(f"Processing training plan ({len(plan._plan)} items total)...")
            
            ddls_to_add = []
            docs_to_add = []
            sqls_to_add = []
            
            for item in plan._plan:
                if item.item_type == TrainingPlanItem.ITEM_TYPE_DDL:
                    ddls_to_add.append(item.item_value)
                elif item.item_type == TrainingPlanItem.ITEM_TYPE_IS:
                    docs_to_add.append(item.item_value)
                elif item.item_type == TrainingPlanItem.ITEM_TYPE_SQL:
                    sqls_to_add.append((item.item_name, item.item_value))
            
            if ddls_to_add:
                logger.info(f"\nAdding {len(ddls_to_add)} DDL(s) in batch...")
                self.add_ddl(ddls_to_add)
            
            if docs_to_add:
                logger.info(f"\nAdding {len(docs_to_add)} document(s) in batch...")
                self.add_documentation(docs_to_add)
            
            if sqls_to_add:
                logger.info(f"\nAdding {len(sqls_to_add)} SQL(s) individually...")
                for question, sql in sqls_to_add:
                    self.add_question_sql(question=question, sql=sql)
            
            logger.info("\nTraining plan execution completed successfully!")
            return None
        
        logger.warning("No training data provided")
        return None

    # ==================== 重写 remove_training_data 方法 ====================
    def remove_training_data(self, id: str, **kwargs) -> bool:
        """删除训练数据（支持 -hash 后缀的 ID）"""
        if not id:
            logger.warning("Deletion failed: ID cannot be empty")
            return False

        try:
            if id.endswith("-hash"):
                for collection_name in [self._sql_collection, self._ddl_collection, self._doc_collection]:
                    try:
                        result = self.milvus_client.query(
                            collection_name=collection_name,
                            filter=f'id == "{id}"',
                            output_fields=["id"],
                            limit=1
                        )
                        if result and len(result) > 0:
                            self.milvus_client.delete(
                                collection_name=collection_name,
                                ids=[id]
                            )
                            logger.info(f"Successfully deleted ID from {collection_name}: {id}")
                            return True
                    except Exception as e:
                        logger.debug(f"在 {collection_name} 中查询 {id} 失败: {e}")
                        continue

                logger.warning(f"Deletion failed: ID {id} not found in any collection")
                return False

            elif id.endswith("-sql"):
                self.milvus_client.delete(collection_name=self._sql_collection, ids=[id])
                logger.info(f"Successfully deleted ID from {self._sql_collection}: {id}")
                return True
            elif id.endswith("-ddl"):
                self.milvus_client.delete(collection_name=self._ddl_collection, ids=[id])
                logger.info(f"Successfully deleted ID from {self._ddl_collection}: {id}")
                return True
            elif id.endswith("-doc"):
                self.milvus_client.delete(collection_name=self._doc_collection, ids=[id])
                logger.info(f"Successfully deleted ID from {self._doc_collection}: {id}")
                return True
            else:
                logger.warning(f"Deletion failed: Invalid ID format {id}")
                return False

        except Exception as e:
            logger.error(f"Failed to delete training data: {e}")
            return False


# ==================== 数据库连接 (MySQL 8.0) ====================

    def connect_to_mysql(
        self,
        host: str,
        dbname: str,
        user: str,
        password: str,
        port: int = 3306,
        **kwargs,
    ) -> None:
        """
        Connect to MySQL 8.0 via SQLAlchemy + PyMySQL.

        用 SQLAlchemy 抽象层:
          - run_sql() 用 pandas.read_sql, 跟 PG 走同一路径
          - DDL/Doc/SQL 训练数据走 Milvus (不依赖此连接)
          - 同接口形状, 跟原 connect_to_postgres 保持一致

        Args:
            host: MySQL host (e.g. '10.8.0.100')
            dbname: 数据库名 (e.g. 'special_operations')
            user: 数据库用户
            password: 数据库密码
            port: 端口 (默认 3306)
        """
        import sqlalchemy
        # 注意: charset 必须 utf8mb4 支持中文/表情
        url = (
            f"mysql+pymysql://{user}:{password}@{host}:{port}/{dbname}"
            f"?charset=utf8mb4&connect_timeout=5"
        )
        engine = sqlalchemy.create_engine(url)

        # 替换原 PG 的 connect_to_postgres: 把 engine 挂到 self 上
        self.engine = engine
        self.dialect = "MySQL"
        logger.info(f"Connected to MySQL: {host}:{port}/{dbname}")

    def connect_to_postgres(self, *args, **kwargs):
        """
        兼容旧接口: 项目已经全面迁到 MySQL, 此方法 fallback 到 MySQL 连接.
        保留是为了不破坏可能存在的旧调用.
        """
        logger.warning("connect_to_postgres is deprecated, calling connect_to_mysql instead")
        return self.connect_to_mysql(*args, **kwargs)

    def run_sql(self, sql: str, **kwargs):
        """
        执行 SQL, 返回 DataFrame.

        兼容 Vanna 旧接口, 同时给智能问数工具调用使用.
        """
        import pandas as pd
        try:
            if hasattr(self, "engine") and self.engine is not None:
                return pd.read_sql(sql, self.engine)
            raise RuntimeError("No engine configured - call connect_to_mysql() first")
        except Exception as e:
            logger.error(f"run_sql failed: {e}")
            raise


# ==================== 客户端工厂函数 ====================
def create_vanna_client(
    # 必填参数：LLM 配置
    openai_api_key: str,
    openai_base_url: str,
    model: str,
    # 必填参数：Milvus 配置
    milvus_uri: str,
    # 必填参数：Embedding 配置
    embedding_api_url: str,
    # 可选参数：Embedding 提供商和认证
    embedding_provider: Literal["jina", "qwen", "bge"] = "jina",
    embedding_api_key: str = None,
    embedding_model_name: str = None,
    # 可选参数：Milvus 度量方式
    metric_type: str = "COSINE",
    # 可选参数：LLM 生成参数
    temperature: float = 0.2,
    max_tokens: int = 14000,
    # 可选参数：SQL 方言和语言
    dialect: str = "MySQL",
    language: str = "zh-CN",
) -> MyVanna:
    """创建 Vanna 客户端实例"""
    # 创建嵌入模型客户端
    embedding_function = create_embedding_client(
        provider=embedding_provider,
        api_url=embedding_api_url,
        api_key=embedding_api_key,
        model_name=embedding_model_name,
    )
    
    logger.info(f"Apply Embedding: {embedding_provider.upper()} ({embedding_api_url})")
    
    # 连接 Milvus
    milvus_client = MilvusClient(uri=milvus_uri)
    logger.info(f"Success connect to Milvus: {milvus_uri}")
    
    # 创建 OpenAI 客户端
    openai_client = OpenAI(
        api_key=openai_api_key,
        base_url=openai_base_url
    )
    
    # 初始化 Vanna
    vn = MyVanna(config={
        'model': model,
        'milvus_uri': milvus_uri,
        'embedding_function': embedding_function,
        'milvus_client': milvus_client,
        'temperature': temperature,
        'max_tokens': max_tokens,
        'dialect': dialect,
        'language': language,
        'metric_type': metric_type,
    })
    
    vn.client = openai_client
    vn.run_sql_is_set = True
    vn.static_documentation = ""
    
    return vn
