# backend/mcp/cs_order_server.py
# 电商客服 MCP 工具服务（P2）
#
# 设计原则：
#   1) 参数化工具，不暴露 SQL 直通（注入面从根上消除——同办公助手 SQL 白名单思路）
#   2) 统一 JSON 返回：{"status": "success|not_found|invalid|rejected|duplicate", "data"/"message": ...}
#   3) 写操作：幂等键（idempotency_key）+ 审计日志（audit_logs）
#   4) 规则与《售后政策》对齐：7 天无理由 / 未拆封 / 金额 ≥ 500 需主管审批
#   5) 数据源适配层（ORDER_BACKEND=db|api）：
#      - db ：直连本地 PostgreSQL（默认，演示数据）
#      - api：调用外部订单系统 HTTP API（工具契约完全不变——"统一入口 + 可插拔后端"）
#      API 契约（由 mock_oms_api.py 演示实现）：
#        GET /orders/{order_id}              → 订单主体（含 customer 嵌套）
#        GET /orders/{order_id}/items        → 商品明细列表
#        GET /orders/{order_id}/logistics    → 物流轨迹列表
#        GET /customers/{phone}/orders?limit → 客户订单列表
#        GET /products/{sku}                 → 商品信息
#
# 工具清单：
#   只读：get_order / list_orders / track_logistics / check_return_eligibility / query_inventory
#   写：  create_return_ticket / create_compensation
#
# 独立运行：python -m backend.mcp.cs_order_server  → http://localhost:8101/mcp
# 平台挂载：backend/main.py 挂到 /mcp/cs

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import asyncpg
import httpx
from mcp.server.fastmcp import FastMCP

from backend.config import get_settings

mcp = FastMCP(
    name="CSP-OrderTools",
    stateless_http=True,
    json_response=True,
)

RETURN_WINDOW_DAYS = 7                    # 七天无理由（自签收起算）
REVIEW_AMOUNT_THRESHOLD = Decimal("500")  # 金额 ≥ 500 需主管审批


class OrderBackendError(Exception):
    """外部订单系统接口异常。"""


# ── 基础设施 ──────────────────────────────────────────────────

def _dsn() -> str:
    s = get_settings()
    return (
        f"postgresql://{s.db_user}:{s.db_password}"
        f"@{s.db_host}:{s.db_port}/{s.db_name}"
    )


async def _connect() -> asyncpg.Connection:
    return await asyncpg.connect(_dsn())


def _use_api() -> bool:
    return (get_settings().order_backend or "db").strip().lower() == "api"


def _parse_dt(v) -> datetime | None:
    if isinstance(v, datetime):
        return v
    if isinstance(v, str) and v:
        try:
            return datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _jsonable(v):
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, uuid.UUID):
        return str(v)
    if v is None or isinstance(v, (str, int, float, bool)):
        return v                     # 基本类型原样放过（注意：bool 是 int 子类，须在兜底前）
    return str(v)                    # 兜底：真正未知的类型转字符串，避免 json 序列化失败


def _ok(data) -> str:
    return json.dumps({"status": "success", "data": data}, ensure_ascii=False, default=_jsonable)


def _msg(status: str, message: str, **extra) -> str:
    return json.dumps({"status": status, "message": message, **extra}, ensure_ascii=False, default=_jsonable)


async def _audit(conn, action: str, target: str, payload: dict, actor: str = "cs_mcp") -> None:
    await conn.execute(
        "INSERT INTO audit_logs (actor, action, target, payload) VALUES ($1,$2,$3,$4)",
        actor, action, target, json.dumps(payload, ensure_ascii=False, default=str),
    )


# ── 数据源适配层（db | api）───────────────────────────────────
# 所有工具只依赖下面这组"规范结构"，不感知数据来自库里还是 HTTP 接口。

