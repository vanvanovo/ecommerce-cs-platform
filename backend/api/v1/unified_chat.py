# backend/api/v1/unified_chat.py
# 统一 AI 助手流式接口（P4 电商版）
#
# 流程：
#   1) 规则前置拦截（问候/感谢/身份/转人工短语——零 Token）
#   2) Qwen 混合意图路由（core.router.route_ecom：本地优先 + 云端回退）
#   3) 分发：
#        - out_of_scope       → 引导说明（不调 Agent）
#        - human / 低置信      → 转人工分支（交接摘要 + 入未解决问题池）
#        - 单意图             → 短路直出（跳过汇总）
#        - 多意图             → asyncio.gather 并行 → LLM 汇总（去重/冲突/一致性校验）
#   4) SSE 事件：routing_decision / progress / token / handoff / guidance / meta / done / error

import asyncio
import hashlib
import json
import re
import time
import uuid as uuid_lib
from types import SimpleNamespace
from typing import Optional

import asyncpg
from fastapi import APIRouter, Depends
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from backend.agents.common import build_handoff_summary
from backend.config import get_settings
from backend.core.cache import TTL_ROUTE, cache_get, cache_set, get_metrics, incr_metric
from backend.core.llm_factory import get_llm
from backend.core.logger import get_logger
from backend.core.orchestrator import AgentRequest, AgentType, get_orchestrator
from backend.core.router import route_ecom
from backend.dependencies import get_current_user

router = APIRouter()
logger = get_logger(__name__)

SHORT_CIRCUIT_CONFIDENCE = 0.8      # 单意图高置信 → 短路直出（跳过汇总）
LOW_CONFIDENCE_HUMAN = 0.6          # 路由置信度低于此值 → 转人工兜底

_INTENT_TO_AGENT = {
    "product":    AgentType.QA,
    "order":      AgentType.ORDER,
    "logistics":  AgentType.ORDER,
    "aftersale":  AgentType.AFTERSALE,
    "complaint":  AgentType.COMPLAINT,
    "chitchat":   AgentType.QA,
    "out_of_scope": None,
}

_DISPLAY = {
    "product": "商品咨询", "order": "订单查询", "logistics": "物流追踪",
    "aftersale": "售后/退款", "complaint": "投诉处理", "chitchat": "闲聊",
    "out_of_scope": "超出服务范围", "human": "转人工",
}

_GREETING_EXACT = {
    "你好", "您好", "hi", "hello", "嗨", "在吗", "在么",
    "谢谢", "谢谢你", "感谢", "thanks", "thank you",
    "再见", "拜拜", "bye", "你是谁", "你叫什么", "你是什么",
    "你能做什么", "你有什么功能", "你能帮我做什么",
}
_GREETING_KW = ("你是谁", "你叫什么", "你能做什么", "你有什么功能", "介绍一下你自己", "自我介绍")
_HUMAN_PHRASES = ("转人工", "人工客服", "找客服", "转接人工", "要人工", "转真人", "真人客服", "找个人")

GREETING_REPLY = (
    "您好！我是电商智能客服，可以帮你：\n"
    "- 查订单 / 物流（提供订单号，如 A1024）\n"
    "- 办理退货、退款、换货\n"
    "- 咨询商品与售后政策\n"
    "- 投诉或转人工\n"
    "直接说需求就行～"
)


def _pre_filter(message: str) -> Optional[dict]:
    """规则前置：转人工短语 / 问候类，零 Token 直答。"""
    q = message.strip().lower()
    if any(p in q for p in _HUMAN_PHRASES):
        return {"kind": "human", "reason": "用户明确要求转人工"}
    if q in _GREETING_EXACT or any(k in q for k in _GREETING_KW):
        return {"kind": "template", "content": GREETING_REPLY}
    return None


def _sse(data: dict) -> dict:
    return {"data": json.dumps(data, ensure_ascii=False, default=str)}


def _chunks(text: str, size: int = 60):
    for i in range(0, len(text), size):
        yield text[i:i + size]


# ── 转人工分支（交接摘要 + 未解决问题池落库）──────────────────

