# scripts/check_complaint_agent.py
# P3 验收：投诉/转人工 Agent（高危升级 / 带订单升级 / 一般安抚）
# 执行：python scripts/check_complaint_agent.py

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
            r = await c.post("/api/v1/complaint/chat",
                             json={"session_id": session, "message": msg}, headers=h)
            print(f"\n>>> [{session}] {msg}")
            print("    HTTP", r.status_code, "|", json.dumps(r.json(), ensure_ascii=False)[:320])
            return r.json()

        # 1) 高危词（12315）→ 升级转人工
        r1 = await chat(f"p3-cp-{run}-1", "你们服务太差了，再不解决我就去12315投诉！")
        check(r1.get("risk_level") == "high" and r1.get("need_human") is True,
              "高危词 → high + 转人工")
        check("人工" in (r1.get("answer") or ""), "安抚话术包含转人工说明")

        # 2) 带订单号的高危投诉 → 交接包附带订单状态
        r2 = await chat(f"p3-cp-{run}-2", "订单A1024拖到现在没人处理，我要曝光你们")
        summary = r2.get("handoff_summary") or ""
        check(r2.get("need_human") is True and "A1024" in summary,
              "交接包含订单号")
        check(r2.get("structured_output", {}).get("order", {}).get("status") == "delivered",
              "交接包附带订单状态（delivered）")

        # 3) 一般不满（单个负面词）→ 安抚解决，不转人工
        r3 = await chat(f"p3-cp-{run}-3", "这个快递有点太慢了，能帮我看看吗")
        check(r3.get("risk_level") in ("normal", "low") and r3.get("need_human") is False,
              "一般不满 → 安抚解决，不转人工")

        print(f"\n{'='*46}")
        print(f"投诉 Agent 验收：通过 {ok} / {total}")
        print(f"{'='*46}")


if __name__ == "__main__":
    asyncio.run(main())