async def _api_get(path: str) -> Any:
    """调用外部订单系统 GET 接口；404 返回 None；其余异常抛 OrderBackendError。"""
    s = get_settings()
    url = f"{s.order_api_base.rstrip('/')}{path}"
    try:
        async with httpx.AsyncClient(trust_env=False, timeout=s.order_api_timeout_seconds) as client:
            resp = await client.get(url)
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPError as e:
        raise OrderBackendError(f"订单系统接口调用失败：{url} | {e}") from e


def _canonicalize_order(d: dict) -> dict:
    """任意来源订单 → 规范结构。"""
    delivered = _parse_dt(d.get("delivered_at"))
    now = datetime.now(timezone.utc)
    days = round((now - delivered).total_seconds() / 86400, 1) if delivered else None
    customer = d.get("customer")
    if not isinstance(customer, dict):
        customer = {
            "name": d.get("customer_name"),
            "phone": d.get("customer_phone"),
            "tier": d.get("customer_tier"),
        }
    return {
        "order_id": d.get("order_id") or d.get("id"),
        "customer_id": d.get("customer_id"),
        "status": d.get("status"),
        "total_amount": float(d.get("total_amount") or 0),
        "customer": customer,
        "created_at": _parse_dt(d.get("created_at")),
        "paid_at": _parse_dt(d.get("paid_at")),
        "shipped_at": _parse_dt(d.get("shipped_at")),
        "delivered_at": delivered,
        "days_since_delivered": days,
    }


def _canonicalize_item(d: dict) -> dict:
    return {
        "sku": d.get("sku"),
        "name": d.get("name"),
        "quantity": int(d.get("quantity") or 1),
        "unit_price": float(d.get("unit_price") or 0),
        "opened": bool(d.get("opened")),
        "category": d.get("category"),
        "warranty_months": int(d.get("warranty_months") or 0),
        "returnable": bool(d.get("returnable", True)),
        "unopened_required": bool(d.get("unopened_required", False)),
    }


def _canonicalize_track(d: dict) -> dict:
    return {
        "track_time": _jsonable(_parse_dt(d.get("track_time"))),
        "location": d.get("location"),
        "status": d.get("status"),
        "description": d.get("description"),
    }


async def _src_order(order_id: str) -> dict | None:
    if _use_api():
        data = await _api_get(f"/orders/{order_id}")
        return _canonicalize_order(data) if data else None
    conn = await _connect()
    try:
        row = await conn.fetchrow(
            """
            SELECT o.*, c.name AS customer_name, c.phone AS customer_phone, c.tier AS customer_tier
            FROM orders o JOIN customers c ON c.id = o.customer_id
            WHERE o.id = $1
            """,
            order_id,
        )
        return _canonicalize_order(dict(row)) if row else None
    finally:
        await conn.close()


async def _src_items(order_id: str) -> list[dict]:
    if _use_api():
        data = await _api_get(f"/orders/{order_id}/items")
        return [_canonicalize_item(i) for i in (data or [])]
    conn = await _connect()
    try:
        rows = await conn.fetch(
            """
            SELECT i.sku, p.name, i.quantity, i.unit_price, i.opened,
                   p.category, p.warranty_months, p.returnable, p.unopened_required
            FROM order_items i JOIN products p ON p.sku = i.sku
            WHERE i.order_id = $1 ORDER BY i.id
            """,
            order_id,
        )
        return [_canonicalize_item(dict(r)) for r in rows]
    finally:
        await conn.close()


async def _src_tracks(order_id: str) -> list[dict]:
    if _use_api():
        data = await _api_get(f"/orders/{order_id}/logistics")
        return [_canonicalize_track(t) for t in (data or [])]
    conn = await _connect()
    try:
        rows = await conn.fetch(
            "SELECT track_time, location, status, description FROM logistics_tracks "
            "WHERE order_id = $1 ORDER BY track_time",
            order_id,
        )
        return [_canonicalize_track(dict(r)) for r in rows]
    finally:
        await conn.close()


