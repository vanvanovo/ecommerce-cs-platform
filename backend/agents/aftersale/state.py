# backend/agents/aftersale/state.py
# 售后/退款 Agent 的状态定义（含 HitL 审批字段）

from typing import Annotated, Optional
from typing_extensions import TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AftersaleState(TypedDict, total=False):
    # ── 请求上下文 ──
    customer_id: str
    tenant_id: str
    session_id: str
    messages: Annotated[list[BaseMessage], add_messages]

    # ── 请求解析 ──
    order_id: Optional[str]
    ticket_type: Optional[str]       # refund / return / exchange
    reason: Optional[str]
    sku: Optional[str]
    clarify_count: int

    # ── 物流异常检测（签收未收到）──
    latest_track: Optional[dict]
    logistics_anomaly: Optional[bool]

    # ── 规则审核（MCP check_return_eligibility）──
    check_status: Optional[str]      # ok / not_found / error
    check_result: Optional[dict]
    auto_decision: Optional[str]     # auto_approve / submit_for_review / quality_path / reject / not_delivered

    # ── HitL 主管审批 ──
    review_payload: Optional[dict]
    supervisor_decision: Optional[dict]   # {action, comment, reviewer}

    # ── 结果 ──
    ticket_id: Optional[str]
    ticket_status: Optional[str]     # auto_approved / pending_review / approved / rejected / failed
    answer: Optional[str]
    structured_output: Optional[dict]
    need_human: bool
    need_clarify: bool
    clarify_question: Optional[str]
    handoff_summary: Optional[str]
    error: Optional[str]