def _dsn() -> str:
    s = get_settings()
    return (f"postgresql://{s.db_user}:{s.db_password}"
            f"@{s.db_host}:{s.db_port}/{s.db_name}")


async def _save_unresolved(current_user: dict, session_id: str, question: str, summary: str) -> None:
    """把转人工请求写入未解决问题池（失败不影响主流程）。"""
    try:
        try:
            cid = uuid_lib.UUID(current_user["user_id"])
        except (ValueError, KeyError):
            cid = None
        conn = await asyncpg.connect(_dsn())
        try:
            await conn.execute(
                "INSERT INTO unresolved_questions (tenant_id, customer_id, session_id, question, summary) "
                "VALUES ($1,$2,$3,$4,$5)",
                current_user.get("tenant_id", "tenant_default"), cid, session_id,
                question[:500], summary[:2000],
            )
        finally:
            await conn.close()
        logger.info("unified.unresolved_saved", session_id=session_id)
    except Exception as e:
        logger.warning("unified.save_unresolved_failed", error=str(e)[:150])


async def _human_flow(req, current_user: dict, t0: float, reason: str):
    """转人工：生成交接摘要 → 落库 → SSE handoff 事件。"""
    summary = build_handoff_summary(
        [HumanMessage(content=req.message)],
        {"转人工原因": reason},
        "请人工客服接手继续处理",
    )
    yield _sse({"type": "routing_decision", "intents": ["human"], "display": ["转人工"],
                "confidence": 1.0, "provider": "rule", "mode": "human"})
    yield _sse({"type": "progress", "stage": "正在为你转接人工客服…"})
    await _save_unresolved(current_user, req.session_id, req.message, summary)
    await incr_metric("handoff_total")
    yield _sse({"type": "handoff", "summary": summary, "reason": reason})
    for c in _chunks("已为你转接人工客服，请稍候。人工客服会看到本次对话内容，你无需重复描述。"):
        yield _sse({"type": "token", "content": c})
    yield _sse({"type": "meta", "mode": "human", "agents_used": [],
                "elapsed_ms": int((time.perf_counter() - t0) * 1000)})
    yield _sse({"type": "done"})


# ── 单 Agent 执行（经 Orchestrator，含三层兜底）──────────────

def _attach_reviews(results: list[dict], current_user: dict, session_id: str) -> None:
    """结果中有 HitL 暂停的（如售后审批）→ 登记审批单，补进内容。"""
    for r in results:
        md = r["response"].metadata or {}
        if not md.get("interrupted"):
            continue
        from backend.api.v1.aftersale import register_pending_review
        thread_id = f"customer_{current_user['user_id']}_session_{session_id}"
        rid = register_pending_review(
            thread_id, current_user["user_id"], session_id, md.get("review_payload") or {},
        )
        r["response"].content = (r["response"].content or "") + f"\n（已生成审批单 {rid}，主管审批后会通知你）"
        if isinstance(r["response"].structured, dict):
            r["response"].structured["review_id"] = rid
        logger.info("unified.review_registered", review_id=rid, intent=r["intent"])


async def _run_one(intent: str, message: str, current_user: dict, session_id: str) -> dict:
    orch = get_orchestrator()
    request = AgentRequest(
        student_id=current_user["user_id"],
        tenant_id=current_user.get("tenant_id", "tenant_default"),
        session_id=session_id,
        agent_type=_INTENT_TO_AGENT[intent],
        user_message=message,
    )
    resp = await orch.handle(request)
    return {"intent": intent, "agent_type": _INTENT_TO_AGENT[intent].value, "response": resp}


# ── 多意图汇总（含一致性校验）───────────────────────────────

AGGREGATE_SYSTEM_PROMPT = "你是电商客服平台的汇总助手，只基于给定专项结果做合并，绝不新增信息。"

AGGREGATE_PROMPT = """请把以下多条专项处理结果合并成一条给用户的完整回复。

【用户问题】
{question}

【各专项结果】
{parts}

要求：
1. 按用户诉求分段/分点回复，覆盖每个专项的结论；
2. 去重：重复信息只说一次；若专项之间冲突，以订单/审核数据为准并简要说明；
3. 严禁新增专项结果中不存在的信息（尤其金额、时效、政策条款）；
4. 中文、客服口吻、简洁，直接输出。"""

