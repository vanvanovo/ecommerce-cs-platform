# scripts/eval_intent.py
# 电商意图路由评测：对候选 Provider 跑评测集，输出指标 + badcase + Markdown 报告
# 执行示例：
#   python scripts/eval_intent.py --providers ollama_cpu --limit 60
#   python scripts/eval_intent.py --providers ollama_cpu,ollama_gpu,deepseek
#   python scripts/eval_intent.py --providers ollama_cpu --out docs/p1_intent_eval_report.md

import argparse
import asyncio
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.core.router import INTENTS, RouteResult, route_ecom   # noqa: E402

DATA = Path(__file__).resolve().parents[1] / "backend" / "core" / "data" / "ecom_intent_eval.jsonl"


def load_items(limit: int | None) -> list[dict]:
    items = [json.loads(line) for line in DATA.read_text(encoding="utf-8").splitlines() if line.strip()]
    if limit and limit < len(items):
        # 按类目分层抽样，保持四类比例
        buckets: dict[str, list[dict]] = defaultdict(list)
        for it in items:
            buckets[it["category"]].append(it)
        rng = random.Random(11)
        picked = []
        for cat, bucket in buckets.items():
            k = max(1, round(limit * len(bucket) / len(items)))
            picked += rng.sample(bucket, min(k, len(bucket)))
        items = picked[:limit]
    return items


async def eval_provider(items: list[dict], provider: str) -> list[tuple[dict, object]]:
    results = []
    for i, it in enumerate(items, 1):
        r = await route_ecom(it["text"], provider=provider, allow_fallback=False)
        if r.provider == "fallback":     # 该 provider 完全失败：记为无效，而非误判成 human
            r = RouteResult(intents=[], slots={}, need_clarify=True, confidence=0.0,
                            provider="fallback", latency_ms=r.latency_ms)
        results.append((it, r))
        if i % 20 == 0:
            print(f"    [{provider}] {i}/{len(items)} …")
    return results


