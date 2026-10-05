# backend/core/router.py
# 电商意图路由（P1）：本地 Ollama Qwen 优先 + 云端 qwen-flash / DeepSeek 回退
#
# 统一输出 JSON：
#   {"intents": ["aftersale"], "slots": {"order_id": "A1024"},
#    "need_clarify": false, "confidence": 0.92}
#
# Provider：
#   ollama_cpu  —— 本地 Qwen（Ollama，num_gpu=0，检索栈独占 GPU）
#   ollama_gpu  —— 本地 Qwen（Ollama 自动分配 GPU）
#   dashscope   —— 百炼 qwen-flash（OpenAI 兼容）
#   deepseek    —— DeepSeek（最后兜底）
# 降级链：任一 provider 超时/报错 → 链上下一个 → 全部失败返回人工兜底

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field

import httpx

from backend.config import get_settings
from backend.core.logger import get_logger

logger = get_logger(__name__)

# ── 意图标签（与方案 §6.2 对齐）──────────────────────────────
INTENTS = ["product", "order", "logistics", "aftersale", "complaint", "human", "chitchat", "out_of_scope"]
INTENT_CN = {
    "product": "商品咨询", "order": "订单查询", "logistics": "物流追踪",
    "aftersale": "售后/退款", "complaint": "投诉", "human": "转人工",
    "chitchat": "闲聊", "out_of_scope": "超出服务范围",
}

ROUTE_PROMPT = """你是电商客服平台的意图路由器。请分析用户消息，只输出一行 JSON，不要输出其他任何文字。

可选意图（intents 数组，可多选，最多 3 个）：
- product：商品咨询（参数、价格、对比、是否支持无理由、保修）
- order：订单查询（订单状态、金额、买了什么）
- logistics：物流追踪（快递到哪了、什么时候到、物流不更新）
- aftersale：售后（退货、退款、换货、维修）
- complaint：投诉（不满、要投诉、曝光、差评、12315）
- human：用户明确要求转人工 / 找客服
- chitchat：问候、感谢、闲聊
- out_of_scope：与商城业务无关（写代码、天气、订机票等），礼貌说明能力范围

输出字段：
- intents：字符串数组（1~3 个）
- slots：对象；可包含 order_id（形如 A1024）、phone（11 位手机号）；没有则为空对象
- need_clarify：布尔值；缺少办理关键信息（如售后/查单缺订单号）时为 true
- confidence：0~1 的小数

判定规则（重要）：
1. order 只用于"查询订单本身"（状态、金额、明细、取消、改地址）；提到订单号是为了办售后或查物流时，分别归 aftersale / logistics，不要额外加 order。
2. logistics 看"快递/包裹/物流位置"和"发货/到货时间"；问"订单到哪一步了"这类订单进度归 order。
3. "推荐商品/类目/牌子"归 product；纯寒暄才归 chitchat。
4. need_clarify：办理类服务（退货/退款/换货/查单/查物流）缺少订单号时为 true；纯政策、规则、参数咨询（如"退款多久到账""保修多久"）不因缺订单号而追问，为 false。
5. 不要把消息里提到的商品名/订单号机械地当作意图："XX拆封了还能退吗"只归 aftersale；"XX多少钱"才归 product。
6. 只对用户"明确表达"的诉求打多标签；一句模糊诉求（如"我的单子怎么没动静"）只给最贴近的单个意图，宁少勿多。

示例：
用户: 耳机拆封了想退，订单A1024
输出: {"intents": ["aftersale"], "slots": {"order_id": "A1024"}, "need_clarify": false, "confidence": 0.92}

用户: 我想退货
输出: {"intents": ["aftersale"], "slots": {}, "need_clarify": true, "confidence": 0.85}

用户: 订单A1024到哪了，另外想问下耳机保修多久
输出: {"intents": ["logistics", "product"], "slots": {"order_id": "A1024"}, "need_clarify": false, "confidence": 0.9}

用户: 你好
输出: {"intents": ["chitchat"], "slots": {}, "need_clarify": false, "confidence": 0.95}

用户: 帮我写个 Python 爬虫
输出: {"intents": ["out_of_scope"], "slots": {}, "need_clarify": false, "confidence": 0.9}

用户: 订单A1002我要退货
输出: {"intents": ["aftersale"], "slots": {"order_id": "A1002"}, "need_clarify": false, "confidence": 0.9}

用户: 退款一般多久到账？
输出: {"intents": ["aftersale"], "slots": {}, "need_clarify": false, "confidence": 0.9}

用户: 最近一笔订单到哪一步了？
输出: {"intents": ["order"], "slots": {}, "need_clarify": false, "confidence": 0.88}

用户: 包裹卡住了
输出: {"intents": ["logistics"], "slots": {}, "need_clarify": true, "confidence": 0.85}

用户: 智能手表 S2拆封了还能退吗？
输出: {"intents": ["aftersale"], "slots": {}, "need_clarify": false, "confidence": 0.9}

用户: 我上周下的单怎么还没动静？
输出: {"intents": ["order"], "slots": {}, "need_clarify": false, "confidence": 0.85}

现在处理：
用户: {message}
输出:"""


@dataclass
class RouteResult:
    intents: list[str]
    slots: dict
    need_clarify: bool
    confidence: float
    provider: str          # 实际生效的 provider（含 fallback 标记）
    latency_ms: int
    raw: str = field(default="", repr=False)


# ── 解析与校验 ──────────────────────────────────────────────

def parse_route_json(text: str) -> dict:
    """从模型输出中稳健地提取 JSON（容忍 code fence / 前后缀）。"""
    t = (text or "").strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t, flags=re.S).strip()
    start, end = t.find("{"), t.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError(f"输出中找不到 JSON：{t[:120]!r}")
    return json.loads(t[start:end + 1])