async def _src_customer_orders(phone: str, limit: int) -> list[dict]:
    if _use_api():
        data = await _api_get(f"/customers/{phone}/orders?limit={limit}")
        rows = data or []
    else:
        conn = await _connect()
        try:
            recs = await conn.fetch(
                """
                SELECT o.id, o.status, o.total_amount, o.created_at, o.delivered_at
                FROM orders o JOIN customers c ON c.id = o.customer_id
                WHERE c.phone = $1
                ORDER BY o.created_at DESC LIMIT $2
                """,
                phone, limit,
            )
            rows = [dict(r) for r in recs]
        finally:
            await conn.close()
    return [
        {
            "order_id": r.get("order_id") or r.get("id"),
            "status": r.get("status"),
            "total_amount": float(r.get("total_amount") or 0),
            "created_at": _parse_dt(r.get("created_at")),
            "delivered_at": _parse_dt(r.get("delivered_at")),
        }
        for r in rows
    ]


async def _src_product(sku: str) -> dict | None:
    if _use_api():
        data = await _api_get(f"/products/{sku}")
        if not data:
            return None
        return {k: _jsonable(v) for k, v in data.items()}
    conn = await _connect()
    try:
        row = await conn.fetchrow("SELECT * FROM products WHERE sku = $1", sku)
        return {k: _jsonable(v) for k, v in dict(row).items()} if row else None
    finally:
        await conn.close()


# ── 规则引擎（与《售后政策》一致）────────────────────────────

def _evaluate_return(order: dict, items: list[dict], sku: str | None = None) -> dict:
    days = order["days_since_delivered"]
    within = days is not None and days <= RETURN_WINDOW_DAYS

    target = [i for i in items if (sku is None or i["sku"] == sku)]
    amount = Decimal(str(order["total_amount"]))
    over_threshold = amount >= REVIEW_AMOUNT_THRESHOLD

    opened = any(i["opened"] for i in target)
    unopened_required = any(i["unopened_required"] for i in target)
    returnable = all(i["returnable"] for i in target) if target else False

    item_views = []
    for i in target:
        wm = i["warranty_months"] or 0
        item_views.append({
            "sku": i["sku"], "name": i["name"], "opened": i["opened"],
            "category": i["category"], "unit_price": i["unit_price"],
            "returnable": i["returnable"], "unopened_required": i["unopened_required"],
            "warranty_months": wm,
            "in_warranty": bool(days is not None and wm > 0 and days <= wm * 30),
        })

    reasons: list[str] = []
    eligible, next_step = True, "auto_approve"

    if order["status"] != "delivered":
        eligible, next_step = False, "not_delivered"
        reasons.append(f"订单状态为 {order['status']}（未签收），可走取消/拒收流程")
    elif not within:
        eligible, next_step = False, "reject"
        reasons.append(f"已签收 {days} 天，超过 {RETURN_WINDOW_DAYS} 天无理由窗口；如为质量问题可走保修")
    elif opened and unopened_required:
        eligible, next_step = False, "quality_path"
        reasons.append("个人卫生类商品（如耳机/牙刷）拆封后不支持七天无理由；如为质量问题转保修流程")
    elif not returnable:
        eligible, next_step = False, "reject"
        reasons.append("该商品类目不支持无理由退货")
    elif opened or over_threshold:
        next_step = "submit_for_review"
        if opened:
            reasons.append("商品已拆封，需人工确认商品状态")
        if over_threshold:
            reasons.append(f"金额 {amount} ≥ {REVIEW_AMOUNT_THRESHOLD}，需主管审批")
    else:
        reasons.append("满足 7 天无理由 + 未拆封 + 金额 < 500，可自动通过")

    return {
        "order_id": order["order_id"],
        "order_status": order["status"],
        "days_since_delivered": days,
        "within_return_window": within,
        "amount": float(amount),
        "amount_over_threshold": over_threshold,
        "items": item_views,
        "eligible": eligible,
        "next_step": next_step,     # auto_approve / submit_for_review / quality_path / reject / not_delivered
        "reasons": reasons,
    }


