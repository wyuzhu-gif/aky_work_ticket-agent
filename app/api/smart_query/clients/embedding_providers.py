"""
嵌入向量提供者（多模型支持）
统一接口设计，支持 Jina、Qwen、BGE 等向量模型

迁移自 SQLAgent-dev: backend/vanna/src/Improve/clients/embedding_providers.py
"""

import logging
logger = logging.getLogger(__name__)
import os
import json
import requests
import numpy as np
from typing import List, Optional, Dict, Any


# ==================== 嵌入向量基类 ====================

class EmbeddingBase:
    """
    统一的嵌入向量基类
    
    子类只需实现 _embed(texts) 方法即可
    支持任意向量模型服务（Jina、Qwen、BGE、OpenAI等）
    """
    def __init__(
        self,
        api_url: str,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        timeout: int = 30,
        extra_headers: Optional[Dict[str, str]] = None,
    ):
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.model_name = model_name
        self.timeout = timeout
        self.extra_headers = extra_headers or {}
        self.embedding_dim = None

    # ==================== 统一的公开接口 ====================
    
    def encode_documents(self, documents: List[str]) -> np.ndarray:
        if not documents:
            return np.zeros((0, self.embedding_dim or 768), dtype=np.float32)
        return self._embed(documents)

    def encode_queries(self, queries: List[str]) -> np.ndarray:
        if not queries:
            return np.zeros((0, self.embedding_dim or 768), dtype=np.float32)
        return self._embed(queries)

    # ==================== 子类必须实现 ====================
    
    def _embed(self, texts: List[str]) -> np.ndarray:
        raise NotImplementedError("子类必须实现 _embed() 方法")

    # ==================== 工具方法：安全请求 ====================
    
    def _request_json(self, method: str, url: str, **kwargs) -> Any:
        headers = dict(self.extra_headers)
        if self.api_key:
            headers.setdefault("Authorization", f"Bearer {self.api_key}")
        headers.setdefault("Content-Type", "application/json")

        resp = requests.request(
            method, url, headers=headers, timeout=self.timeout, **kwargs
        )
        
        try:
            resp.raise_for_status()
        except requests.HTTPError as e:
            raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:400]}") from e
        
        try:
            return resp.json()
        except Exception as e:
            raise RuntimeError(f"Invalid JSON response: {resp.text[:400]}") from e


# ==================== Jina 向量模型 ====================

class JinaEmbedding(EmbeddingBase):
    """Jina Embeddings 适配器（本地/远程服务）"""
    def __init__(
        self,
        api_url: str = "http://127.0.0.1:8603/v1/embeddings",
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        timeout: int = 30,
        normalize: bool = True,
        pooling: str = "mean",
        extra_headers: Optional[Dict[str, str]] = None,
        skip_test: bool = False,
    ):
        super().__init__(api_url, api_key, model_name, timeout, extra_headers)
        self.normalize = normalize
        self.pooling = pooling
        
        if not skip_test:
            try:
                test_emb = self._embed(["ping"])
                self.embedding_dim = test_emb.shape[1]
                logger.info(f"Jina 连接成功: {api_url} (维度: {self.embedding_dim})")
            except Exception as e:
                logger.warning(f"Jina 连接测试失败: {e}")

    def _embed(self, texts: List[str]) -> np.ndarray:
        payload = {
            "inputs": [{"text": t} for t in texts],
            "normalize": self.normalize,
            "pooling": self.pooling,
        }
        if self.model_name:
            payload["model"] = self.model_name

        data = self._request_json("POST", self.api_url, json=payload)
        embs = data.get("embeddings")
        if not embs:
            raise RuntimeError(f"Empty embeddings from Jina: {data}")
        
        result = np.array(embs, dtype=np.float32)
        if self.embedding_dim is None:
            self.embedding_dim = result.shape[1]
        return result


# ==================== Qwen 向量模型（DashScope 兼容）====================

