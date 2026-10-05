# scripts/bench_p6.py
# P6 实测数字采集：缓存省时 / 单意图短路 vs 多意图并行 / 售后工单统计
#
# 用法：python scripts/bench_p6.py
# 说明：数字以本机实测为准（CPU 推理），写进 P6 报告的是"跑多少写多少"。

import asyncio
import json
import sys
import time
import uuid

import asyncpg
import httpx

BASE = "http://localhost:8000"


def _login(c: httpx.Client, u: str, p: str) -> dict:
    r = c.post("/api/v1/auth/login", json={"username": u, "password": p})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def chat(h: dict, message: str) -> tuple[dict, str, float]:
    """发一条统一入口消息，返回 (meta, 答案文本, 耗时秒)。每条独立连接，避免连接复用干扰计时。"""
    events, text = [], []
    t0 = time.perf_counter()
    with httpx.Client(base_url=BASE, timeout=600, trust_env=False) as c:
        with c.stream("POST", "/api/v1/chat/stream",
                      json={"session_id": f"bench-{uuid.uuid4().hex[:8]}", "message": message},
                      headers=h) as s:
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
    elapsed = time.perf_counter() - t0
    meta = next((e for e in events if e["type"] == "meta"), {})
    return meta, "".join(text), elapsed


def main() -> int:
    with httpx.Client(base_url=BASE, timeout=600, trust_env=False) as c:
        h = _login(c, "student01@eduagent.local", "Student@123456")

        # ── 1) 路由缓存：同一问题两跑 ──
        q = "退货运费由谁承担呢？"
        print("== 1) 路由缓存（同问题两跑）==")
        m1, a1, d1 = chat(h, q)
        m2, a2, d2 = chat(h, q)
        print(f"  第1跑: provider={m1.get('provider')} mode={m1.get('mode')} "
              f"answer_modes={m1.get('answer_modes')} 答案{len(a1)}字 耗时={d1:.1f}s")
        print(f"  第2跑: provider={m2.get('provider')} 答案{len(a2)}字 耗时={d2:.1f}s"
              f"（缓存命中，省 {d1 - d2:.1f}s）")

        # ── 2) 单意图短路 vs 多意图并行 ──
        print("== 2) 单意图 vs 多意图 ==")
        m3, _, d3 = chat(h, "订单 A1023 现在什么状态？")
        print(f"  单意图: intents={m3.get('agents_used')} mode={m3.get('mode')} 耗时={d3:.1f}s")
        m4, _, d4 = chat(h, "查一下订单 A1024 的物流到哪了，另外耳机保修多久？")
        print(f"  多意图: intents={m4.get('agents_used')} mode={m4.get('mode')} "
              f"verified={m4.get('verified')} 耗时={d4:.1f}s")

    # ── 3) 售后工单统计（DB） ──
    print("== 3) 售后工单统计（DB）==")

    async def db_stats():
        from backend.config import get_settings
        s = get_settings()
        conn = await asyncpg.connect(
            f"postgresql://{s.db_user}:{s.db_password}@{s.db_host}:{s.db_port}/{s.db_name}")
        try:
            rows = await conn.fetch(
                "SELECT status, COUNT(*) AS n FROM after_sales_tickets GROUP BY status ORDER BY status")
            total = sum(int(r["n"]) for r in rows)
            by = {r["status"]: int(r["n"]) for r in rows}
            auto = by.get("auto_approved", 0)
            review = by.get("pending_review", 0) + by.get("approved", 0)
            denom = auto + review
            unresolved = await conn.fetchval(
                "SELECT COUNT(*) FROM unresolved_questions WHERE COALESCE(status,'pending') <> 'resolved'")
            return by, total, auto, review, denom, int(unresolved or 0)
        finally:
            await conn.close()

    by, total, auto, review, denom, unresolved = asyncio.run(db_stats())
    rate = (auto / denom * 100) if denom else 0
    print(f"  工单总数={total} 分布={by}")
    print(f"  自动通过率（auto/{auto}+审批路径{review}）= {rate:.1f}%")
    print(f"  待处理未解决问题={unresolved}")
    return 0


if __name__ == "__main__":
    sys.exit(main())