def _check_order_id(order_id: str) -> str | None:
    oid = (order_id or "").strip().upper()
    return oid if re.fullmatch(r"A\d{4}", oid) else None


# ── 只读工具 ─────────────────────────────────────────────────

@mcp.tool()
async def get_order(order_id: str) -> str:
    """查询订单详情：状态、金额、客户信息、商品明细（含拆封标记）。

    Args:
        order_id: 订单号，形如 "A1024"
    """
    oid = _check_order_id(order_id)
    if not oid:
        return _msg("invalid", f"订单号格式不正确：{order_id}（应为 A + 4 位数字，如 A1024）")
    order = await _src_order(oid)
    if not order:
        return _msg("not_found", f"未找到订单 {oid}")
    items = await _src_items(oid)
    return _ok({**order, "items": items})


@mcp.tool()
async def list_orders(phone: str, limit: int = 5) -> str:
    """按手机号查询客户的最近订单列表。

    Args:
        phone: 11 位手机号，如 "13800000001"
        limit: 返回条数（1~20，默认 5）
    """
    phone = re.sub(r"\D", "", phone or "")
    if not re.fullmatch(r"1\d{10}", phone):
        return _msg("invalid", f"手机号格式不正确：{phone}")
    limit = max(1, min(int(limit), 20))
    orders = await _src_customer_orders(phone, limit)
    return _ok({"phone": phone, "count": len(orders), "orders": orders})


@mcp.tool()
async def track_logistics(order_id: str) -> str:
    """查询订单物流轨迹（最新节点 + 全部轨迹）。

    Args:
        order_id: 订单号，形如 "A1024"
    """
    oid = _check_order_id(order_id)
    if not oid:
        return _msg("invalid", f"订单号格式不正确：{order_id}")

    # P6：物流轨迹 5 分钟缓存（命中直接返回并标注 cached）
    from backend.core.cache import TTL_LOGISTICS, cache_get, cache_set, incr_metric

    cache_key = f"cache:logi:{oid}"
    cached = await cache_get(cache_key)
    if cached is not None:
        await incr_metric("logistics_cache_hit")
        return json.dumps({"status": "success", "data": {**cached, "cached": True}},
                          ensure_ascii=False, default=_jsonable)
    await incr_metric("logistics_cache_miss")

    order = await _src_order(oid)
    if not order:
        return _msg("not_found", f"未找到订单 {oid}")
    tracks = await _src_tracks(oid)
    payload = {
        "order_id": oid,
        "order_status": order["status"],
        "latest": tracks[-1] if tracks else None,
        "tracks": tracks,
        "note": "" if tracks else "暂无物流轨迹（订单可能尚未发货）",
    }
    await cache_set(cache_key, payload, ttl=TTL_LOGISTICS)
    return _ok(payload)


@mcp.tool()
async def check_return_eligibility(order_id: str, sku: str | None = None, reason: str | None = None) -> str:
    """审核订单的退换货资格（7 天窗口 / 拆封规则 / 金额阈值 / 保修状态），返回是否可自动通过或需人工。

    Args:
        order_id: 订单号，如 "A1024"
        sku:      可选，只审核某个商品（默认整单）
        reason:   可选，用户退货原因（仅用于日志说明）
    """
    oid = _check_order_id(order_id)
    if not oid:
        return _msg("invalid", f"订单号格式不正确：{order_id}")
    order = await _src_order(oid)
    if not order:
        return _msg("not_found", f"未找到订单 {oid}")
    items = await _src_items(oid)
    if sku and not any(i["sku"] == sku for i in items):
        return _msg("invalid", f"订单 {oid} 中不包含商品 {sku}")
    return _ok(_evaluate_return(order, items, sku))


