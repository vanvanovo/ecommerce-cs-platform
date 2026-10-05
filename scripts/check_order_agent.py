# scripts/check_order_agent.py
# P3 验收：订单/物流 Agent HTTP 接口（4 个场景 + 多轮补槽位）
# 前置：后端已启动（uvicorn backend.main:app :8000）
# 执行：python scripts/check_order_agent.py

import asyncio
import json
import time

import httpx

BASE = "http://localhost:8000"


async def main() -> None:
    ok = 0
    total = 0

    def check(cond: bool, name: str) -> None:
        nonlocal ok, total
        total += 1
        if cond:
            ok += 1
            print(f"  ✓ {name}")
        else:
            print(f"  ✗ {name}")

    async with httpx.AsyncClient(base_url=BASE, timeout=180, trust_env=False) as c:
        r = await c.post("/api/v1/auth/login",
                         json={"username": "student01@eduagent.local", "password": "Student@123456"})
        h = {"Authorization": f"Bearer {r.json()['access_token']}"}
        run = time.strftime("%m%d%H%M%S")

        async def chat(session: str, msg: str) -> dict:
            r = await c.post("/api/v1/order/chat",
                             json={"session_id": session, "message": msg}, headers=h)
            print(f"\n>>> [{session}] {msg}")
            print("    HTTP", r.status_code, "|", json.dumps(r.json(), ensure_ascii=False)[:360])
            return r.json()

        # 1) 直接带订单号 + 物流关键词
        r1 = await chat(f"p3-{run}-1", "订单A1024到哪了？")
        check(r1.get("order_id") == "A1024" and r1.get("structured_output", {}).get("status") == "delivered",
              "A1024：识别单号 + 返回已签收状态")
        check(not r1.get("need_clarify") and not r1.get("need_human"), "A1024：正常直答")

        # 2) 缺槽位 → 追问 → 补单号（同一 session 多轮）
        r2a = await chat(f"p3-{run}-2", "帮我查一下订单")
        check(r2a.get("need_clarify") is True, "缺槽位：触发追问")
        r2b = await chat(f"p3-{run}-2", "A1026")
        check(r2b.get("order_id") == "A1026" and not r2b.get("need_clarify"),
              "补充单号后：正常查询（多轮记忆生效）")

        # 3) 手机号命中多单 → 列出候选
        r3 = await chat(f"p3-{run}-3", "13800000001 我的订单")
        check(r3.get("need_clarify") is True and "多个订单" in (r3.get("clarify_question") or ""),
              "手机号多单：列出候选并请用户指定")

        # 4) 不存在的订单
        r4 = await chat(f"p3-{run}-4", "订单A9999到哪了？")
        check("没有查询到" in (r4.get("answer") or ""), "不存在订单：友好提示")

        print(f"\n{'='*46}")
        print(f"订单 Agent 验收：通过 {ok} / {total}")
        print(f"{'='*46}")


if __name__ == "__main__":
    asyncio.run(main())
