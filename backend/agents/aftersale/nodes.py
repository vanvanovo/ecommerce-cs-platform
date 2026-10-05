# backend/agents/aftersale/nodes.py
# 售后/退款 Agent 的节点实现（规则审核 + 主管 HitL 审批 + MCP 建单）
#
# 处理链路（对齐《售后政策》规则）：
#   parse_request → check_eligibility（MCP 规则引擎）
#     ├─ auto_approve       → create_ticket → compose_answer
#     ├─ submit_for_review / quality_path → supervisor_review [interrupt] →（approve/modify）create_ticket
#     │                                                  └─（reject）reject_reviewed
#     └─ reject / not_delivered → reject_node

import json
import re

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.types import interrupt

from backend.agents.aftersale.prompts import (
    AFTERSALE_SYSTEM_PROMPT,
    CLARIFY_TEXT,
    HANDOFF_TEXT,
    LOGISTICS_ANOMALY_TEXT,
    NOT_FOUND_TEXT,
    REVIEW_TITLE,
    SUBMIT_ANSWER_PROMPT,
)
from backend.agents.aftersale.state import AftersaleState
from backend.agents.common import build_handoff_summary, call_cs_tool, last_human_text
from backend.core.llm_factory import get_llm
from backend.core.logger import get_logger

logger = get_logger(__name__)

ORDER_ID_RE = re.compile(r"(?<![0-9A-Za-z])A\d{4}(?![0-9])", re.IGNORECASE)
SKU_RE = re.compile(r"(?<![0-9A-Za-z])SKU-\d{4}(?![0-9])", re.IGNORECASE)
EXCHANGE_HINTS = ("换货", "换新", "换一个", "换个", "换成")
REFUND_HINTS = ("退款", "退钱", "退我")


# ── 请求解析 ────────────────────────────────────────────────

async def parse_request_node(state: AftersaleState) -> dict:
    """抽取订单号/SKU，识别售后类型（退款/退货/换货），记录诉求原文。"""
    text = " ".join(
        m.content if isinstance(m.content, str) else str(m.content)
        for m in state.get("messages", [])
        if isinstance(m, HumanMessage)
    )

    order_id = state.get("order_id")
    m = ORDER_ID_RE.search(text)
    if m:
        order_id = m.group(0).upper()

    sku = state.get("sku")
    ms = SKU_RE.search(text)
    if ms:
        sku = ms.group(0).upper()

    ticket_type = state.get("ticket_type")
    if not ticket_type:
        if any(k in text for k in EXCHANGE_HINTS):
            ticket_type = "exchange"
        elif any(k in text for k in REFUND_HINTS):
            ticket_type = "refund"
        else:
            ticket_type = "return"

    reason = state.get("reason") or last_human_text(state.get("messages", []))[:200]

    return {
        "order_id": order_id, "sku": sku,
        "ticket_type": ticket_type, "reason": reason,
    }


def route_after_parse(state: AftersaleState) -> str:
    return "check" if state.get("order_id") else "clarify"


# ── 物流异常检测（签收未收到 → 转人工核实）────────────────────
# 业务背景：用户声称"显示签收但没收到"属于物流异常件（疑似丢件/误签），
# 不能按普通退款规则处理，必须人工核实——这是真实客服系统的标准防线。

CLAIM_KEYWORDS = (
    "没收到", "未收到", "没有收到", "还没收到", "没拿到", "没见着",
    "显示签收", "签收但", "丢件", "少件", "空包裹", "没给我送",
)


async def check_logistics_node(state: AftersaleState) -> dict:
    """命中"签收未收到"话术时查物流：最新节点=已签收 → 标记异常。"""
    text = " ".join(
        m.content if isinstance(m.content, str) else str(m.content)
        for m in state.get("messages", [])
        if isinstance(m, HumanMessage)
    )
    claim = any(k in text for k in CLAIM_KEYWORDS)
    if not (claim and state.get("order_id")):
        return {"logistics_anomaly": False}

    try:
        res = await call_cs_tool("track_logistics", {"order_id": state["order_id"]})
    except Exception as e:                        # 查询失败不阻断主流程
        logger.warning("aftersale.track_failed", error=str(e)[:150])
        return {"logistics_anomaly": False}

    if res.get("status") != "success":
        return {"logistics_anomaly": False}

    latest = (res.get("data") or {}).get("latest") or {}
    if "已签收" in (latest.get("status") or ""):
        logger.info("aftersale.logistics_anomaly", order_id=state.get("order_id"),
                    latest=latest.get("status"))
        return {"latest_track": latest, "logistics_anomaly": True}
    return {"latest_track": latest, "logistics_anomaly": False}


