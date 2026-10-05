# backend/api/v1/aftersale.py
# 售后/退款 Agent HTTP 接口（P3，含 HitL 主管审批三件套）
#
#   POST /api/v1/aftersale/submit                 用户提交售后申请（可能自动通过 / 转主管审批 / 拒绝）
#   GET  /api/v1/aftersale/review/{review_id}     主管查看待审批详情（teacher/admin）
#   POST /api/v1/aftersale/confirm/{review_id}    主管审批（approve/modify/reject），恢复 interrupt

import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, status as http_status
from langchain_core.messages import HumanMessage
from langgraph.types import Command
from pydantic import BaseModel, Field

from backend.agents.aftersale.graph import get_aftersale_graph
from backend.core.logger import get_logger
from backend.core.memory import build_thread_id
from backend.core.retry import with_retry
from backend.dependencies import get_current_user

router = APIRouter()
logger = get_logger(__name__)

# 审批登记表：review_id → {thread_id, user_id, session_id, payload, created_at}
# 说明：demo 用内存；P6 换 Postgres checkpointer 时改为从图状态/DB 读取
_REVIEW_REGISTRY: dict[str, dict] = {}


class SubmitRequest(BaseModel):
    session_id: str = Field(..., description="会话 ID")
    message: str = Field(..., min_length=1, max_length=2000)


class ConfirmRequest(BaseModel):
    action: str = Field(..., description="approve / modify / reject")
    comment: str = Field("", max_length=500, description="审批意见")


def _extract_interrupt(result: dict) -> dict | None:
    """从 ainvoke 结果中取出 interrupt 的 payload。"""
    intr = result.get("__interrupt__")
    if not intr:
        return None
    first = intr[0] if isinstance(intr, (list, tuple)) and intr else intr
    value = getattr(first, "value", None)
    if value is None and isinstance(first, dict):
        value = first
    return value


def _require_supervisor(current_user: dict) -> None:
    if current_user.get("role") not in ("teacher", "admin"):
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN,
                            detail="仅主管（teacher/admin）可操作审批")


def register_pending_review(thread_id: str, user_id: str, session_id: str, payload: dict) -> str:
    """登记一条待审批单（/aftersale/submit 与统一入口并行路径共用）。"""
    review_id = "RV-" + uuid.uuid4().hex[:10]
    _REVIEW_REGISTRY[review_id] = {
        "thread_id": thread_id,
        "user_id": user_id,
        "session_id": session_id,
        "payload": payload,
        "created_at": time.time(),
    }
    return review_id


def list_pending_reviews() -> list[dict]:
    """待审批单列表（按提交时间排序；/aftersale/reviews 与运营台总览共用）。P6"""
    items = []
    for rid, entry in _REVIEW_REGISTRY.items():
        p = entry.get("payload") or {}
        check = p.get("check_result") or {}
        items.append({
            "review_id": rid,
            "order_id": p.get("order_id"),
            "ticket_type": p.get("ticket_type"),
            "amount": check.get("amount"),
            "suggested_action": p.get("suggested_action"),
            "reasons": check.get("reasons") or ([p.get("reason")] if p.get("reason") else []),
            "created_at": entry.get("created_at"),
        })
    items.sort(key=lambda x: x.get("created_at") or 0)
    return items


@router.get("/reviews")
async def list_reviews(current_user: dict = Depends(get_current_user)):
    """主管：待审批单列表（内存登记表，按提交时间排序）。"""
    _require_supervisor(current_user)
    items = list_pending_reviews()
    return {"count": len(items), "items": items}