class QwenEmbedding(EmbeddingBase):
    """Qwen Embeddings 适配器（DashScope OpenAI-兼容接口）"""
    def __init__(
        self,
        api_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1",
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        timeout: int = 30,
        extra_headers: Optional[Dict[str, str]] = None,
    ):
        super().__init__(api_url, api_key, model_name, timeout, extra_headers)

    def _embed(self, texts: List[str]) -> np.ndarray:
        url = f"{self.api_url}/embeddings"
        payload = {"input": texts}
        if self.model_name:
            payload["model"] = self.model_name

        data = self._request_json("POST", url, json=payload)
        items = data.get("data")
        if not items:
            raise RuntimeError(f"Empty embeddings from Qwen: {data}")
        
        embs = [it.get("embedding") for it in items]
        result = np.array(embs, dtype=np.float32)
        if self.embedding_dim is None:
            self.embedding_dim = result.shape[1]
        return result


# ==================== BGE 向量模型 ====================

class BGEEmbedding(EmbeddingBase):
    """BGE (BAAI General Embedding) 适配器"""
    def __init__(
        self,
        api_url: str = "https://api-inference.huggingface.co/pipeline/feature-extraction",
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        timeout: int = 60,
        extra_headers: Optional[Dict[str, str]] = None,
        hf_task_style: bool = True,
    ):
        super().__init__(api_url, api_key, model_name, timeout, extra_headers)
        self.hf_task_style = hf_task_style

    def _embed(self, texts: List[str]) -> np.ndarray:
        if self.hf_task_style:
            url = f"{self.api_url}/{self.model_name}" if self.model_name else self.api_url
        else:
            url = self.api_url

        headers = dict(self.extra_headers)
        if self.api_key:
            headers.setdefault("Authorization", f"Bearer {self.api_key}")
        headers.setdefault("Content-Type", "application/json")

        resp = requests.post(url, headers=headers, json={"inputs": texts}, timeout=self.timeout)
        
        try:
            resp.raise_for_status()
        except requests.HTTPError as e:
            raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:400]}") from e

        try:
            data = resp.json()
        except Exception:
            try:
                data = json.loads(resp.text)
            except Exception as e:
                raise RuntimeError(f"Invalid response: {resp.text[:400]}") from e

        if isinstance(data, list) and data and isinstance(data[0], list) and isinstance(data[0][0], (int, float)):
            embs = data
        elif isinstance(data, list) and data and isinstance(data[0], (int, float)):
            embs = [data]
        else:
            embs = data.get("embeddings") or data.get("vectors") or data.get("data")
            if not embs:
                raise RuntimeError(f"Empty embeddings from BGE: {str(data)[:400]}")

        result = np.array(embs, dtype=np.float32)
        if self.embedding_dim is None:
            self.embedding_dim = result.shape[1]
        return result


def create_embedding_client(
    provider: str,
    api_url: Optional[str] = None,
    api_key: Optional[str] = None,
    model_name: Optional[str] = None,
    **kwargs
) -> EmbeddingBase:
    """创建嵌入向量客户端（工厂函数）"""
    provider = provider.lower()
    
    if provider == "jina":
        return JinaEmbedding(
            api_url=api_url or "http://127.0.0.1:8603/v1/embeddings",
            api_key=api_key,
            model_name=model_name,
            **kwargs
        )
    elif provider == "qwen":
        return QwenEmbedding(
            api_url=api_url or "https://dashscope.aliyuncs.com/compatible-mode/v1",
            api_key=api_key or os.getenv("DASHSCOPE_API_KEY"),
            model_name=model_name,
            **kwargs
        )
    elif provider == "bge":
        return BGEEmbedding(
            api_url=api_url or "https://api-inference.huggingface.co/pipeline/feature-extraction",
            api_key=api_key or os.getenv("HUGGINGFACE_API_KEY"),
            model_name=model_name,
            **kwargs
        )
    else:
        raise ValueError(
            f"Unsupported provider: {provider}. Supported: jina, qwen, bge"
        )
