# backend/agents/complaint/nodes.py
# 投诉/转人工 Agent 的节点实现
#
# 设计说明：投诉处理分两层——
#   ① 规则层（零成本、确定性）：高危词/负面词扫描，决定要不要升级；
#   ② LLM 层：生成共情话术与解决建议。
# 转人工 = 生成"交接包"（对话摘要 + 订单信息 + 风险信号）交给坐席，
# 不需要图暂停（interrupt 用于审批场景，不用于交接场景）。

import json
import re

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from backend.agents.common import build_handoff_summary, call_cs_tool, last_human_text
from backend.agents.complaint.prompts import (
    COMPLAINT_SYSTEM_PROMPT,
    ESCALATE_PROMPT,
    RESOLVE_PROMPT,
)
from backend.agents.complaint.state import ComplaintState
from backend.core.llm_factory import get_llm
from backend.core.logger import get_logger

logger = get_logger(__name__)

ORDER_ID_RE = re.compile(r"(?<![0-9A-Za-z])A\d{4}(?![0-9])", re.IGNORECASE)

# 高危信号（命中即升级）：监管投诉 / 公开曝光 / 法律途径
HIGH_RISK_WORDS = (
    "12315", "曝光", "起诉", "举报", "消协", "黑猫", "媒体",
    "发帖", "小红书", "微博", "抖音曝光", "投诉到平台", "投诉升级", "差评",
)
# 负面情绪词（2 个以上升级）
NEGATIVE_WORDS = (
    "太差", "垃圾", "骗子", "气死", "恶心", "无语", "离谱", "过分",
    "态度差", "没人管", "没人理", "什么破",
)


async def analyze_node(state: ComplaintState) -> dict:
    """规则层：高危词 / 负面情绪词扫描 + 订单号抽取。"""
    text = " ".join(
        m.content if isinstance(m.content, str) else str(m.content)
        for m in state.get("messages", [])
        if isinstance(m, HumanMessage)
    )

    high_hits = [w for w in HIGH_RISK_WORDS if w in text]
    neg_hits = [w for w in NEGATIVE_WORDS if w in text]

    if high_hits:
        level = "high"
    elif len(neg_hits) >= 2:
        level = "high"
    elif neg_hits:
        level = "normal"
    else:
        level = "low"

    order_id = state.get("order_id")
    m = ORDER_ID_RE.search(text)
    if m:
        order_id = m.group(0).upper()

    logger.info("complaint.analyzed", risk_level=level,
                high_hits=len(high_hits), neg_hits=len(neg_hits))
    return {
        "order_id": order_id,
        "risk_level": level,
        "risk_reasons": high_hits + neg_hits,
    }


def route_after_analyze(state: ComplaintState) -> str:
    return "escalate" if state.get("risk_level") == "high" else "resolve"


async def _fetch_order_brief(order_id: str | None) -> dict | None:
    """可选增强：把手上的订单状态附进交接包（失败不影响主流程）。"""
    if not order_id:
        return None
    try:
        res = await call_cs_tool("get_order", {"order_id": order_id})
        if res.get("status") == "success":
            d = res["data"]
            return {
                "order_id": d.get("order_id"),
                "status": d.get("status"),
                "total_amount": d.get("total_amount"),
                "days_since_delivered": d.get("days_since_delivered"),
            }
    except Exception as e:
        logger.warning("complaint.fetch_order_failed", error=str(e)[:150])
    return None


async def escalate_node(state: ComplaintState) -> dict:
    """高危投诉：生成交接包 + 安抚话术，立即转人工。"""
    order_info = await _fetch_order_brief(state.get("order_id"))
    reasons = "、".join(state.get("risk_reasons") or [])
    summary = build_handoff_summary(
        state.get("messages", []),
        {"order_id": state.get("order_id"), "risk_reasons": state.get("risk_reasons")},
        json.dumps(order_info, ensure_ascii=False) if order_info else "",
    )

    llm = get_llm("complaint", temperature=0.5)
    prompt = ESCALATE_PROMPT.format(
        message=last_human_text(state.get("messages", [])),
        reasons=reasons or "情绪激烈",
        order_json=json.dumps(order_info or {}, ensure_ascii=False),
        summary=summary,
    )
    resp = await llm.ainvoke([
        SystemMessage(content=COMPLAINT_SYSTEM_PROMPT),
        HumanMessage(content=prompt),
    ])
    text = resp.content if isinstance(resp.content, str) else str(resp.content)

    return {
        "answer": text.strip(),
        "need_human": True,
        "handoff_summary": summary,
        "structured_output": {
            "risk_level": "high",
            "risk_reasons": state.get("risk_reasons"),
            "order": order_info,
            "action": "escalated_to_human",
        },
        "messages": [AIMessage(content=text.strip())],
    }


async def resolve_node(state: ComplaintState) -> dict:
    """一般不满：安抚 + 可执行建议（不转人工）。"""
    order_info = await _fetch_order_brief(state.get("order_id"))

    llm = get_llm("complaint", temperature=0.5)
    prompt = RESOLVE_PROMPT.format(
        message=last_human_text(state.get("messages", [])),
        order_json=json.dumps(order_info or {}, ensure_ascii=False),
    )
    resp = await llm.ainvoke([
        SystemMessage(content=COMPLAINT_SYSTEM_PROMPT),
        HumanMessage(content=prompt),
    ])
    text = resp.content if isinstance(resp.content, str) else str(resp.content)

    return {
        "answer": text.strip(),
        "need_human": False,
        "handoff_summary": None,
        "structured_output": {
            "risk_level": state.get("risk_level", "low"),
            "risk_reasons": state.get("risk_reasons"),
            "order": order_info,
            "action": "resolved",
        },
        "messages": [AIMessage(content=text.strip())],
    }
