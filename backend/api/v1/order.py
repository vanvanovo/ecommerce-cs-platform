# backend/api/v1/order.py
# 订单/物流 Agent HTTP 接口（P3）
# POST /api/v1/order/chat  {session_id, message} → 结构化响应
# 容错：图调用经 with_retry 三层兜底（重试 3 次 → Agent 降级 → 系统兜底）

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from langchain_core.messages import HumanMessage

from backend.agents.order.graph import get_order_graph
from backend.core.logger import get_logger
from backend.core.memory import build_config
from backend.core.retry import with_retry
from backend.dependencies import get_current_user

router = APIRouter()
logger = get_logger(__name__)


class OrderChatRequest(BaseModel):
    session_id: str = Field(..., description="会话 ID（同一会话多轮共用一个）")
    message: str = Field(..., min_length=1, max_length=2000, description="用户输入")


@router.post("/chat")
async def order_chat(req: OrderChatRequest, current_user: dict = Depends(get_current_user)):
    """订单/物流查询：抽取槽位 → 调 MCP 工具 → 生成回答；缺参追问、异常转人工。"""
    graph = get_order_graph()
    config = build_config(current_user["user_id"], req.session_id)

    initial_state = {
        "messages": [HumanMessage(content=req.message)],
        "customer_id": current_user["user_id"],
        "tenant_id": current_user.get("tenant_id", "tenant_default"),
        "session_id": req.session_id,
    }

    @with_retry(agent_type="order")
    async def _invoke():
        return await graph.ainvoke(initial_state, config=config)

    try:
        result = await _invoke()
    except Exception as e:
        logger.error("order_chat.failed", error=str(e)[:300])
        raise HTTPException(status_code=500, detail="订单查询服务暂时不可用，请稍后重试")

    if result.get("fallback_used"):               # 三层兜底：标准失败响应（不抛异常）
        return {
            "answer": result.get("content", "订单查询服务暂时不可用，请稍后重试"),
            "need_human": True,
            "fallback_used": True,
        }

    logger.info(
        "order_chat.done",
        session_id=req.session_id,
        fetch_status=result.get("fetch_status"),
        need_human=result.get("need_human", False),
        need_clarify=result.get("need_clarify", False),
    )
    return {
        "answer": result.get("answer", ""),
        "order_id": result.get("order_id"),
        "query_kind": result.get("query_kind"),
        "structured_output": result.get("structured_output"),
        "need_human": result.get("need_human", False),
        "need_clarify": result.get("need_clarify", False),
        "clarify_question": result.get("clarify_question"),
        "handoff_summary": result.get("handoff_summary"),
    }
