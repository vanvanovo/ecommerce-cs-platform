# scripts/check_aftersale_agent.py
# P3 验收：售后/退款 Agent（自动通过 / 主管审批通过 / 未签收拒绝 / 主管驳回）
# 前置：后端已启动（uvicorn backend.main:app :8000）
# 执行：python scripts/check_aftersale_agent.py

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
        r_s = await c.post("/api/v1/auth/login",
                           json={"username": "student01@eduagent.local", "password": "Student@123456"})
        hs = {"Authorization": f"Bearer {r_s.json()['access_token']}"}
        r_t = await c.post("/api/v1/auth/login",
                           json={"username": "teacher01@eduagent.local", "password": "Teacher@123456"})
        ht = {"Authorization": f"Bearer {r_t.json()['access_token']}"}
        run = time.strftime("%m%d%H%M%S")

        async def submit(session: str, msg: str) -> dict:
            r = await c.post("/api/v1/aftersale/submit",
                             json={"session_id": session, "message": msg}, headers=hs)
            print(f"\n>>> 用户提交 [{session}] {msg}")
            print("    HTTP", r.status_code, "|", json.dumps(r.json(), ensure_ascii=False)[:300])
            return r.json()

        # 1) 自动通过：A1026（129 元 / 未拆封 / 1 天前签收）
        r1 = await submit(f"p3-af-{run}-1", "订单A1026我要退款")
        check(r1.get("ticket_status") == "auto_approved" and r1.get("ticket_id"),
              f"自动通过并建单（{r1.get('ticket_id')}）")

        # 2) HitL 通过：A1024（699 元 / 已拆封耳机 → quality_path）
        r2 = await submit(f"p3-af-{run}-2", "订单A1024耳机拆封了想退")
        check(r2.get("status") == "pending_review" and bool(r2.get("review_id")),
              f"转主管审批（{r2.get('review_id')}）")

        # 2a) 普通用户无权查看审批
        g0 = await c.get(f"/api/v1/aftersale/review/{r2['review_id']}", headers=hs)
        check(g0.status_code == 403, "普通用户访问审批详情 → 403")

        # 2b) 主管查看审批详情
        g1 = await c.get(f"/api/v1/aftersale/review/{r2['review_id']}", headers=ht)
        payload = (g1.json() or {}).get("payload", {})
        print("    主管看到审批材料:", json.dumps(payload, ensure_ascii=False)[:220])
        check(g1.status_code == 200 and payload.get("order_id") == "A1024",
              "主管可查看审批材料（含规则审核结果）")

        # 2c) 主管审批通过 → 工单落定 approved
        c1 = await c.post(f"/api/v1/aftersale/confirm/{r2['review_id']}",
                          json={"action": "approve", "comment": "同意退货，请按指引领取退货面单"}, headers=ht)
        j1 = c1.json()
        print("    审批结果:", json.dumps(j1, ensure_ascii=False)[:260])
        check(c1.status_code == 200 and j1.get("ticket_status") == "approved" and j1.get("ticket_id"),
              f"主管通过 → 工单 approved（{j1.get('ticket_id')}）")

        # 2d) 重复审批 → 404（审批单已处理）
        c1b = await c.post(f"/api/v1/aftersale/confirm/{r2['review_id']}",
                           json={"action": "approve"}, headers=ht)
        check(c1b.status_code == 404, "重复审批已处理的单 → 404")

        # 3) 规则拒绝：A1049 未签收（paid）
        r3 = await submit(f"p3-af-{run}-3", "订单A1049我要退货")
        check(r3.get("status") == "rejected" or "未签收" in (r3.get("answer") or ""),
              "未签收订单 → 拒绝并说明原因")

        # 4) HitL 驳回：A1004（1757 元 → 必进审批）
        r4 = await submit(f"p3-af-{run}-4", "订单A1004我要退款")
        check(r4.get("status") == "pending_review" and bool(r4.get("review_id")),
              "大额订单 → 转主管审批")
        c2 = await c.post(f"/api/v1/aftersale/confirm/{r4['review_id']}",
                          json={"action": "reject", "comment": "商品已使用，不符合退货条件"}, headers=ht)
        j2 = c2.json()
        print("    驳回结果:", json.dumps(j2, ensure_ascii=False)[:220])
        check(c2.status_code == 200 and "未通过主管审核" in (j2.get("answer") or ""),
              "主管驳回 → 用户收到驳回说明")

        # 5) 物流异常：显示签收但未收到 → 转人工核实（不直接走退款规则）
        r5 = await submit(f"p3-af-{run}-5", "订单A1024显示签收了但我没收到，我要退款")
        print("    交接摘要:", (r5.get("handoff_summary") or "")[:150].replace("\n", " / "))
        check(r5.get("need_human") is True and "物流异常" in (r5.get("answer") or ""),
              "签收未收到 → 物流异常转人工")
        check(r5.get("structured_output", {}).get("action") == "logistics_anomaly",
              "结构化输出标记 logistics_anomaly")

        print(f"\n{'='*46}")
        print(f"售后 Agent 验收：通过 {ok} / {total}")
        print(f"{'='*46}")


if __name__ == "__main__":
    asyncio.run(main())