@mcp.tool()
async def query_inventory(sku: str) -> str:
    """查询商品库存与售后属性（价格 / 库存 / 保修月数 / 是否支持无理由 / 是否要求未拆封）。

    Args:
        sku: 商品编号，如 "SKU-1001"
    """
    sku = (sku or "").strip().upper()
    if not re.fullmatch(r"SKU-\d{4}", sku):
        return _msg("invalid", f"SKU 格式不正确：{sku}（应为 SKU-XXXX）")
    product = await _src_product(sku)
    if not product:
        return _msg("not_found", f"未找到商品 {sku}")
    return _ok(product)


# ── 写操作（幂等 + 审计）─────────────────────────────────────
# 说明：写操作统一落"工单库"（demo 为本地 PostgreSQL）；
#       生产对接退货系统时，把 INSERT 换成调用退货系统 API 即可（同上适配层思路）。

async def _next_ticket_id(conn) -> str:
    seq = await conn.fetchval(
        r"SELECT COALESCE(MAX(CAST(SUBSTRING(id FROM 'RT-\d{4}-(\d+)') AS INT)), 1000) + 1 "
        r"FROM after_sales_tickets"
    )
    return f"RT-2026-{seq}"


async def _find_by_idempotency(conn, key: str):
    return await conn.fetchrow(
        "SELECT id, order_id, type, status, amount, created_at FROM after_sales_tickets "
        "WHERE idempotency_key = $1",
        key,
    )


def _ticket_view(row) -> dict:
    return {k: _jsonable(v) for k, v in dict(row).items()}


@mcp.tool()
async def create_return_ticket(
    order_id: str,
    ticket_type: str = "return",
    reason: str = "",
    sku: str | None = None,
    idempotency_key: str | None = None,
) -> str:
    """创建售后工单（退货/退款/换货）。规则自动审核：满足条件自动通过；金额≥500 或已拆封转主管审批；不满足条件拒绝创建。

    幂等：同一 idempotency_key 重复调用会返回第一次创建的工单（status=duplicate）。
    P6：同一订单的写操作经 Redis 分布式锁串行化，防并发重复建单。

    Args:
        order_id:        订单号，如 "A1024"
        ticket_type:     refund / return / exchange（默认 return）
        reason:          用户申请原因
        sku:             可选，指定商品
        idempotency_key: 可选，幂等键（建议格式：{order_id}-{type}-{hash}）
    """
    oid = _check_order_id(order_id)
    if not oid:
        return _msg("invalid", f"订单号格式不正确：{order_id}")
    if ticket_type not in ("refund", "return", "exchange"):
        return _msg("invalid", "ticket_type 仅支持 refund / return / exchange")

    from backend.core.cache import incr_metric, redis_lock

    try:
        async with redis_lock(f"ticket:{oid}", ttl=10, wait=2.0):
            return await _create_return_ticket_locked(oid, ticket_type, reason, sku, idempotency_key)
    except TimeoutError:
        await incr_metric("write_lock_busy")
        return _msg("busy", f"订单 {oid} 正在处理另一笔售后请求，请稍后重试")


