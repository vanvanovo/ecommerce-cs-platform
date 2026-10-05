# services/rag_agent/retriever.py
# RAG Agent 的检索适配层：一份接口，三种后端（可插拔）
#
#   mcp    （默认）：调用平台现有 MCP 知识库工具 search_knowledge_base（零额外模型加载）
#   inproc        ：本地进程内加载 BGE-M3 + Reranker（独立但吃内存）
#   http   （B 预留）：调用外部 RAG 服务（一期 ecommerce_rag 包成 HTTP 后接这里）
#
# 返回统一结构：
#   {"docs": [{"content", "source_name", "score"}],
#    "confidence": float, "is_high_confidence": bool, "mode": str}

import asyncio

import httpx

from backend.config import get_settings
from backend.core.logger import get_logger
from backend.mcp.client import call_mcp_tool

logger = get_logger(__name__)

CONFIDENCE_THRESHOLD = 0.75


async def _via_mcp(query: str, tenant_id: str, top_k: int) -> dict:
    """走平台 MCP 知识库工具（复用已有 BGE-M3 + Reranker，不重复加载模型）。

    P6：政策类检索结果进 Redis 缓存（TTL 30 分钟）——命中直接返回，省掉 ~8s CPU 检索。
    """
    import hashlib

    from backend.core.cache import TTL_POLICY, cache_get, cache_set, incr_metric

    cache_key = "cache:rag:" + hashlib.md5(
        f"{tenant_id}:{top_k}:{query.strip()}".encode("utf-8")
    ).hexdigest()
    cached = await cache_get(cache_key)
    if cached is not None:
        await incr_metric("rag_cache_hit")
        return {**cached, "cached": True}
    await incr_metric("rag_cache_miss")

    s = get_settings()
    res = await call_mcp_tool(
        s.kb_mcp_server_url, "search_knowledge_base",
        {"query": query, "tenant_id": tenant_id, "top_k": top_k},
        timeout=15.0,
    )
    docs = res if isinstance(res, list) else [res]
    docs = [d for d in docs if isinstance(d, dict)]
    confidence = float(docs[0].get("confidence", 0.0)) if docs else 0.0
    result = {
        "docs": [
            {"content": d.get("content", ""), "source_name": d.get("source_name", ""),
             "score": float(d.get("score") or 0.0)}
            for d in docs
        ],
        "confidence": confidence,
        "is_high_confidence": confidence >= CONFIDENCE_THRESHOLD,
        "mode": "mcp",
    }
    await cache_set(cache_key, result, ttl=TTL_POLICY)
    return result


async def _via_inproc(query: str, tenant_id: str, top_k: int) -> dict:
    """进程内加载模型检索（独立服务，但占内存；本机内存紧张时不建议）。"""
    from backend.core.reranker import retrieve

    ranked, confidence = await asyncio.to_thread(
        lambda: retrieve(query, tenant_id, None, rerank_top_k=top_k)
    )
    return {
        "docs": [
            {"content": d.content, "source_name": d.metadata.get("source_name", ""),
             "score": float(d.score)}
            for d in ranked
        ],
        "confidence": float(confidence),
        "is_high_confidence": float(confidence) >= CONFIDENCE_THRESHOLD,
        "mode": "inproc",
    }


async def _via_http(query: str, tenant_id: str, top_k: int) -> dict:
    """B 后补预留：调用外部 RAG 服务（一期 ecommerce_rag 包成 HTTP 后接这里）。

    外部服务契约（预留）：
        GET {RAG_EXTERNAL_URL}/search?query=..&top_k=..&tenant_id=..
        → {"docs": [{"content", "source_name", "score"}], "confidence": float}
    """
    s = get_settings()
    if not s.rag_external_url:
        raise RuntimeError("RAG_EXTERNAL_URL 未配置（B 路线：一期 RAG 服务地址）")
    async with httpx.AsyncClient(trust_env=False, timeout=s.a2a_timeout_seconds + 5) as client:
        resp = await client.get(
            f"{s.rag_external_url.rstrip('/')}/search",
            params={"query": query, "top_k": top_k, "tenant_id": tenant_id},
        )
        resp.raise_for_status()
        data = resp.json()
    confidence = float(data.get("confidence", 0.0))
    return {
        "docs": data.get("docs", []),
        "confidence": confidence,
        "is_high_confidence": confidence >= CONFIDENCE_THRESHOLD,
        "mode": "http",
    }


async def retrieve_docs(query: str, tenant_id: str = "tenant_default", top_k: int = 3) -> dict:
    """检索适配入口：按 RAG_AGENT_RETRIEVAL_MODE 选择后端。"""
    mode = (get_settings().rag_agent_retrieval_mode or "mcp").strip().lower()
    logger.info("rag_agent.retrieve", mode=mode, query=query[:50])
    if mode == "mcp":
        return await _via_mcp(query, tenant_id, top_k)
    if mode == "inproc":
        return await _via_inproc(query, tenant_id, top_k)
    if mode == "http":
        return await _via_http(query, tenant_id, top_k)
    raise ValueError(f"未知 RAG_AGENT_RETRIEVAL_MODE: {mode}（可选 mcp / inproc / http）")
