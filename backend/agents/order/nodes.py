# backend/agents/order/nodes.py
# 订单/物流 Agent 的节点实现
#
# 设计取舍：订单号（A1024）/手机号是"强格式槽位"，
# 用规则（正则）抽取比 LLM 更准、更快、更便宜；LLM 用于答复生成与话术适配。

import json
import re

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from backend.agents.common import (
    build_handoff_summary,
    call_cs_tool,
    last_human_text,
)
from backend.agents.order.prompts import (
    CLARIFY_TEXT,
    COMPOSE_ANSWER_PROMPT,
    HANDOFF_TEXT,
    NOT_FOUND_TEXT,
    ORDER_SYSTEM_PROMPT,
)
from backend.agents.order.state import OrderState
from backend.core.llm_factory import get_llm
from backend.core.logger import get_logger

logger = get_logger(__name__)

ORDER_ID_RE = re.compile(r"(?<![0-9A-Za-z])A\d{4}(?![0-9])", re.IGNORECASE)
PHONE_RE = re.compile(r"(?<!\d)1\d{10}(?!\d)")
LOGISTICS_KEYWORDS = (
    "物流", "快递", "包裹", "到哪", "到哪儿", "轨迹", "配送", "派送",
    "什么时候到", "几天到", "没收到", "签收",
)


# ── 槽位抽取（规则）──────────────────────────────────────────

async def extract_slots_node(state: OrderState) -> dict:
    """从对话历史中抽取订单号/手机号，并判断查询类型（规则优先）。"""
    text = " ".join(
        m.content if isinstance(m.content, str) else str(m.content)
        for m in state.get("messages", [])
        if isinstance(m, HumanMessage)
    )

    order_id = state.get("order_id")
    phone = state.get("phone")

    m = ORDER_ID_RE.search(text)
    if m:
        order_id = m.group(0).upper()
    m2 = PHONE_RE.search(text)
    if m2:
        phone = m2.group(0)

    kind = state.get("query_kind")
    if any(k in text for k in LOGISTICS_KEYWORDS):
        kind = "logistics"
    elif not kind:
        kind = "order"

    return {"order_id": order_id, "phone": phone, "query_kind": kind}


def route_after_extract(state: OrderState) -> str:
    return "fetch" if (state.get("order_id") or state.get("phone")) else "clarify"


# ── 数据获取（MCP）──────────────────────────────────────────

async def _fetch_by_order_id(order_id: str) -> dict:
    """按订单号取订单 + 物流轨迹。"""
    order = await call_cs_tool("get_order", {"order_id": order_id})
    if order.get("status") != "success":
        return {"fetch_status": "missing", "error": order.get("message", "")}

    tracks = await call_cs_tool("track_logistics", {"order_id": order_id})
    tracks_data = tracks.get("data", {}).get("tracks", []) if tracks.get("status") == "success" else []

    data = order["data"]
    return {
        "order_data": data,
        "items": data.get("items", []),
        "tracks": tracks_data,
        "fetch_status": "ok",
    }


async def fetch_data_node(state: OrderState) -> dict:
    """按订单号直查；只有手机号时先查最近订单列表。"""
    try:
        if state.get("order_id"):
            return await _fetch_by_order_id(state["order_id"])

        listed = await call_cs_tool("list_orders", {"phone": state["phone"], "limit": 5})
        if listed.get("status") != "success":
            return {"fetch_status": "missing", "error": listed.get("message", "")}

        orders = listed["data"]["orders"]
        if not orders:
            return {"fetch_status": "missing", "error": "该手机号名下没有订单"}
        if len(orders) == 1:
            return await _fetch_by_order_id(orders[0]["order_id"])
        return {"candidates": orders, "fetch_status": "multiple"}

    except Exception as e:                      # MCP 重试后仍失败 → 走转人工兜底
        logger.error("order_agent.fetch_failed", error=str(e)[:200])
        return {"fetch_status": "error", "error": str(e)[:200]}


