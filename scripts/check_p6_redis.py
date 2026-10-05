# scripts/check_p6_redis.py
# P6 验收：Redis（缓存 / 写锁 / 监控指标）
#
# 用法（先 FLUSHDB 清空计数，再按顺序跑）：
#   python scripts/check_p6_redis.py route      # 路由决策缓存（同问题两跑）
#   python scripts/check_p6_redis.py rag        # A2A 知识库检索缓存（省 CPU 检索时间）
#   python scripts/check_p6_redis.py logistics  # 物流轨迹 5 分钟缓存
#   python scripts/check_p6_redis.py lock       # 写操作分布式锁（持锁 → busy；释放 → 正常）
#   python scripts/check_p6_redis.py metrics    # 监控指标接口
#
# 退出码：0 通过 / 1 失败

import asyncio
import json
import sys
import time
import uuid

import httpx

BASE = "http://localhost:8000"
ROUTE_MSG = "耳机保修多久？"


def _login(c: httpx.Client) -> dict:
    r = c.post("/api/v1/auth/login",
               json={"username": "student01@eduagent.local", "password": "Student@123456"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _chat_once(c: httpx.Client, h: dict, message: str, session_id: str) -> tuple[dict, str]:
    events, text = [], []
    with c.stream("POST", "/api/v1/chat/stream",
                  json={"session_id": session_id, "message": message}, headers=h) as s:
        for line in s.iter_lines():
            if not line or not line.startswith("data: "):
                continue
            try:
                ev = json.loads(line[6:])
            except Exception:
                continue
            events.append(ev)
            if ev.get("type") == "token":
                text.append(ev.get("content", ""))
    meta = next((e for e in events if e["type"] == "meta"), {})
    return meta, "".join(text)


def check_route() -> int:
    """同一问题连跑两次：首跑 miss（真实路由），重跑 hit（Redis，省时）。"""
    with httpx.Client(base_url=BASE, timeout=300, trust_env=False) as c:
        h = _login(c)
        t1 = time.perf_counter()
        m1, _ = _chat_once(c, h, ROUTE_MSG, f"p6-route-a-{uuid.uuid4().hex[:6]}")
        d1 = time.perf_counter() - t1
        t2 = time.perf_counter()
        m2, _ = _chat_once(c, h, ROUTE_MSG, f"p6-route-b-{uuid.uuid4().hex[:6]}")
        d2 = time.perf_counter() - t2

    ok = m1.get("provider") != "cache" and m2.get("provider") == "cache"
    print(f"  第1次: provider={m1.get('provider')} elapsed={d1:.1f}s")
    print(f"  第2次: provider={m2.get('provider')} elapsed={d2:.1f}s（路由缓存命中）")
    print(f"  {'✓' if ok else '✗'} 路由缓存：miss → hit（省时 {d1 - d2:.1f}s）")
    return 0 if ok else 1


def check_rag() -> int:
    """A2A 直连两次：首跑走 MCP 知识库（~8s CPU 检索），重跑 Redis 直出。"""
    from backend.core.a2a_client import call_rag_agent

    async def run():
        t1 = time.perf_counter()
        r1 = await call_rag_agent(ROUTE_MSG)
        d1 = time.perf_counter() - t1
        t2 = time.perf_counter()
        r2 = await call_rag_agent(ROUTE_MSG)
        d2 = time.perf_counter() - t2
        return r1, d1, r2, d2

    r1, d1, r2, d2 = asyncio.run(run())
    ok = (not r1.get("cached")) and bool(r2.get("cached")) and d2 < d1 * 0.5
    print(f"  第1次: {d1:.1f}s cached={bool(r1.get('cached'))} conf={r1.get('confidence'):.3f}")
    print(f"  第2次: {d2:.1f}s cached={bool(r2.get('cached'))}（Redis 命中，省时 {d1 - d2:.1f}s）")
    print(f"  {'✓' if ok else '✗'} RAG 检索缓存")
    return 0 if ok else 1


def check_logistics() -> int:
    """物流轨迹连查两次：第二次 cached=true 且内容一致。"""
    from backend.agents.common import call_cs_tool

    async def run():
        r1 = await call_cs_tool("track_logistics", {"order_id": "A1001"})
        r2 = await call_cs_tool("track_logistics", {"order_id": "A1001"})
        return r1, r2

    r1, r2 = asyncio.run(run())
    d1 = r1.get("data") or {}
    d2 = r2.get("data") or {}
    ok = (not d1.get("cached")) and bool(d2.get("cached")) and d1.get("tracks") == d2.get("tracks")
    print(f"  第1次: status={r1.get('status')} cached={bool(d1.get('cached'))} "
          f"tracks={len(d1.get('tracks') or [])}")
    print(f"  第2次: status={r2.get('status')} cached={bool(d2.get('cached'))}")
    print(f"  {'✓' if ok else '✗'} 物流 5 分钟缓存（内容一致）")
    return 0 if ok else 1


def check_lock() -> int:
    """写锁：外部持锁时工具等待 ~2s 返回 busy；释放后正常创建。"""
    from backend.agents.common import call_cs_tool
    from backend.core.cache import redis_lock

    async def run():
        async with redis_lock("ticket:A1001", ttl=5, wait=1.0):
            held = await call_cs_tool("create_return_ticket", {
                "order_id": "A1001", "reason": "写锁验证（持锁）",
                "idempotency_key": f"lock-held-{uuid.uuid4().hex[:8]}",
            })
        free = await call_cs_tool("create_return_ticket", {
            "order_id": "A1001", "reason": "写锁验证（释放后）",
            "idempotency_key": f"lock-free-{uuid.uuid4().hex[:8]}",
        })
        return held, free

    held, free = asyncio.run(run())
    ok = held.get("status") == "busy" and free.get("status") in ("success", "rejected", "duplicate")
    print(f"  持锁时: status={held.get('status')}（期望 busy）")
    print(f"  释放后: status={free.get('status')} "
          f"ticket={(free.get('data') or {}).get('ticket_id', '-')}")
    print(f"  {'✓' if ok else '✗'} 写锁串行化 + busy 降级")
    return 0 if ok else 1


def check_metrics() -> int:
    with httpx.Client(base_url=BASE, timeout=60, trust_env=False) as c:
        h = _login(c)
        r = c.get("/api/v1/chat/metrics", headers=h)
    metrics = r.json().get("metrics", {})
    print("  指标: " + json.dumps(metrics, ensure_ascii=False))
    need = ["route_cache_hit", "short_circuit_total", "tool_call_total"]
    ok = all(k in metrics for k in need)
    print(f"  {'✓' if ok else '✗'} 监控指标接口（{len(metrics)} 项）")
    return 0 if ok else 1


if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else "route"
    fn = {"route": check_route, "rag": check_rag, "logistics": check_logistics,
          "lock": check_lock, "metrics": check_metrics}.get(action)
    if fn is None:
        print(f"未知动作：{action}")
        sys.exit(2)
    sys.exit(fn())