async def _create_return_ticket_locked(
    oid: str,
    ticket_type: str,
    reason: str,
    sku: str | None,
    idempotency_key: str | None,
) -> str:
    conn = await _connect()
    try:
        if idempotency_key:
            existing = await _find_by_idempotency(conn, idempotency_key)
            if existing:
                return _msg("duplicate", "该幂等键已创建过工单，返回原有工单", data=_ticket_view(existing))

        order = await _src_order(oid)
        if not order:
            return _msg("not_found", f"未找到订单 {oid}")
        items = await _src_items(oid)
        if sku and not any(i["sku"] == sku for i in items):
            return _msg("invalid", f"订单 {oid} 中不包含商品 {sku}")

        check = _evaluate_return(order, items, sku)
        if check["next_step"] in ("reject", "not_delivered"):
            return _msg("rejected", "；".join(check["reasons"]), data=check)

        status = "auto_approved" if check["next_step"] == "auto_approve" else "pending_review"
        amount = Decimal(str(order["total_amount"]))
        if sku:
            for i in items:
                if i["sku"] == sku:
                    amount = Decimal(str(i["unit_price"])) * int(i["quantity"])

        try:
            async with conn.transaction():
                ticket_id = await _next_ticket_id(conn)
                await conn.execute(
                    """
                    INSERT INTO after_sales_tickets
                        (id, order_id, customer_id, type, reason, status, auto_check, amount, created_at, idempotency_key)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8, now(), $9)
                    """,
                    ticket_id, oid, order["customer_id"], ticket_type, (reason or "")[:200],
                    status, json.dumps(check, ensure_ascii=False, default=str), amount, idempotency_key,
                )
                await _audit(conn, "create_return_ticket", ticket_id, {
                    "order_id": oid, "ticket_type": ticket_type, "status": status,
                    "amount": float(amount), "sku": sku,
                    "idempotency_key": idempotency_key, "reason": (reason or "")[:200],
                    "source": "api" if _use_api() else "db",
                })
        except asyncpg.UniqueViolationError:
            existing = await _find_by_idempotency(conn, idempotency_key)
            if existing:
                return _msg("duplicate", "并发重复请求，返回已存在工单", data=_ticket_view(existing))
            raise

        return _ok({
            "ticket_id": ticket_id,
            "order_id": oid,
            "type": ticket_type,
            "status": status,
            "amount": float(amount),
            "auto_check": check,
        })
    finally:
        await conn.close()


@mcp.tool()
async def create_compensation(
    order_id: str,
    amount: float,
    reason: str,
    idempotency_key: str | None = None,
) -> str:
    """创建补偿工单（如超时未发货 / 物流延迟补偿）。金额 ≥ 500 转主管审批；幂等键规则同上。

    P6：同一订单的写操作经 Redis 分布式锁串行化。

    Args:
        order_id:        订单号，如 "A1049"
        amount:          补偿金额（元），需 > 0
        reason:          补偿原因
        idempotency_key: 可选，幂等键
    """
    oid = _check_order_id(order_id)
    if not oid:
        return _msg("invalid", f"订单号格式不正确：{order_id}")
    try:
        amount_dec = Decimal(str(amount))
    except Exception:
        return _msg("invalid", f"补偿金额不合法：{amount}")
    if amount_dec <= 0 or amount_dec > 200:
        return _msg("invalid", "补偿金额需在 (0, 200] 元之间")

    from backend.core.cache import incr_metric, redis_lock

    try:
        async with redis_lock(f"ticket:{oid}", ttl=10, wait=2.0):
            return await _create_compensation_locked(oid, amount_dec, reason, idempotency_key)
    except TimeoutError:
        await incr_metric("write_lock_busy")
        return _msg("busy", f"订单 {oid} 正在处理另一笔售后请求，请稍后重试")


async def _create_compensation_locked(
    oid: str,
    amount_dec: Decimal,
    reason: str,
    idempotency_key: str | None,
) -> str:
    conn = await _connect()
    try:
        if idempotency_key:
            existing = await _find_by_idempotency(conn, idempotency_key)
            if existing:
                return _msg("duplicate", "该幂等键已创建过工单，返回原有工单", data=_ticket_view(existing))

        order = await _src_order(oid)
        if not order:
            return _msg("not_found", f"未找到订单 {oid}")

        status = "pending_review" if amount_dec >= REVIEW_AMOUNT_THRESHOLD else "auto_approved"
        check = {
            "rule": "超时未发货/物流延迟补偿",
            "amount": float(amount_dec),
            "over_threshold": amount_dec >= REVIEW_AMOUNT_THRESHOLD,
            "order_status": order["status"],
        }
        async with conn.transaction():
            ticket_id = await _next_ticket_id(conn)
            await conn.execute(
                """
                INSERT INTO after_sales_tickets
                    (id, order_id, customer_id, type, reason, status, auto_check, amount, created_at, idempotency_key)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8, now(), $9)
                """,
                ticket_id, oid, order["customer_id"], "compensation", (reason or "")[:200],
                status, json.dumps(check, ensure_ascii=False), amount_dec, idempotency_key,
            )
            await _audit(conn, "create_compensation", ticket_id, {
                "order_id": oid, "amount": float(amount_dec), "status": status,
                "idempotency_key": idempotency_key, "reason": (reason or "")[:200],
                "source": "api" if _use_api() else "db",
            })

        return _ok({
            "ticket_id": ticket_id,
            "order_id": oid,
            "type": "compensation",
            "status": status,
            "amount": float(amount_dec),
        })
    finally:
        await conn.close()


