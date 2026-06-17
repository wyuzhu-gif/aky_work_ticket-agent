"""
Wiki 知识库检索接口 — 给智能问数用。

每个 AI 回答完成后，前端会调用此接口获取相关 GB/AQ/行标条款作为知识引用。
底层复用 service/wiki_search.py 已建好的 FTS5 索引，不需要 Milvus/embedding 依赖。
"""

import time
from fastapi import APIRouter, Query, Request

from services.wiki_search import get_wiki_search
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/wiki", tags=["智能问数-知识检索"])


@router.get("")
async def search_wiki(
    request: Request,
    q: str = Query(default="", min_length=1, description="搜索关键词"),
):
    """搜索 Hermes 安全生产知识库，返回匹配页面+内容片段。"""
    start_ts = time.time()
    client_ip = request.client.host if request.client else "-"
    user_agent = request.headers.get("user-agent", "-")
    referer = request.headers.get("referer", "-")

    logger.info(
        f"[WIKI_REQ] 收到检索请求: q={q!r} ip={client_ip} ua={user_agent[:50]} referer={referer[:80]}"
    )

    wc = get_wiki_search()
    search_start = time.time()
    results = wc.search(q, limit=5)
    search_ms = (time.time() - search_start) * 1000

    logger.info(
        f"[WIKI_SEARCH] query={q!r} → {len(results)} 条结果, search耗时={search_ms:.1f}ms, 索引库={wc.db_path}"
    )

    # 逐页读取 content（snippet 不够展开用）
    content_start = time.time()
    for i, r in enumerate(results):
        content = wc.get_page(r["filepath"])
        if content and len(content) > 3000:
            content = content[:3000] + "\n...(已截断)"
        r["content"] = content or ""
    content_ms = (time.time() - content_start) * 1000

    total_ms = (time.time() - start_ts) * 1000

    # 详细记录返回的每条结果
    if results:
        logger.info(f"[WIKI_RESULTS] query={q!r} 返回 {len(results)} 条:")
        for i, r in enumerate(results, 1):
            logger.info(
                f"  [{i}] page_type={r.get('page_type', '-'):10s} title={r.get('title', '-')[:50]:50s} "
                f"filepath={r.get('filepath', '-')[:60]} snippet_len={len(r.get('snippet', ''))}"
            )
    else:
        logger.warning(f"[WIKI_EMPTY] query={q!r} 无匹配结果 — 引用面板不会显示")

    logger.info(
        f"[WIKI_DONE] query={q!r} total={len(results)} 总耗时={total_ms:.1f}ms "
        f"(search={search_ms:.1f}ms + content={content_ms:.1f}ms)"
    )

    return {"query": q, "total": len(results), "results": results}
