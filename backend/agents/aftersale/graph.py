# backend/agents/aftersale/graph.py
# 售后/退款 Agent 的 LangGraph 状态图（含物流异常分支 + HitL 主管审批）

from langgraph.graph import StateGraph, START, END

from backend.agents.aftersale.nodes import (
    ask_clarify_node,
    check_eligibility_node,
    check_logistics_node,
    compose_answer_node,
    create_ticket_node,
    human_handoff_node,
    logistics_anomaly_handoff_node,
    not_found_node,
    parse_request_node,
    reject_node,
    reject_reviewed_node,
    route_after_check,
    route_after_clarify,
    route_after_logistics,
    route_after_parse,
    route_after_review,
    supervisor_review_node,
)
from backend.agents.aftersale.state import AftersaleState
from backend.core.memory import get_memory_saver


def build_aftersale_graph():
    """
    构建并编译售后/退款 Agent 状态图。

    执行链路：
        parse_request →（有订单号？）
          ├─ 否 → ask_clarify →（两次仍缺 → 转人工 / 否则等待补充）
          └─ 是 → check_logistics（"签收未收到"话术 → 查轨迹）
                    ├─ 最新节点=已签收 → logistics_handoff（转人工核实，防丢件/误签）
                    └─ 正常 → check_eligibility（MCP 规则引擎）
                              ├─ auto_approve → create_ticket → compose_answer → END
                              ├─ submit_for_review / quality_path
                              │      → supervisor_review [interrupt]
                              │            ├─ approve/modify → create_ticket → compose_answer → END
                              │            └─ reject         → reject_reviewed → END
                              ├─ reject / not_delivered → reject_node → END
                              ├─ not_found → not_found → END
                              └─ error     → human_handoff → END
    """
    builder = StateGraph(AftersaleState)

    builder.add_node("parse_request",       parse_request_node)
    builder.add_node("check_logistics",     check_logistics_node)
    builder.add_node("check_eligibility",   check_eligibility_node)
    builder.add_node("supervisor_review",   supervisor_review_node)
    builder.add_node("create_ticket",       create_ticket_node)
    builder.add_node("compose_answer",      compose_answer_node)
    builder.add_node("reject",              reject_node)
    builder.add_node("reject_reviewed",     reject_reviewed_node)
    builder.add_node("ask_clarify",         ask_clarify_node)
    builder.add_node("not_found",           not_found_node)
    builder.add_node("human_handoff",       human_handoff_node)
    builder.add_node("logistics_handoff",   logistics_anomaly_handoff_node)

    builder.add_edge(START, "parse_request")
    builder.add_conditional_edges("parse_request", route_after_parse, {
        "check": "check_logistics",
        "clarify": "ask_clarify",
    })
    builder.add_conditional_edges("check_logistics", route_after_logistics, {
        "anomaly": "logistics_handoff",
        "normal": "check_eligibility",
    })
    builder.add_conditional_edges("check_eligibility", route_after_check, {
        "create": "create_ticket",
        "review": "supervisor_review",
        "reject": "reject",
        "not_found": "not_found",
        "handoff": "human_handoff",
    })
    builder.add_conditional_edges("supervisor_review", route_after_review, {
        "create": "create_ticket",
        "reject_reviewed": "reject_reviewed",
    })
    builder.add_conditional_edges("ask_clarify", route_after_clarify, {
        "end": END,
        "human": "human_handoff",
    })

    builder.add_edge("create_ticket",      "compose_answer")
    builder.add_edge("compose_answer",     END)
    builder.add_edge("reject",             END)
    builder.add_edge("reject_reviewed",    END)
    builder.add_edge("not_found",          END)
    builder.add_edge("human_handoff",      END)
    builder.add_edge("logistics_handoff",  END)

    return builder.compile(checkpointer=get_memory_saver("aftersale"))


# ── 图缓存（懒加载单例）─────────────────────────────────────
_aftersale_graph = None


def get_aftersale_graph():
    global _aftersale_graph
    if _aftersale_graph is None:
        _aftersale_graph = build_aftersale_graph()
    return _aftersale_graph