def route_after_logistics(state: AftersaleState) -> str:
    return "anomaly" if state.get("logistics_anomaly") else "normal"


async def logistics_anomaly_handoff_node(state: AftersaleState) -> dict:
    """物流异常件：生成交接包转人工核实（不直接走退款规则）。"""
    latest = state.get("latest_track") or {}
    summary = build_handoff_summary(
        state.get("messages", []),
        {
            "order_id": state.get("order_id"),
            "物流最新节点": latest.get("status"),
            "节点时间": latest.get("track_time"),
        },
        "物流显示已签收但用户声称未收到，需人工核实（疑似丢件/误签）",
    )
    return {
        "answer": LOGISTICS_ANOMALY_TEXT,
        "need_human": True,
        "handoff_summary": summary,
        "structured_output": {"action": "logistics_anomaly", "latest_track": latest},
        "messages": [AIMessage(content=LOGISTICS_ANOMALY_TEXT)],
    }


# ── 规则审核（MCP）───────────────────────────────────────────

async def check_eligibility_node(state: AftersaleState) -> dict:
    """调用 MCP 规则引擎核对退换货资格（7 天窗口 / 拆封 / 金额阈值 / 保修）。"""
    try:
        res = await call_cs_tool("check_return_eligibility", {
            "order_id": state["order_id"],
            "sku": state.get("sku"),
            "reason": state.get("reason"),
        })
    except Exception as e:                       # MCP 重试后仍失败
        logger.error("aftersale.check_failed", error=str(e)[:200])
        return {"check_status": "error", "error": str(e)[:200]}

    if res.get("status") != "success":
        return {"check_status": "not_found", "error": res.get("message", "")}

    check = res["data"]
    logger.info("aftersale.check_done", order_id=state.get("order_id"),
                next_step=check.get("next_step"))
    return {
        "check_status": "ok",
        "check_result": check,
        "auto_decision": check.get("next_step"),
    }


def route_after_check(state: AftersaleState) -> str:
    if state.get("check_status") == "not_found":
        return "not_found"
    if state.get("check_status") == "error":
        return "handoff"

    decision = state.get("auto_decision")
    if decision == "auto_approve":
        return "create"
    if decision in ("submit_for_review", "quality_path"):
        return "review"
    return "reject"                              # reject / not_delivered


# ── HitL：主管审批 ──────────────────────────────────────────

async def supervisor_review_node(state: AftersaleState) -> dict:
    """高风险退换货暂停，等待主管审批（interrupt）。resume 后拿到审批决定。"""
    payload = {
        "type": "aftersale_review",
        "order_id": state.get("order_id"),
        "ticket_type": state.get("ticket_type"),
        "reason": state.get("reason"),
        "check_result": state.get("check_result"),
        "suggested_action": state.get("auto_decision"),
        "message": REVIEW_TITLE,
    }
    decision = interrupt(payload)                # ← 图暂停；Command(resume=...) 后在此继续
    return {"review_payload": payload, "supervisor_decision": decision or {}}


def route_after_review(state: AftersaleState) -> str:
    action = (state.get("supervisor_decision") or {}).get("action")
    return "create" if action in ("approve", "modify") else "reject_reviewed"


# ── 建单与结果 ──────────────────────────────────────────────

async def create_ticket_node(state: AftersaleState) -> dict:
    """MCP 创建售后工单（幂等）；主管已审批的，把工单状态落定为 approved。"""
    decision = state.get("supervisor_decision") or {}
    order_id = state["order_id"]
    ticket_type = state.get("ticket_type") or "return"
    key = f"{order_id}|{state.get('session_id')}|{ticket_type}|{state.get('sku') or 'all'}"

    try:
        res = await call_cs_tool("create_return_ticket", {
            "order_id": order_id,
            "ticket_type": ticket_type,
            "reason": state.get("reason") or "",
            "sku": state.get("sku"),
            "idempotency_key": key,
        })
    except Exception as e:
        logger.error("aftersale.create_ticket_failed", error=str(e)[:200])
        return {"ticket_status": "failed", "error": str(e)[:200]}

    if res.get("status") not in ("success", "duplicate"):
        return {"ticket_status": "failed", "error": res.get("message", "")}

    data = res.get("data") or {}
    ticket_id = data.get("ticket_id")
    status = data.get("status")

    # 主管审批通过 → 审批工具把 pending_review 落定为 approved
    if ticket_id and decision.get("action") in ("approve", "modify") and status == "pending_review":
        try:
            rev = await call_cs_tool("review_ticket", {
                "ticket_id": ticket_id,
                "decision": decision.get("action"),
                "reviewer": decision.get("reviewer", ""),
                "comment": decision.get("comment", ""),
            })
            status = (rev.get("data") or {}).get("status", status)
        except Exception as e:
            logger.warning("aftersale.review_ticket_failed", ticket_id=ticket_id, error=str(e)[:150])

    logger.info("aftersale.ticket_created", ticket_id=ticket_id, status=status)
    return {
        "ticket_id": ticket_id,
        "ticket_status": status,
        "structured_output": {
            "ticket_id": ticket_id, "ticket_status": status,
            "order_id": order_id, "ticket_type": ticket_type,
            "amount": (state.get("check_result") or {}).get("amount"),
        },
    }


