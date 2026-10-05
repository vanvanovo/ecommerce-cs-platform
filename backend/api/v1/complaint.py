# backend/api/v1/complaint.py
# 投诉/转人工 Agent HTTP 接口（P3）
# POST /api/v1/complaint/chat  {session_id, message}
# 容错：图调用经 with_retry 三层兜底

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from langchain_core.messages import HumanMessage

from backend.agents.complaint.graph import get_complaint_graph
from backend.core.logger import get_logger
from backend.core.memory import build_config
from backend.core.retry import with_retry
from backend.dependencies import get_current_user

router = APIRouter()
logger = get_logger(__name__)


class ComplaintChatRequest(BaseModel):
    session_id: str = Field(..., description="会话 ID")
    message: str = Field(..., min_length=1, max_length=2000)


@router.post("/chat")
async def complaint_chat(req: ComplaintChatRequest, current_user: dict = Depends(get_current_user)):
    """投诉处理：风险识别 → 高危转人工（交接包）/ 一般安抚解决。"""
    graph = get_complaint_graph()
    config = build_config(current_user["user_id"], req.session_id)

    initial_state = {
        "messages": [HumanMessage(content=req.message)],
        "customer_id": current_user["user_id"],
        "tenant_id": current_user.get("tenant_id", "tenant_default"),
        "session_id": req.session_id,
    }

    @with_retry(agent_type="complaint")
    async def _invoke():
        return await graph.ainvoke(initial_state, config=config)

    try:
        result = await _invoke()
    except Exception as e:
        logger.error("complaint_chat.failed", error=str(e)[:300])
        raise HTTPException(status_code=500, detail="投诉处理服务暂时不可用，请稍后重试")

    if result.get("fallback_used"):               # 三层兜底：情绪场景直接转人工话术
        return {
            "answer": result.get("content", "非常抱歉，已为你优先转接人工专员，请稍候。"),
            "need_human": True,
            "fallback_used": True,
        }

    logger.info(
        "complaint_chat.done",
        session_id=req.session_id,
        risk_level=result.get("risk_level"),
        need_human=result.get("need_human", False),
    )
    return {
        "answer": result.get("answer", ""),
        "risk_level": result.get("risk_level"),
        "risk_reasons": result.get("risk_reasons"),
        "structured_output": result.get("structured_output"),
        "need_human": result.get("need_human", False),
        "handoff_summary": result.get("handoff_summary"),
    }