_ORDER_ID_RE = re.compile(r"A\d{4}")
_AMOUNT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*元")


def _verify_summary(summary: str, sources: str) -> bool:
    """确定性一致性校验：汇总里提到的订单号/金额必须能在专项结果里找到。"""
    src = sources.replace(" ", "")
    for oid in set(_ORDER_ID_RE.findall(summary)):
        if oid not in src:
            return False
    for amt in set(_AMOUNT_RE.findall(summary)):
        if amt in src:
            continue
        norm = amt.rstrip("0").rstrip(".") if "." in amt else amt
        if norm not in src:
            return False
    return True


async def _aggregate(question: str, results: list[dict]) -> tuple[str, bool]:
    parts = []
    for r in results:
        parts.append(f"【{_DISPLAY.get(r['intent'], r['intent'])}】\n{r['response'].content}")
    sources = "\n\n".join(parts)

    llm = get_llm("summarize", temperature=0.3)
    prompt = AGGREGATE_PROMPT.format(question=question, parts=sources)
    resp = await llm.ainvoke([SystemMessage(content=AGGREGATE_SYSTEM_PROMPT), HumanMessage(content=prompt)])
    text = (resp.content if isinstance(resp.content, str) else str(resp.content)).strip()

    if not _verify_summary(text, sources):
        logger.warning("unified.aggregate_verify_failed", question=question[:80])
        await incr_metric("hallucination_blocked")
        return "\n\n".join(parts), False          # 校验失败 → 降级用原文拼接（不润色）
    return text, True


# ── 接口 ────────────────────────────────────────────────────

class UnifiedChatRequest(BaseModel):
    session_id: str = Field(..., description="会话 ID")
    message:    str = Field(..., min_length=1, max_length=2000, description="用户输入")


