# scripts/check_unified_p4.py
# P4 验收：统一入口（规则前置 / 短路直出 / 多意图并行汇总 / 转人工 / 投诉升级）
# 前置：后端已启动（uvicorn backend.main:app :8000）
# 执行：python scripts/check_unified_p4.py

import json
import time

import httpx

BASE = "http://localhost:8000"


def main() -> None:
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

    with httpx.Client(base_url=BASE, timeout=300, trust_env=False) as c:
        r = c.post("/api/v1/auth/login",
                   json={"username": "student01@eduagent.local", "password": "Student@123456"})
        h = {"Authorization": f"Bearer {r.json()['access_token']}"}
        run = time.strftime("%m%d%H%M%S")

        def chat(session: str, msg: str) -> dict:
            """跑一次 SSE，收集事件与文本。"""
            events, text = [], []
            with c.stream("POST", "/api/v1/chat/stream",
                          json={"session_id": session, "message": msg}, headers=h) as s:
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
            return {"events": events, "text": "".join(text)}

        # 1) 规则前置：问候零 Token
        r1 = chat(f"p4-{run}-1", "你好")
        types1 = [e["type"] for e in r1["events"]]
        check("routing_decision" not in types1 and "token" in types1 and r1["text"],
              "问候 → 规则前置模板直答（未调路由）")

        # 2) 短路直出：单意图高置信
        r2 = chat(f"p4-{run}-2", "耳机保修多久？")
        meta2 = next((e for e in r2["events"] if e["type"] == "meta"), {})
        rd2 = next((e for e in r2["events"] if e["type"] == "routing_decision"), {})
        print(f"    [短路] intents={rd2.get('intents')} mode={meta2.get('mode')} "
              f"elapsed={meta2.get('elapsed_ms')}ms text={r2['text'][:60]}…")
        check(meta2.get("mode") == "short_circuit" and meta2.get("agents_used") == ["product"],
              "单意图高置信 → 短路直出（跳过汇总）")

        # 3) 多意图并行 + 汇总
        r3 = chat(f"p4-{run}-3", "我的订单A1024到哪了，另外耳机拆封了能退吗？")
        meta3 = next((e for e in r3["events"] if e["type"] == "meta"), {})
        rd3 = next((e for e in r3["events"] if e["type"] == "routing_decision"), {})
        print(f"    [并行] intents={rd3.get('intents')} agents={meta3.get('agents_used')} "
              f"verified={meta3.get('verified')} elapsed={meta3.get('elapsed_ms')}ms")
        print(f"    汇总文本: {r3['text'][:140]}…")
        has_logistics = any(k in r3["text"] for k in ("物流", "快递", "签收", "派送"))
        has_aftersale = "退" in r3["text"]
        check(meta3.get("mode") == "parallel" and len(meta3.get("agents_used") or []) >= 2,
              "多意图 → 并行执行（≥2 Agent）")
        check(has_logistics and has_aftersale and meta3.get("verified") is True,
              "汇总覆盖两个诉求且一致性校验通过")

        # 4) 转人工直达
        r4 = chat(f"p4-{run}-4", "转人工")
        types4 = [e["type"] for e in r4["events"]]
        meta4 = next((e for e in r4["events"] if e["type"] == "meta"), {})
        handoff4 = next((e for e in r4["events"] if e["type"] == "handoff"), None)
        check("handoff" in types4 and meta4.get("mode") == "human" and bool(handoff4),
              "转人工 → 直达人工分支（交接摘要 + handoff 事件）")

        # 5) 投诉升级 → 交接（Agent 内部升级）
        r5 = chat(f"p4-{run}-5", "订单A1024一直没人处理，我要去12315投诉！")
        rd5 = next((e for e in r5["events"] if e["type"] == "routing_decision"), {})
        handoff5 = next((e for e in r5["events"] if e["type"] == "handoff"), None)
        print(f"    [投诉] intents={rd5.get('intents')} handoff={'有' if handoff5 else '无'}")
        check("complaint" in (rd5.get("intents") or []) and bool(handoff5),
              "投诉 → complaint Agent → 交接事件")

        print(f"\n{'='*46}")
        print(f"P4 统一入口验收：通过 {ok} / {total}")
        print(f"{'='*46}")


if __name__ == "__main__":
    main()
