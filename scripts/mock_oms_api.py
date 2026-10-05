# scripts/mock_oms_api.py
# 演示用"外部订单系统"HTTP API（Mock OMS）——读取同一份 PostgreSQL 演示数据
#
# 用途：把 MCP 工具服务的数据源切到 api（ORDER_BACKEND=api）时，
#       工具会通过 HTTP 调本服务获取订单/物流/商品数据，演示"同一套工具、两种数据源"。
#
# 运行：python scripts/mock_oms_api.py      → http://localhost:8200
# 接口契约（与 backend/mcp/cs_order_server.py 的适配层对应）：
#   GET /orders/{order_id}              → 订单主体（含 customer 嵌套）
#   GET /orders/{order_id}/items        → 商品明细列表
#   GET /orders/{order_id}/logistics    → 物流轨迹列表
#   GET /customers/{phone}/orders?limit → 客户订单列表
#   GET /products/{sku}                 → 商品信息
#   GET /health                         → 健康检查

import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import asyncpg
from fastapi import FastAPI, HTTPException, Query

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.config import get_settings  # noqa: E402

app = FastAPI(title="Mock OMS API（演示用外部订单系统）", version="1.0.0")

_s = get_settings()
DSN = (
    f"postgresql://{_s.db_user}:{_s.db_password}"
    f"@{_s.db_host}:{_s.db_port}/{_s.db_name}"
)


def _jsonable(v):
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, datetime):
        return v.isoformat()
    return v


def _clean(d: dict) -> dict:
    return {k: _jsonable(v) for k, v in d.items()}


async def _conn() -> asyncpg.Connection:
    return await asyncpg.connect(DSN)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/orders/{order_id}")
async def get_order(order_id: str):
    conn = await _conn()
    try:
        row = await conn.fetchrow(
            """
            SELECT o.*, c.name AS customer_name, c.phone AS customer_phone, c.tier AS customer_tier
            FROM orders o JOIN customers c ON c.id = o.customer_id
            WHERE o.id = $1
            """,
            order_id.upper(),
        )
        if not row:
            raise HTTPException(404, f"order {order_id} not found")
        d = _clean(dict(row))
        d["order_id"] = d.pop("id")
        d["customer"] = {
            "name": d.pop("customer_name"),
            "phone": d.pop("customer_phone"),
            "tier": d.pop("customer_tier"),
        }
        return d
    finally:
        await conn.close()


@app.get("/orders/{order_id}/items")
async def get_items(order_id: str):
    conn = await _conn()
    try:
        rows = await conn.fetch(
            """
            SELECT i.sku, p.name, i.quantity, i.unit_price, i.opened,
                   p.category, p.warranty_months, p.returnable, p.unopened_required
            FROM order_items i JOIN products p ON p.sku = i.sku
            WHERE i.order_id = $1 ORDER BY i.id
            """,
            order_id.upper(),
        )
        return [_clean(dict(r)) for r in rows]
    finally:
        await conn.close()


@app.get("/orders/{order_id}/logistics")
async def get_logistics(order_id: str):
    conn = await _conn()
    try:
        exists = await conn.fetchval("SELECT 1 FROM orders WHERE id = $1", order_id.upper())
        if not exists:
            raise HTTPException(404, f"order {order_id} not found")
        rows = await conn.fetch(
            "SELECT track_time, location, status, description FROM logistics_tracks "
            "WHERE order_id = $1 ORDER BY track_time",
            order_id.upper(),
        )
        return [_clean(dict(r)) for r in rows]
    finally:
        await conn.close()


@app.get("/customers/{phone}/orders")
async def customer_orders(phone: str, limit: int = Query(5, ge=1, le=20)):
    conn = await _conn()
    try:
        rows = await conn.fetch(
            """
            SELECT o.id AS order_id, o.status, o.total_amount, o.created_at, o.delivered_at
            FROM orders o JOIN customers c ON c.id = o.customer_id
            WHERE c.phone = $1
            ORDER BY o.created_at DESC LIMIT $2
            """,
            phone, limit,
        )
        return [_clean(dict(r)) for r in rows]
    finally:
        await conn.close()


@app.get("/products/{sku}")
async def get_product(sku: str):
    conn = await _conn()
    try:
        row = await conn.fetchrow("SELECT * FROM products WHERE sku = $1", sku.upper())
        if not row:
            raise HTTPException(404, f"product {sku} not found")
        return _clean(dict(row))
    finally:
        await conn.close()


if __name__ == "__main__":
    import uvicorn
    port = 8200
    print(f"Mock OMS API → http://localhost:{port}  （文档见 /docs）")
    uvicorn.run(app, host="0.0.0.0", port=port)