async def compose_answer_node(state: AftersaleState) -> dict:
    """按处理动作生成给用户的回复。"""
    if state.get("ticket_status") == "failed":
        summary = build_handoff_summary(
            state.get("messages", []),
            {"order_id": state.get("order_id")},
            f"工单创建失败：{state.get('error', '未知')}",
        )
        return {
            "answer": HANDOFF_TEXT, "need_human": True, "handoff_summary": summary,
            "messages": [AIMessage(content=HANDOFF_TEXT)],
        }

    llm = get_llm("aftersale", temperature=0.3)
    action = state.get("ticket_status") or state.get("auto_decision") or ""
    prompt = SUBMIT_ANSWER_PROMPT.format(
        request=state.get("reason") or last_human_text(state.get("messages", [])),
        check_json=json.dumps(state.get("check_result") or {}, ensure_ascii=False, default=str),
        ticket_json=json.dumps({
            "ticket_id": state.get("ticket_id"),
            "status": state.get("ticket_status"),
        }, ensure_ascii=False),
        action=action,
    )
    resp = await llm.ainvoke([
        SystemMessage(content=AFTERSALE_SYSTEM_PROMPT),
        HumanMessage(content=prompt),
    ])
    text = resp.content if isinstance(resp.content, str) else str(resp.content)

    return {
        "answer": text.strip(),
        "need_human": False, "need_clarify": False,
        "clarify_count": 0, "handoff_summary": None,
        "messages": [AIMessage(content=text.strip())],
    }


async def reject_node(state: AftersaleState) -> dict:
    """规则不通过（超窗 / 未签收 / 类目不支持）：说明原因并给替代建议。"""
    check = state.get("check_result") or {}
    reasons = "；".join(check.get("reasons") or ["不满足售后条件"])
    text = f"抱歉，这笔订单暂不支持该售后申请：{reasons}。如需进一步处理，我可以为你转接人工客服。"
    return {
        "answer": text,
        "structured_output": {"rejected": True, "reasons": check.get("reasons")},
        "need_human": False, "need_clarify": False,
        "messages": [AIMessage(content=text)],
    }


async def reject_reviewed_node(state: AftersaleState) -> dict:
    """主管审批驳回：说明审批结论。"""
    decision = state.get("supervisor_decision") or {}
    check = state.get("check_result") or {}
    reason_text = (decision.get("comment") or "").strip() or "；".join(
        check.get("reasons") or ["主管未通过该申请"])
    text = f"很抱歉，你的售后申请未通过主管审核：{reason_text}。如仍有疑问，可以为你转接人工客服。"
    return {
        "answer": text, "ticket_status": "rejected",
        "structured_output": {"ticket_status": "rejected", "review_comment": decision.get("comment")},
        "need_human": False, "need_clarify": False,
        "messages": [AIMessage(content=text)],
    }


async def ask_clarify_node(state: AftersaleState) -> dict:
    """缺订单号：追问一次；第二次仍缺 → 转人工。"""
    count = (state.get("clarify_count") or 0) + 1
    if count >= 2:
        summary = build_handoff_summary(
            state.get("messages", []),
            {"order_id": state.get("order_id")},
            "连续两次未提供订单号，转人工继续处理",
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


def route_after_clarify(state: AftersaleState) -> str:
    return "human" if state.get("need_human") else "end"


async def not_found_node(state: AftersaleState) -> dict:
    return {
        "answer": NOT_FOUND_TEXT,
        "need_clarify": True, "clarify_question": NOT_FOUND_TEXT,
        "messages": [AIMessage(content=NOT_FOUND_TEXT)],
    }


async def human_handoff_node(state: AftersaleState) -> dict:
    summary = build_handoff_summary(
        state.get("messages", []),
        {"order_id": state.get("order_id")},
        f"售后审核异常：{state.get('error', '未知')}（已重试 3 次）",
    )
    return {
        "need_human": True, "answer": HANDOFF_TEXT, "handoff_summary": summary,
        "messages": [AIMessage(content=HANDOFF_TEXT)],
    }
