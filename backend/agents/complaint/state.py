# backend/agents/complaint/state.py
# 投诉/转人工 Agent 的状态定义

from typing import Annotated, Optional
from typing_extensions import TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class ComplaintState(TypedDict, total=False):
    # ── 请求上下文 ──
    customer_id: str
    tenant_id: str
    session_id: str
    messages: Annotated[list[BaseMessage], add_messages]

    # ── 情绪与风险分析 ──
    order_id: Optional[str]
    risk_level: Optional[str]          # high / normal / low
    risk_reasons: Optional[list]

    # ── 输出 ──
    answer: Optional[str]
    structured_output: Optional[dict]
    need_human: bool
    handoff_summary: Optional[str]