def normalize_route(data: dict) -> tuple[list[str], dict, bool, float]:
    """校验并归一化路由结果；intents 过滤到白名单，slots 只保留合法字段。"""
    raw_intents = data.get("intents") or []
    if isinstance(raw_intents, str):
        raw_intents = [raw_intents]
    intents = list(dict.fromkeys(i for i in raw_intents if i in INTENTS))[:3]
    if not intents:
        raise ValueError(f"intents 非法：{raw_intents!r}")

    slots: dict = {}
    raw_slots = data.get("slots") or {}
    if isinstance(raw_slots, dict):
        oid = str(raw_slots.get("order_id") or "").strip().upper()
        if re.fullmatch(r"A\d{4}", oid):
            slots["order_id"] = oid
        phone = re.sub(r"\D", "", str(raw_slots.get("phone") or ""))
        if re.fullmatch(r"1\d{10}", phone):
            slots["phone"] = phone

    need_clarify = bool(data.get("need_clarify", False))
    try:
        confidence = max(0.0, min(1.0, float(data.get("confidence", 0.0))))
    except (TypeError, ValueError):
        confidence = 0.0
    return intents, slots, need_clarify, confidence


# ── 各 Provider 调用（统一返回模型原始文本）──────────────────

async def _call_ollama(message: str, num_gpu: int | None) -> str:
    s = get_settings()
    options: dict = {"temperature": 0, "num_predict": 200}
    if num_gpu is not None:
        options["num_gpu"] = num_gpu          # 0 = 强制 CPU，避免与检索栈抢显存
    body = {
        "model": s.ollama_router_model,
        "stream": False,
        "keep_alive": "5m",                    # 常驻 5 分钟，避免每次重载
        "options": options,
        "messages": [
            {"role": "system", "content": "你是严格的 JSON 输出器，只输出一行 JSON。"},
            {"role": "user", "content": ROUTE_PROMPT.replace("{message}", message)},
        ],
    }
    async with httpx.AsyncClient(trust_env=False, timeout=s.router_timeout_seconds) as c:
        r = await c.post(f"{s.ollama_base_url}/api/chat", json=body)
        r.raise_for_status()
        return r.json()["message"]["content"]


async def _call_openai_compat(message: str, base_url: str, api_key: str, model: str) -> str:
    """OpenAI 兼容接口（百炼 / DeepSeek 共用）。"""
    s = get_settings()
    async with httpx.AsyncClient(trust_env=False, timeout=s.router_timeout_seconds) as c:
        r = await c.post(
            f"{base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "temperature": 0,
                "max_tokens": 200,
                "messages": [
                    {"role": "system", "content": "你是严格的 JSON 输出器，只输出一行 JSON。"},
                    {"role": "user", "content": ROUTE_PROMPT.replace("{message}", message)},
                ],
            },
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]


async def _call_dashscope(message: str) -> str:
    s = get_settings()
    if not s.dashscope_api_key:
        raise RuntimeError("DASHSCOPE_API_KEY 未配置")
    return await _call_openai_compat(message, s.dashscope_base_url, s.dashscope_api_key, s.qwen_router_model)


async def _call_deepseek(message: str) -> str:
    s = get_settings()
    if not s.deepseek_api_key:
        raise RuntimeError("DEEPSEEK_API_KEY 未配置")
    return await _call_openai_compat(message, s.deepseek_base_url, s.deepseek_api_key, s.deepseek_model_chat)


CALLERS = {
    "ollama_cpu": lambda m: _call_ollama(m, num_gpu=0),
    "ollama_gpu": lambda m: _call_ollama(m, num_gpu=None),
    "dashscope": _call_dashscope,
    "deepseek": _call_deepseek,
}

FALLBACK_CHAIN: dict[str, list[str]] = {
    "ollama_cpu": ["ollama_cpu", "dashscope", "deepseek"],
    "ollama_gpu": ["ollama_gpu", "dashscope", "deepseek"],
    "dashscope": ["dashscope", "deepseek"],
    "deepseek": ["deepseek"],
}


# ── 主入口 ─────────────────────────────────────────────────

async def route_ecom(message: str, provider: str | None = None, allow_fallback: bool = True) -> RouteResult:
    """电商意图路由：本地优先 → 云端回退；全部失败时返回人工兜底。

    allow_fallback=False 时只用指定 provider（评测用，避免回退掩盖单模型的真实表现）。
    """
    s = get_settings()
    name = provider or s.router_provider
    chain = (FALLBACK_CHAIN.get(name, FALLBACK_CHAIN["ollama_cpu"])
             if allow_fallback else [name])

    last_err: Exception | None = None
    for name in chain:
        t0 = time.perf_counter()
        try:
            raw = await CALLERS[name](message)
            intents, slots, need_clarify, confidence = normalize_route(parse_route_json(raw))
            latency_ms = int((time.perf_counter() - t0) * 1000)
            logger.info(
                "router.decision",
                provider=name, intents=",".join(intents), slots=json.dumps(slots, ensure_ascii=False),
                need_clarify=need_clarify, confidence=confidence, latency_ms=latency_ms,
            )
            return RouteResult(intents, slots, need_clarify, confidence, f"{name}", latency_ms, raw=raw)
        except Exception as e:                       # noqa: BLE001 —— 路由必须逐级降级，不向上抛
            last_err = e
            logger.warning("router.provider_failed", provider=name, error=str(e)[:200])

    logger.error("router.all_failed", error=str(last_err)[:300])
    return RouteResult(
        intents=["human"], slots={}, need_clarify=True, confidence=0.0,
        provider="fallback", latency_ms=0, raw="",
    )
