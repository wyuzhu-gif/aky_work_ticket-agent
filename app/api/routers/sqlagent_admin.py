"""Proxy router: forward SQLAgent project admin requests."""
import logging
import httpx
from fastapi import APIRouter, HTTPException, Request
from config.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/sqlagent", tags=["sqlagent-admin"])

BASE = lambda path: (
    f"{settings.sqlagent_url.rstrip('/')}/api/v1/projects/{settings.sqlagent_project_id}{path}"
)


async def _proxy(method: str, path: str, body: dict | None = None, params: dict | None = None):
    url = BASE(path)
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.request(method, url, json=body, params=params)
            if resp.status_code >= 400:
                detail = resp.text[:500]
                logger.error(f"SQLAgent proxy error {resp.status_code}: {detail}")
                raise HTTPException(status_code=resp.status_code, detail=detail)
            return resp.json()
    except httpx.ConnectError:
        raise HTTPException(status_code=502, detail="SQLAgent 服务不可用")


# ──────────────── LLM Config ────────────────

@router.get("/llm-config")
async def get_llm_config():
    return await _proxy("GET", "/llm-config")


@router.put("/llm-config")
async def set_llm_config(request: Request):
    body = await request.json()
    return await _proxy("PUT", "/llm-config", body=body)


@router.post("/llm-test")
async def test_llm(request: Request):
    body = await request.json()
    return await _proxy("POST", "/llm-test", body=body)


# ──────────────── DB Config ────────────────

@router.get("/db-config")
async def get_db_config():
    return await _proxy("GET", "/db-config")


@router.put("/db-config")
async def set_db_config(request: Request):
    body = await request.json()
    return await _proxy("PUT", "/db-config", body=body)


@router.post("/db-test")
async def test_db(request: Request):
    body = await request.json()
    return await _proxy("POST", "/db-test", body=body)


# ──────────────── Training Data ────────────────

@router.get("/training")
async def get_training(training_type: str | None = None):
    params = {"training_type": training_type} if training_type else None
    return await _proxy("GET", "/training/get", params=params)


@router.post("/training/add")
async def add_training(request: Request):
    body = await request.json()
    return await _proxy("POST", "/training/add", body=body)


@router.delete("/training/{item_id}")
async def delete_training(item_id: str):
    return await _proxy("DELETE", "/training/delete", params={"item_id": item_id})


# ──────────────── Agent Config ────────────────

@router.get("/agent-config")
async def get_agent_config():
    return await _proxy("GET", "/agent-config")


@router.put("/agent-config")
async def set_agent_config(request: Request):
    body = await request.json()
    return await _proxy("PUT", "/agent-config", body=body)
