# scripts/check_rag_a2a.py
# P5 验收：A2A 独立 RAG 知识库 Agent
#
# 用法：
#   python scripts/check_rag_a2a.py direct          # 直连 A2A Agent（检索结果）
#   python scripts/check_rag_a2a.py chat rag        # 平台统一入口（RAG_VIA_A2A=true，期望 rag + 来源）
#   python scripts/check_rag_a2a.py chat llm_direct # RAG Agent 已停止（期望降级、不 500）
#
# 退出码：0 通过 / 1 失败

import asyncio
import json
import sys
import time

import httpx

BASE = "http://localhost:8000"
QUERY = "耳机保修多久？"          # 商品咨询（P4 实测稳定路由到 product）


def run_direct() -> int:
    from backend.core.a2a_client import call_rag_agent

    res = asyncio.run(call_rag_agent(QUERY))
    brief = {k: res.get(k) for k in ("mode", "confidence", "is_high_confidence")}
    print(f"  A2A 直连：{json.dumps(brief, ensure_ascii=False)}")
    docs = res.get("docs") or []
    print(f"  docs={len(docs)} | 首个来源：{docs[0].get('source_name', '') if docs else '（无）'}")
    ok = len(docs) >= 1 and res.get("confidence", 0) >= 0.75
    print("  ✓ A2A 直连检索正常（带来源）" if ok else "  ✗ A2A 直连检索异常")
    return 0 if ok else 1


def run_chat(expect: str) -> int:
    with httpx.Client(base_url=BASE, timeout=300, trust_env=False) as c:
        r = c.post("/api/v1/auth/login",
                   json={"username": "student01@eduagent.local", "password": "Student@123456"})
        h = {"Authorization": f"Bearer {r.json()['access_token']}"}

        events, text = [], []
        with c.stream("POST", "/api/v1/chat/stream",
                      json={"session_id": f"p5-{time.strftime('%m%d%H%M%S')}", "message": QUERY},
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

    meta = next((e for e in events if e["type"] == "meta"), {})
    modes = meta.get("answer_modes") or {}
    sources = meta.get("sources") or []
    actual = modes.get("product")
    print(f"  mode={meta.get('mode')} | answer_modes={modes} | sources={sources[:1]}")
    print(f"  answer: {''.join(text)[:90]}…")
    ok = actual == expect and (expect != "rag" or len(sources) >= 1)
    print(f"  {'✓' if ok else '✗'} 期望 product={expect}，实际={actual}；sources={len(sources)} 条")
    return 0 if ok else 1


if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else "chat"
    if action == "direct":
        sys.exit(run_direct())
    expect = sys.argv[2] if len(sys.argv) > 2 else "rag"
    sys.exit(run_chat(expect))