@mcp.tool()
async def review_ticket(
    ticket_id: str,
    decision: str,
    reviewer: str = "",
    comment: str = "",
) -> str:
    """主管审批售后工单：decision ∈ approve / modify / reject。

    效果：更新工单状态（approved / rejected）+ 写 refund_approvals 审批记录 + 审计日志。
    已终态的工单重复调用会返回当前状态（不重复写入）。
    P6：审批写操作经 Redis 分布式锁串行化，防并发重复审批。

    Args:
        ticket_id: 工单号，如 "RT-2026-1003"
        decision:  approve（通过）/ modify（修改后通过）/ reject（驳回）
        reviewer:  审批人（主管 user_id）
        comment:   审批意见
    """
    ticket_id = (ticket_id or "").strip().upper()
    if not re.fullmatch(r"RT-\d{4}-\d+", ticket_id):
        return _msg("invalid", f"工单号格式不正确：{ticket_id}")
    if decision not in ("approve", "modify", "reject"):
        return _msg("invalid", "decision 仅支持 approve / modify / reject")

    from backend.core.cache import incr_metric, redis_lock

    try:
        async with redis_lock(f"review:{ticket_id}", ttl=10, wait=2.0):
            return await _review_ticket_locked(ticket_id, decision, reviewer, comment)
    except TimeoutError:
        await incr_metric("write_lock_busy")
        return _msg("busy", f"工单 {ticket_id} 正在被审批，请稍后重试")


async def _review_ticket_locked(ticket_id: str, decision: str, reviewer: str, comment: str) -> str:
    conn = await _connect()
    try:
        row = await conn.fetchrow(
            "SELECT id, order_id, status, amount FROM after_sales_tickets WHERE id = $1",
            ticket_id,
        )
        if not row:
            return _msg("not_found", f"未找到工单 {ticket_id}")
        if row["status"] in ("approved", "rejected"):
            return _msg("duplicate", f"工单已是终态（{row['status']}），无需重复审批",
                        data={"ticket_id": ticket_id, "status": row["status"]})

        new_status = "approved" if decision in ("approve", "modify") else "rejected"
        async with conn.transaction():
            await conn.execute(
                "UPDATE after_sales_tickets SET status = $1 WHERE id = $2",
                new_status, ticket_id,
            )
            await conn.execute(
                "INSERT INTO refund_approvals (ticket_id, decision, reviewer, comment) "
                "VALUES ($1,$2,$3,$4)",
                ticket_id, decision, reviewer or "supervisor", (comment or "")[:500],
            )
            await _audit(conn, "review_ticket", ticket_id, {
                "decision": decision, "status": new_status,
                "reviewer": reviewer, "comment": (comment or "")[:200],
                "source": "api" if _use_api() else "db",
            })

        return _ok({"ticket_id": ticket_id, "status": new_status, "decision": decision})
    finally:
        await conn.close()


# ── 独立运行入口（可选）───────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    port = 8101
    print(f"CSP Order MCP Server → http://localhost:{port}/mcp")
    uvicorn.run(mcp.streamable_http_app(), host="0.0.0.0", port=port)