def route_after_fetch(state: OrderState) -> str:
    status = state.get("fetch_status")
    return {
        "ok": "compose",
        "multiple": "ask_choose",
        "missing": "not_found",
        "error": "handoff",
    }.get(status, "not_found")


# ── 输出节点 ────────────────────────────────────────────────

async def compose_answer_node(state: OrderState) -> dict:
    """LLM 根据结构化数据生成客服口吻的回答。"""
    llm = get_llm("order", temperature=0.3)
    prompt = COMPOSE_ANSWER_PROMPT.format(
        question=last_human_text(state.get("messages", [])),
        kind=state.get("query_kind") or "order",
        order_json=json.dumps(state.get("order_data") or {}, ensure_ascii=False, default=str),
        tracks_json=json.dumps(state.get("tracks") or [], ensure_ascii=False, default=str),
    )
    resp = await llm.ainvoke([
        SystemMessage(content=ORDER_SYSTEM_PROMPT),
        HumanMessage(content=prompt),
    ])
    text = resp.content if isinstance(resp.content, str) else str(resp.content)

    tracks = state.get("tracks") or []
    order = state.get("order_data") or {}
    structured = {
        "order_id": order.get("order_id"),
        "status": order.get("status"),
        "total_amount": order.get("total_amount"),
        "latest_track": tracks[-1] if tracks else None,
    }
    return {
        "answer": text.strip(),
        "structured_output": structured,
        "need_human": False,
        "need_clarify": False,
        "clarify_count": 0,
        "handoff_summary": None,
        "messages": [AIMessage(content=text.strip())],
    }


async def ask_clarify_node(state: OrderState) -> dict:
    """缺槽位：追问一次；第二次仍缺 → 转人工（追问要有边界）。"""
    count = (state.get("clarify_count") or 0) + 1

    if count >= 2:
        summary = build_handoff_summary(
            state.get("messages", []),
            {"order_id": state.get("order_id"), "phone": state.get("phone")},
            "连续两次未能获取订单号/手机号，转人工继续处理",
        )
        return {
            "clarify_count": count, "need_human": True,
            "answer": HANDOFF_TEXT, "handoff_summary": summary,
            "messages": [AIMessage(content=HANDOFF_TEXT)],
        }

    return {
        "clarify_count": count, "need_clarify": True,
        "clarify_question": CLARIFY_TEXT, "answer": CLARIFY_TEXT,
        "messages": [AIMessage(content=CLARIFY_TEXT)],
    }


def route_after_clarify(state: OrderState) -> str:
    return "human" if state.get("need_human") else "end"


async def ask_choose_node(state: OrderState) -> dict:
    """手机号命中多单：列出候选，请用户指定订单号。"""
    lines = [
        f"- {o.get('order_id')}（{o.get('status')}，¥{o.get('total_amount')}）"
        for o in (state.get("candidates") or [])
    ]
    text = "你名下有多个订单，请告诉我要查哪一个的订单号：\n" + "\n".join(lines)
    return {
        "need_clarify": True, "clarify_question": text, "answer": text,
        "messages": [AIMessage(content=text)],
    }


async def not_found_node(state: OrderState) -> dict:
    return {
        "answer": NOT_FOUND_TEXT,
        "need_clarify": True, "clarify_question": NOT_FOUND_TEXT,
        "messages": [AIMessage(content=NOT_FOUND_TEXT)],
    }


async def human_handoff_node(state: OrderState) -> dict:
    """转人工：生成交接摘要（对话要点 + 已收集信息 + 故障说明）。"""
    summary = build_handoff_summary(
        state.get("messages", []),
        {"order_id": state.get("order_id"), "phone": state.get("phone")},
        f"查询异常：{state.get('error', '未知')}（已重试 3 次）",
    )
    return {
        "need_human": True, "answer": HANDOFF_TEXT, "handoff_summary": summary,
        "messages": [AIMessage(content=HANDOFF_TEXT)],
    }
