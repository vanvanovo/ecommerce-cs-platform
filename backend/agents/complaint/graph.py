# backend/agents/complaint/graph.py
# 投诉/转人工 Agent 的 LangGraph 状态图

from langgraph.graph import StateGraph, START, END

from backend.agents.complaint.nodes import (
    analyze_node,
    escalate_node,
    resolve_node,
    route_after_analyze,
)
from backend.agents.complaint.state import ComplaintState
from backend.core.memory import get_memory_saver


def build_complaint_graph():
    """
    构建并编译投诉/转人工 Agent 状态图。

    执行链路：
        analyze（高危词/负面词扫描）
          ├─ high   → escalate（订单信息 + 交接包 + 安抚话术，转人工）
          └─ normal/low → resolve（安抚 + 解决建议）
    """
    builder = StateGraph(ComplaintState)

    builder.add_node("analyze",  analyze_node)
    builder.add_node("escalate", escalate_node)
    builder.add_node("resolve",  resolve_node)

    builder.add_edge(START, "analyze")
    builder.add_conditional_edges("analyze", route_after_analyze, {
        "escalate": "escalate",
        "resolve": "resolve",
    })
    builder.add_edge("escalate", END)
    builder.add_edge("resolve",  END)

    return builder.compile(checkpointer=get_memory_saver("complaint"))


# ── 图缓存（懒加载单例）─────────────────────────────────────
_complaint_graph = None


def get_complaint_graph():
    global _complaint_graph
    if _complaint_graph is None:
        _complaint_graph = build_complaint_graph()
    return _complaint_graph
