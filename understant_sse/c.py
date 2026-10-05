import json
from fastapi import FastAPI
from sse_starlette.sse import EventSourceResponse
from langgraph.graph import StateGraph, MessagesState, START, END
from langchain_core.messages import HumanMessage
from backend.core.llm_factory import get_llm
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage
from typing import Annotated, Optional


# ========== 2. 构建最简 LangGraph（只有 1 个节点） ==========
async def call_model(state: MessagesState, config):
    """节点函数：直接调用 LLM"""
    model = get_llm(agent_type="qa",streaming=True)
    response = await model.ainvoke(state["messages"])
    return {"messages": [response]}   # 返回追加消息

class MessagesState(TypedDict):
    """
    智能问答 Agent 的完整状态定义。
    所有节点通过读写此 State 进行数据传递。
    """

    # ── ① 消息历史（LangGraph 核心，add_messages reducer）────────
    # 节点每次返回 messages 时自动追加，不覆盖历史
    messages: Annotated[list[BaseMessage], add_messages]
# 构建图：START -> call_model -> END
graph_builder = StateGraph(MessagesState)
graph_builder.add_node("call_model", call_model)
graph_builder.add_edge(START, "call_model")
graph_builder.add_edge("call_model", END)
graph = graph_builder.compile()

# ========== 3. FastAPI 应用 ==========
app_web = FastAPI()

@app_web.post("/demo/stream")
async def stream_chat(message: str):
    """流式接口：接收 message，推送 SSE 事件"""

    async def event_generator():
        # 初始状态：只放用户输入
        initial_state = {"messages": [HumanMessage(content=message)]}

        try:
            # ⭐ 核心：astream_events 把图执行过程变成事件流
            async for event in graph.astream_events(initial_state, version="v2"):
                print(event)
                print("*"*80)
                evt = event["event"]
                node = event.get("metadata", {}).get("langgraph_node", "")

                # --- 事件1: 节点开始（模拟“思考中”） ---
                if evt == "on_chain_start" and node == "call_model":
                    yield {
                        "data": json.dumps({"type": "status", "msg": "🤔 AI 正在思考..."}, ensure_ascii=False)
                    }

                # --- 事件2: LLM 逐字吐出 token（最核心） ---
                elif evt == "on_chat_model_stream" and node == "call_model":
                    chunk = event["data"].get("chunk")
                    if chunk and chunk.content:
                        yield {
                            "data": json.dumps({"type": "token", "content": chunk.content},ensure_ascii=False)
                        }

                # --- 事件3: 节点结束（捕获完整回复） ---
                elif evt == "on_chain_end" and node == "call_model":
                    output = event["data"].get("output", {})
                    # 这里 output 就是 AIMessage 对象，取出完整内容备用
                    full_answer = output.get("messages", [])[-1].content if output.get("messages") else ""
                    yield {
                        "data": json.dumps({"type": "meta", "full_answer": full_answer},ensure_ascii=False)
                    }

        except Exception as e:
            yield {
                "data": json.dumps({"type": "error", "message": str(e)},ensure_ascii=False)
            }
            return

        # --- 事件4: 结束信号 ---
        yield {"data": json.dumps({"type": "done"},ensure_ascii=False)}

    return EventSourceResponse(event_generator())

# ========== 4. 启动服务 ==========
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app_web, host="0.0.0.0", port=8000)