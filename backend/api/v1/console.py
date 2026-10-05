# backend/api/v1/console.py
# 运营台接口（P6）：供客服工作台首页与主管看板使用
#
#   GET  /api/v1/console/overview                 总览：待审批 / 未解决 / 工单统计 / 缓存指标（登录可见）
#   GET  /api/v1/console/unresolved               未解决问题池（转人工记录，主管）
#   POST /api/v1/console/unresolved/{id}/resolve  标记已解决（主管）

import uuid as uuid_lib

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query

from backend.api.v1.aftersale import _require_supervisor, list_pending_reviews
from backend.config import get_settings
from backend.core.cache import get_metrics
from backend.core.logger import get_logger
from backend.dependencies import get_current_user

router = APIRouter()
logger = get_logger(__name__)


def _dsn() -> str:
    s = get_settings()
    return (f"postgresql://{s.db_user}:{s.db_password}"
            f"@{s.db_host}:{s.db_port}/{s.db_name}")


def _row_view(r) -> dict:
    d = dict(r)
    for k, v in d.items():
        if isinstance(v, uuid_lib.UUID):
            d[k] = str(v)
        elif hasattr(v, "isoformat"):
            d[k] = v.isoformat()
    return d


@router.get("/overview")
async def console_overview(current_user: dict = Depends(get_current_user)):
    """运营总览（登录即可看）：待审批 / 未解决问题 / 售后工单统计 / Redis 监控指标。"""
    conn = await asyncpg.connect(_dsn())
    try:
        unresolved_pending = await conn.fetchval(
            "SELECT COUNT(*) FROM unresolved_questions "
            "WHERE COALESCE(status, 'pending') <> 'resolved'")
        ticket_rows = await conn.fetch(
            "SELECT status, COUNT(*) AS n FROM after_sales_tickets "
            "GROUP BY status ORDER BY status")
    finally:
        await conn.close()

    by_status = {r["status"]: int(r["n"]) for r in ticket_rows}
    return {
        "pending_reviews": len(list_pending_reviews()),
        "unresolved_questions": int(unresolved_pending or 0),
        "tickets_total": sum(by_status.values()),
        "tickets_by_status": by_status,
        "metrics": await get_metrics(),
    }


@router.get("/unresolved")
async def list_unresolved(current_user: dict = Depends(get_current_user),
                          limit: int = Query(50, ge=1, le=200)):
    """未解决问题池（主管）：转人工记录列表（含交接摘要与状态）。"""
    _require_supervisor(current_user)
    conn = await asyncpg.connect(_dsn())
    try:
        rows = await conn.fetch(
            "SELECT id, session_id, question, summary, "
            "COALESCE(status, 'pending') AS status, created_at "
            "FROM unresolved_questions ORDER BY created_at DESC LIMIT $1",
            limit,
        )
    finally:
        await conn.close()
    return {"count": len(rows), "items": [_row_view(r) for r in rows]}


@router.post("/unresolved/{item_id}/resolve")
async def resolve_unresolved(item_id: int, current_user: dict = Depends(get_current_user)):
    """标记未解决问题已解决（主管）。"""
    _require_supervisor(current_user)
    conn = await asyncpg.connect(_dsn())
    try:
        row = await conn.fetchrow(
            "UPDATE unresolved_questions SET status = 'resolved' "
            "WHERE id = $1 RETURNING id, status",
            item_id,
        )
    finally:
        await conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="记录不存在")
    return {"id": row["id"], "status": row["status"]}