@router.post("/stream")
async def unified_chat_stream(req: UnifiedChatRequest, current_user: dict = Depends(get_current_user)):
    """统一入口（SSE）：规则前置 → 意图路由 → 短路直出 / 并行汇总 / 转人工。"""

    async def event_generator():
        t0 = time.perf_counter()

        # ── 1) 规则前置（零 Token）──
        pre = _pre_filter(req.message)
        if pre and pre["kind"] == "template":
            yield _sse({"type": "token", "content": pre["content"]})
            yield _sse({"type": "done"})
            return
        if pre and pre["kind"] == "human":
            async for ev in _human_flow(req, current_user, t0, pre["reason"]):
                yield ev
            return

        # ── 2) 意图路由（Qwen 本地优先 + 云端回退；P6：重复问题走 Redis 缓存 10 分钟）──
        route_key = "cache:route:" + hashlib.md5(req.message.strip().lower().encode("utf-8")).hexdigest()
        cached_route = await cache_get(route_key)
        if cached_route:
            await incr_metric("route_cache_hit")
            decision = SimpleNamespace(
                intents=cached_route["intents"],
                confidence=cached_route["confidence"],
                provider="cache",
            )
            logger.info("unified.route_cache_hit", key=route_key[-10:])
        else:
            try:
                decision = await route_ecom(req.message)
            except Exception as e:
                logger.error("unified.route_failed", error=str(e)[:200])
                yield _sse({"type": "error", "message": "服务暂时不可用，请稍后重试"})
                yield _sse({"type": "done"})
                return
            await incr_metric("route_cache_miss")
            await cache_set(route_key,
                            {"intents": decision.intents,
                             "confidence": decision.confidence,
                             "provider": decision.provider},
                            ttl=TTL_ROUTE)

        # ── 3) 低置信 → 转人工兜底 ──
        if decision.confidence < LOW_CONFIDENCE_HUMAN:
            async for ev in _human_flow(req, current_user, t0, f"路由置信度较低（{decision.confidence:.2f}）"):
                yield ev
            return

        intents = [i for i in dict.fromkeys(decision.intents) if _INTENT_TO_AGENT.get(i)]
        if not intents:
            yield _sse({"type": "guidance",
                        "message": "这个问题超出我的服务范围～我可以帮你查订单/物流、办理售后、咨询商品政策，或转人工客服。"})
            yield _sse({"type": "done"})
            return

        mode = "single" if len(intents) == 1 else "parallel"
        short_circuit = len(intents) == 1 and decision.confidence >= SHORT_CIRCUIT_CONFIDENCE
        await incr_metric("short_circuit_total" if short_circuit else f"{mode}_total")

        yield _sse({
            "type": "routing_decision",
            "intents": intents,
            "display": [_DISPLAY.get(i, i) for i in intents],
            "confidence": round(decision.confidence, 3),
            "provider": decision.provider,
            "mode": "short_circuit" if short_circuit else mode,
        })

        # ── 4) 执行 ──
        results: list[dict] = []
        if mode == "single":
            intent = intents[0]
            yield _sse({"type": "progress", "stage": f"{_DISPLAY.get(intent, intent)}处理中…"})
            results.append(await _run_one(intent, req.message, current_user, req.session_id))
            _attach_reviews(results, current_user, req.session_id)
            final_text = results[0]["response"].content
            verified = True
        else:
            yield _sse({"type": "progress", "stage": f"正在并行处理 {len(intents)} 个诉求…"})
            gathered = await asyncio.gather(
                *[_run_one(i, req.message, current_user, req.session_id) for i in intents],
                return_exceptions=True,
            )
            for i, g in enumerate(gathered):
                if isinstance(g, Exception):
                    logger.error("unified.parallel_failed", intent=intents[i], error=str(g)[:150])
                else:
                    results.append(g)
            if not results:
                yield _sse({"type": "error", "message": "多个诉求均处理失败，请稍后重试或转人工"})
                yield _sse({"type": "done"})
                return
            _attach_reviews(results, current_user, req.session_id)
            yield _sse({"type": "progress", "stage": "汇总各专项结果…"})
            final_text, verified = await _aggregate(req.message, results)

        for c in _chunks(final_text):
            yield _sse({"type": "token", "content": c})

        # ── 5) 结果中有转人工诉求 → 交接事件 + 落库 ──
        handoff_summary = None
        for r in results:
            md = r["response"].metadata or {}
            if md.get("handoff_summary"):
                handoff_summary = md["handoff_summary"]
                break
            if (r["response"].structured or {}).get("action") == "escalated_to_human":
                handoff_summary = build_handoff_summary(
                    [HumanMessage(content=req.message)], {}, "投诉升级，需要人工跟进")
                break
        if handoff_summary:
            await _save_unresolved(current_user, req.session_id, req.message, handoff_summary)
            await incr_metric("handoff_total")
            yield _sse({"type": "handoff", "summary": handoff_summary, "reason": "需要人工介入"})

        # ── 6) 收尾 meta ──
        fallback_used = any(r["response"].fallback_used for r in results)
        if fallback_used:
            await incr_metric("fallback_total")
        yield _sse({
            "type": "meta",
            "mode": "short_circuit" if short_circuit else mode,
            "agents_used": [r["intent"] for r in results],
            "confidence": round(decision.confidence, 3),
            "provider": decision.provider,
            "verified": verified,
            "fallback_used": fallback_used,
            "sources": sorted({s for r in results
                               for s in ((r["response"].metadata or {}).get("sources") or [])}),
            "answer_modes": {r["intent"]: (r["response"].metadata or {}).get("answer_mode")
                             for r in results
                             if (r["response"].metadata or {}).get("answer_mode")},
            "elapsed_ms": int((time.perf_counter() - t0) * 1000),
        })
        yield _sse({"type": "done"})

    return EventSourceResponse(event_generator())


@router.get("/metrics")
async def chat_metrics(current_user: dict = Depends(get_current_user)):
    """监控埋点（P6）：Redis 指标计数——路由/检索缓存命中、短路/并行、转人工、工具调用成败、幻觉拦截。"""
    return {"metrics": await get_metrics()}