def compute_metrics(results: list[tuple[dict, object]]) -> dict:
    n = len(results)
    valid = sum(1 for _, r in results if r.intents)
    exact = sum(1 for it, r in results if sorted(r.intents) == sorted(it["intents"]))
    clar = sum(1 for it, r in results if r.need_clarify == it["need_clarify"])

    slot_hit = slot_total = 0
    false_slot = false_slot_total = 0
    for it, r in results:
        gold = it["slots"].get("order_id")
        pred = r.slots.get("order_id")
        if gold:
            slot_total += 1
            slot_hit += int(pred == gold)
        else:
            false_slot_total += 1
            false_slot += int(pred is not None)

    lats = sorted(r.latency_ms for _, r in results)
    p50 = lats[len(lats) // 2] if lats else 0
    p95 = lats[min(len(lats) - 1, int(len(lats) * 0.95))] if lats else 0

    per_label = {}
    for lab in INTENTS:
        tp = sum(1 for it, r in results if lab in it["intents"] and lab in r.intents)
        fp = sum(1 for it, r in results if lab not in it["intents"] and lab in r.intents)
        fn = sum(1 for it, r in results if lab in it["intents"] and lab not in r.intents)
        prec = tp / (tp + fp) if tp + fp else 1.0
        rec = tp / (tp + fn) if tp + fn else 1.0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
        per_label[lab] = {"tp": tp, "fp": fp, "fn": fn, "p": prec, "r": rec, "f1": f1}

    cat = defaultdict(lambda: [0, 0])
    for it, r in results:
        cat[it["category"]][1] += 1
        if sorted(r.intents) == sorted(it["intents"]):
            cat[it["category"]][0] += 1

    badcases = [
        (it, r) for it, r in results
        if sorted(r.intents) != sorted(it["intents"]) or r.need_clarify != it["need_clarify"]
    ][:15]

    return {
        "n": n, "valid": valid, "exact": exact, "clar": clar,
        "slot_hit": slot_hit, "slot_total": slot_total,
        "false_slot": false_slot, "false_slot_total": false_slot_total,
        "p50": p50, "p95": p95, "per_label": per_label,
        "by_cat": dict(cat), "badcases": badcases,
        "providers_used": Counter(r.provider for _, r in results),
    }


def fmt_pct(a: int, b: int) -> str:
    return f"{a / b * 100:.1f}%" if b else "-"


def build_report(all_metrics: dict[str, dict], providers: list[str], total_items: int) -> str:
    lines = ["# P1 意图路由评测报告", "",
             f"> 评测集：`backend/core/data/ecom_intent_eval.jsonl`（共 {total_items} 条；"
             f"本次 {all_metrics[providers[0]]['n']} 条分层抽样）",
             f"> Provider：{' / '.join(providers)}", ""]

    lines += ["## 总览", "",
              "| Provider | JSON 有效 | 意图完全匹配 | 追问判断 | 订单号槽位 | 误抽槽位 | P50 | P95 |",
              "|---|---|---|---|---|---|---|---|"]
    for p in providers:
        m = all_metrics[p]
        lines.append(
            f"| {p} | {fmt_pct(m['valid'], m['n'])} | **{fmt_pct(m['exact'], m['n'])}** | "
            f"{fmt_pct(m['clar'], m['n'])} | {fmt_pct(m['slot_hit'], m['slot_total'])} | "
            f"{fmt_pct(m['false_slot'], m['false_slot_total'])} | {m['p50']}ms | {m['p95']}ms |"
        )
    lines.append("")

    lines += ["## 分类别准确率", "", "| Provider | 正常 | 模糊 | 越界 | 多意图 |", "|---|---|---|---|---|"]
    for p in providers:
        c = all_metrics[p]["by_cat"]
        cells = []
        for cat in ["normal", "vague", "out_of_scope", "multi"]:
            hit, tot = c.get(cat, [0, 0])
            cells.append(fmt_pct(hit, tot))
        lines.append(f"| {p} | " + " | ".join(cells) + " |")
    lines.append("")

    lines += ["## 单标签指标（F1 / 准 / 召）", "", "| 意图 | " + " | ".join(providers) + " |",
              "|---|" + "---|" * len(providers)]
    for lab in INTENTS:
        row = [lab]
        for p in providers:
            d = all_metrics[p]["per_label"].get(lab, {"f1": 0, "p": 0, "r": 0})
            row.append(f"{d['f1']:.2f} ({d['p']:.2f}/{d['r']:.2f})")
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")

    for p in providers:
        m = all_metrics[p]
        lines += [f"## {p} · Badcase（前 {len(m['badcases'])} 条）", "",
                  "| 文本 | 期望 | 实际 | 追问(期望/实际) |", "|---|---|---|---|"]
        for it, r in m["badcases"]:
            lines.append(f"| {it['text']} | {'+'.join(it['intents'])} | {'+'.join(r.intents) or '∅'} | "
                         f"{it['need_clarify']}/{r.need_clarify} |")
        lines.append("")
    return "\n".join(lines)


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--providers", default="ollama_cpu", help="逗号分隔：ollama_cpu,ollama_gpu,dashscope,deepseek")
    ap.add_argument("--limit", type=int, default=None, help="分层抽样条数（默认全量）")
    ap.add_argument("--out", default="docs/p1_intent_eval_report.md", help="报告输出路径")
    args = ap.parse_args()

    providers = [p.strip() for p in args.providers.split(",") if p.strip()]
    items = load_items(args.limit)
    print(f"评测集：共 {len(items)} 条 | Providers: {providers}\n")

    all_metrics: dict[str, dict] = {}
    for p in providers:
        print(f"===== 评测 {p} =====")
        results = await eval_provider(items, p)
        all_metrics[p] = compute_metrics(results)
        m = all_metrics[p]
        print(f"  完成：完全匹配 {fmt_pct(m['exact'], m['n'])} | 槽位 {fmt_pct(m['slot_hit'], m['slot_total'])} "
              f"| P50 {m['p50']}ms / P95 {m['p95']}ms\n")

    report = build_report(all_metrics, providers, len(items))
    out = Path(__file__).resolve().parents[1] / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8")
    print(f"📄 报告已写入：{out}")


if __name__ == "__main__":
    asyncio.run(main())