@router.post("/submit")
async def submit_aftersale(req: SubmitRequest, current_user: dict = Depends(get_current_user)):
    """提交售后申请：系统自动审核 → 自动通过 / 转主管审批（返回 review_id）/ 拒绝。"""
    graph = get_aftersale_graph()
    thread_id = build_thread_id(current_user["user_id"], req.session_id)
    config = {"configurable": {"thread_id": thread_id}}

    initial_state = {
        "messages": [HumanMessage(content=req.message)],
        "customer_id": current_user["user_id"],
        "tenant_id": current_user.get("tenant_id", "tenant_default"),
        "session_id": req.session_id,
    }

    @with_retry(agent_type="aftersale")
    async def _invoke():
        return await graph.ainvoke(initial_state, config=config)

    try:
        result = await _invoke()
    except Exception as e:
        logger.error("aftersale.submit_failed", error=str(e)[:300])
        raise HTTPException(status_code=500, detail="售后服务暂时不可用，请稍后重试")

    if result.get("fallback_used"):               # 三层兜底：标准失败响应
        return {
            "status": "fallback",
            "answer": result.get("content", "售后服务暂时不可用，请稍后重试"),
            "need_human": True,
            "fallback_used": True,
        }

    interrupt_payload = _extract_interrupt(result)

    if interrupt_payload:
        review_id = register_pending_review(
            thread_id, current_user["user_id"], req.session_id, interrupt_payload,
        )
        logger.info("aftersale.pending_review", review_id=review_id,
                    order_id=interrupt_payload.get("order_id"))
        return {
            "status": "pending_review",
            "review_id": review_id,
            "answer": "你的退换货申请需要主管审批，已提交（一般 24 小时内完成），请留意通知。",
            "review": interrupt_payload,
        }

    return {
        "status": result.get("ticket_status") or ("rejected" if result.get("structured_output", {}).get("rejected") else "done"),
        "answer": result.get("answer", ""),
        "ticket_id": result.get("ticket_id"),
        "ticket_status": result.get("ticket_status"),
        "structured_output": result.get("structured_output"),
        "need_human": result.get("need_human", False),
        "need_clarify": result.get("need_clarify", False),
        "clarify_question": result.get("clarify_question"),
        "handoff_summary": result.get("handoff_summary"),
    }


@router.get("/review/{review_id}")
async def get_review(review_id: str, current_user: dict = Depends(get_current_user)):
    """主管查看待审批详情（工单材料 + 规则审核结果 + 建议动作）。"""
    _require_supervisor(current_user)
    entry = _REVIEW_REGISTRY.get(review_id)
    if not entry:
        raise HTTPException(status_code=404, detail="审批单不存在或已处理")

    graph = get_aftersale_graph()
    config = {"configurable": {"thread_id": entry["thread_id"]}}
    try:
        snapshot = await graph.aget_state(config)
        paused = bool(snapshot and snapshot.next)
    except Exception as e:
        logger.warning("aftersale.review_state_failed", review_id=review_id, error=str(e)[:150])
        paused = False

    return {
        "review_id": review_id,
        "status": "pending_review" if paused else "processed",
        "payload": entry["payload"],
        "session_id": entry["session_id"],
        "created_at": entry["created_at"],
    }


@router.post("/confirm/{review_id}")
async def confirm_review(review_id: str, req: ConfirmRequest, current_user: dict = Depends(get_current_user)):
    """主管审批：approve / modify / reject，恢复 interrupt 并落定工单状态。"""
    _require_supervisor(current_user)
    if req.action not in ("approve", "modify", "reject"):
        raise HTTPException(status_code=400, detail="action 仅支持 approve / modify / reject")

    entry = _REVIEW_REGISTRY.get(review_id)
    if not entry:
        raise HTTPException(status_code=404, detail="审批单不存在或已处理")

    graph = get_aftersale_graph()
    config = {"configurable": {"thread_id": entry["thread_id"]}}
    decision = {
        "action": req.action,
        "comment": req.comment,
        "reviewer": current_user["user_id"],
    }

    @with_retry(agent_type="aftersale")
    async def _resume():
        return await graph.ainvoke(Command(resume=decision), config=config)

    try:
        result = await _resume()
    except Exception as e:
        logger.error("aftersale.confirm_failed", review_id=review_id, error=str(e)[:300])
        raise HTTPException(status_code=500, detail="审批处理失败，请稍后重试")

    _REVIEW_REGISTRY.pop(review_id, None)
    logger.info("aftersale.reviewed", review_id=review_id, action=req.action,
                ticket_id=result.get("ticket_id"), ticket_status=result.get("ticket_status"))

    return {
        "review_id": review_id,
        "action": req.action,
        "answer": result.get("answer", ""),
        "ticket_id": result.get("ticket_id"),
        "ticket_status": result.get("ticket_status"),
        "structured_output": result.get("structured_output"),
    }
