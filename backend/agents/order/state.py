# backend/agents/order/state.py
# 订单/物流 Agent 的状态定义（LangGraph State）

from typing import Annotated, Optional
from typing_extensions import TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class OrderState(TypedDict, total=False):
    # ── 请求上下文（API 注入，节点只读）──
    customer_id: str
    tenant_id: str
    session_id: str

    # ── 对话（reducer 累积，支持多轮补槽位）──
    messages: Annotated[list[BaseMessage], add_messages]

    # ── 槽位与意图 ──
    order_id: Optional[str]
    phone: Optional[str]
    query_kind: Optional[str]        # order（订单状态）/ logistics（物流追踪）

    # ── 数据（来自 MCP 工具）──
    order_data: Optional[dict]
    items: Optional[list]
    tracks: Optional[list]
    candidates: Optional[list]       # 手机号命中多单时的候选列表
    fetch_status: Optional[str]      # ok / multiple / missing / error
    error: Optional[str]

    # ── 输出 ──
    answer: Optional[str]
    structured_output: Optional[dict]
    need_human: bool
    need_clarify: bool
    clarify_question: Optional[str]
    clarify_count: int
    handoff_summary: Optional[str]
