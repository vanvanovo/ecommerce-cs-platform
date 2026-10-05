# from typing import TypedDict
# from langgraph.graph import StateGraph, START, END
#
# class S(TypedDict):
#     a: int
#     b: int
#
# def node1(state: S) -> dict:
#     return {"a": 100}        # 只更新 a，不动 b
#
# builder = StateGraph(S)
# builder.add_node("n1", node1)
# builder.add_edge(START, "n1")
# builder.add_edge("n1", END)
# graph = builder.compile()
#
# print(graph.invoke({"a": 1, "b": 2}))

# from typing import TypedDict
# from langgraph.graph import StateGraph, START, END
#
# class ChatS(TypedDict):
#     messages: list
#
# def add_one(state: ChatS) -> dict:
#     return {"messages": ["新消息"]}     # 想「加」一条，但默认是「覆盖」
#
# builder = StateGraph(ChatS)
# builder.add_node("n", add_one)
# builder.add_edge(START, "n")
# builder.add_edge("n", END)
# graph = builder.compile()
#
# # 初始已经有两条历史消息
# print(graph.invoke({"messages": ["历史1", "历史2"]}))


#
# import operator
# from typing import Annotated, TypedDict
# from langgraph.graph import StateGraph, START, END
#
# class ChatS(TypedDict):
#     # 关键：用 operator.add 作为合并规则 → 列表会「拼接」而不是「覆盖」
#     messages: Annotated[list, operator.add]
#
# def add_one(state: ChatS) -> dict:
#     return {"messages": ["新消息"]}
#
# builder = StateGraph(ChatS)
# builder.add_node("n", add_one)
# builder.add_edge(START, "n")
# builder.add_edge("n", END)
# graph = builder.compile()
#
# print(graph.invoke({"messages": ["历史1", "历史2"]}))


from typing import Annotated, TypedDict
from langgraph.graph import StateGraph, START, END

def add(old: int, new: int) -> int:     # 自定义 Reducer：把新旧值相加
    return old + new

class CounterState(TypedDict):
    count: Annotated[int, add]           # count 字段的合并方式 = 相加

def step(state: CounterState) -> dict:
    return {"count": 1}                  # 每个节点只「贡献」+1

builder = StateGraph(CounterState)
builder.add_node("a", step)
builder.add_node("b", step)
builder.add_node("c", step)
builder.add_edge(START, "a")
builder.add_edge("a", "b")
builder.add_edge("b", "c")
builder.add_edge("c", END)
graph = builder.compile()

print(graph.invoke({"count": 0}))
