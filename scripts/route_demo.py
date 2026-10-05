# scripts/route_demo.py
# 用途：命令行体验/演示电商意图路由（P1 交付物）
# 用法：
#   python scripts/route_demo.py "耳机拆封了想退，订单A1024"
#   python scripts/route_demo.py "你好" "帮我查下订单A1002" --provider ollama_cpu
#   python scripts/route_demo.py -i          # 交互模式

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.core.router import INTENT_CN, route_ecom   # noqa: E402


async def run_one(text: str, provider: str | None) -> None:
    r = await route_ecom(text, provider=provider)
    cn = "、".join(INTENT_CN.get(i, i) for i in r.intents)
    print(f"\n输入    : {text}")
    print(f"  Provider : {r.provider}  ({r.latency_ms}ms)")
    print(f"  intents  : {r.intents}  （{cn}）")
    print(f"  slots    : {json.dumps(r.slots, ensure_ascii=False)}")
    print(f"  clarify  : {r.need_clarify}    confidence: {r.confidence}")


async def main() -> None:
    ap = argparse.ArgumentParser(description="电商意图路由演示")
    ap.add_argument("texts", nargs="*", help="要路由的一句话（可多条）")
    ap.add_argument("--provider", default=None,
                    help="ollama_cpu / ollama_gpu / dashscope / deepseek（默认读 .env 的 ROUTER_PROVIDER）")
    ap.add_argument("-i", "--interactive", action="store_true", help="交互模式")
    args = ap.parse_args()

    if args.interactive or not args.texts:
        print("交互模式（输入 q 退出）")
        while True:
            try:
                text = input("\n>>> ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if text.lower() in ("q", "quit", "exit"):
                break
            if text:
                await run_one(text, args.provider)
    else:
        for t in args.texts:
            await run_one(t, args.provider)


if __name__ == "__main__":
    asyncio.run(main())
