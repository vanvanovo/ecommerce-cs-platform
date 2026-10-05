# backend/agents/order/graph.py
# 订单/物流 Agent 的 LangGraph 状态图

from langgraph.graph import StateGraph, START, END

from backend.agents.order.nodes import (
    ask_choose_node,
    ask_clarify_node,
    compose_answer_node,
    extract_slots_node,
    fetch_data_node,
    human_handoff_node,
    not_found_node,
    route_after_clarify,
    route_after_extract,
    route_after_fetch,
)
from backend.agents.order.state import OrderState
from backend.core.memory import get_memory_saver


def build_order_graph():
    """
    构建并编译订单/物流 Agent 状态图。

    执行链路：
        extract_slots →（有单号/手机号？）
              ├─ 否 → ask_clarify →（两次仍缺 → 转人工 / 否则等待用户补充）
              └─ 是 → fetch_data（MCP）→（ok / multiple / missing / error）
                        ├─ ok       → compose_answer → END
                        ├─ multiple → ask_choose     → END
                        ├─ missing  → not_found      → END
                        └─ error    → human_handoff  → END
    """
    builder = StateGraph(OrderState)

    builder.add_node("extract_slots", extract_slots_node)
    builder.add_node("fetch_data",    fetch_data_node)
    builder.add_node("compose_answer", compose_answer_node)
    builder.add_node("ask_clarify",   ask_clarify_node)
    builder.add_node("ask_choose",    ask_choose_node)
    builder.add_node("not_found",     not_found_node)
    builder.add_node("human_handoff", human_handoff_node)

    builder.add_edge(START, "extract_slots")
    builder.add_conditional_edges("extract_slots", route_after_extract, {
        "fetch": "fetch_data",
        "clarify": "ask_clarify",
    })
    builder.add_conditional_edges("fetch_data", route_after_fetch, {
        "compose": "compose_answer",
        "ask_choose": "ask_choose",
        "not_found": "not_found",
        "handoff": "human_handoff",
    })
    builder.add_conditional_edges("ask_clarify", route_after_clarify, {
        "end": END,
        "human": "human_handoff",
    })

    builder.add_edge("compose_answer", END)
    builder.add_edge("ask_choose",     END)
    builder.add_edge("not_found",      END)
    builder.add_edge("human_handoff",  END)

    return builder.compile(checkpointer=get_memory_saver("order"))


# ── 图缓存（懒加载单例）─────────────────────────────────────
_order_graph = None


def get_order_graph():
    global _order_graph
    if _order_graph is None:
        _order_graph = build_order_graph()
    return _order_graph
