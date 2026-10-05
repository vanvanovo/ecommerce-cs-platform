# backend/mcp/check_cs_client.py
# P2 验收脚本：列出客服订单 MCP 的全部工具并逐一调用验证
# 执行：python backend/mcp/check_cs_client.py
#
# 注意：通用 client（backend/mcp/client.py）的返回约定——
#   工具返回单个对象时会被包成 [item]；返回列表时直接是列表。
#   本脚本用 one() 兼容这一约定。

import asyncio
import json
import time

import httpx

from backend.config import get_settings
from backend.mcp.client import call_mcp_tool, list_mcp_tools

# 每次运行使用独立幂等键，保证脚本可重复执行
RUN = time.strftime("%m%d%H%M%S")
KEY_TICKET_A = f"p2-check-{RUN}-A1024"
KEY_TICKET_B = f"p2-check-{RUN}-A1026"
KEY_COMP = f"p2-check-{RUN}-comp"


def one(res):
    """兼容 client.py：单条结果被包成 [item] 时取出内层对象。"""
    if isinstance(res, list) and len(res) == 1 and isinstance(res[0], dict):
        return res[0]
    return res


def show(title: str, res) -> None:
    print(f"\n--- {title} ---")
    text = json.dumps(res, ensure_ascii=False, indent=2)
    print(text[:800] + ("…" if len(text) > 800 else ""))


async def main() -> None:
    base = get_settings().cs_mcp_url
    print(f"MCP Server: {base} | 数据源: {get_settings().order_backend}")

    tools = await list_mcp_tools(base)
    names = [t["name"] for t in tools]
    print(f"\n工具数：{len(tools)}")
    print(f"工具清单：{names}")

    ok, fail = 0, 0

    def check(cond: bool, name: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1
            print(f"  ✓ {name}")
        else:
            fail += 1
            print(f"  ✗ {name}")

    # 1) get_order —— 演示订单 A1024（699 / 已拆封）
    r = one(await call_mcp_tool(base, "get_order", {"order_id": "A1024"}))
    show("get_order(A1024)", r)
    check(r.get("status") == "success" and r["data"]["items"][0]["opened"] is True,
          "get_order 返回结构化明细且拆封标记正确")

    # 2) track_logistics
    r = one(await call_mcp_tool(base, "track_logistics", {"order_id": "A1024"}))
    show("track_logistics(A1024)", r)
    check(r.get("status") == "success" and len(r["data"]["tracks"]) >= 3, "物流轨迹返回完整节点")

    # 3) list_orders
    r = one(await call_mcp_tool(base, "list_orders", {"phone": "13800000001", "limit": 3}))
    show("list_orders(13800000001)", r)
    check(r.get("status") == "success" and r["data"]["count"] >= 1, "按手机号查订单列表")

    # 4) query_inventory
    r = one(await call_mcp_tool(base, "query_inventory", {"sku": "SKU-1001"}))
    show("query_inventory(SKU-1001)", r)
    check(r.get("status") == "success" and r["data"].get("unopened_required") is True,
          "商品库存与售后属性")

    # 5) check_return_eligibility —— A1024：699 + 已拆封 → 转保修/人工
    r = one(await call_mcp_tool(base, "check_return_eligibility", {"order_id": "A1024"}))
    show("check_return_eligibility(A1024)", r)
    check(r.get("status") == "success" and r["data"]["next_step"] == "quality_path",
          "拆封耳机 → quality_path（不支持无理由）")

    # 6) check_return_eligibility —— A1026：129 未拆封 → 自动通过
    r = one(await call_mcp_tool(base, "check_return_eligibility", {"order_id": "A1026"}))
    show("check_return_eligibility(A1026)", r)
    check(r.get("status") == "success" and r["data"]["next_step"] == "auto_approve",
          "129 未拆封 → auto_approve")

    # 7) create_return_ticket —— A1024 → pending_review
    r1 = one(await call_mcp_tool(base, "create_return_ticket", {
        "order_id": "A1024", "ticket_type": "return",
        "reason": "耳机拆封想退（P2 验收）", "idempotency_key": KEY_TICKET_A,
    }))
    show("create_return_ticket(A1024) 第一次", r1)
    check(r1.get("status") == "success" and r1["data"]["status"] == "pending_review",
          "创建工单并转待审批")

    # 8) 幂等复放
    r2 = one(await call_mcp_tool(base, "create_return_ticket", {
        "order_id": "A1024", "ticket_type": "return",
        "reason": "耳机拆封想退（P2 验收）", "idempotency_key": KEY_TICKET_A,
    }))
    show("create_return_ticket(A1024) 幂等复放", r2)
    check(r2.get("status") == "duplicate", "同一幂等键返回 duplicate")

    # 8.5) review_ticket：主管审批这张待审工单（P3 追加工具）
    r2b = one(await call_mcp_tool(base, "review_ticket", {
        "ticket_id": r1["data"]["ticket_id"], "decision": "approve",
        "reviewer": "p2-check", "comment": "验收：同意退货",
    }))
    show("review_ticket(审批通过)", r2b)
    check(r2b.get("status") == "success" and r2b["data"]["status"] == "approved",
          "review_ticket：审批通过 → approved")

    # 9) create_return_ticket —— A1026 自动通过
    r3 = one(await call_mcp_tool(base, "create_return_ticket", {
        "order_id": "A1026", "ticket_type": "refund",
        "reason": "不想要了（P2 验收）", "idempotency_key": KEY_TICKET_B,
    }))
    show("create_return_ticket(A1026) 自动通过", r3)
    check(r3.get("status") == "success" and r3["data"]["status"] == "auto_approved",
          "未拆封小额自动通过")

    # 10) create_compensation —— A1049 超时未发货
    r4 = one(await call_mcp_tool(base, "create_compensation", {
        "order_id": "A1049", "amount": 5, "reason": "超时未发货补偿（P2 验收）",
        "idempotency_key": KEY_COMP,
    }))
    show("create_compensation(A1049)", r4)
    check(r4.get("status") == "success" and r4["data"]["status"] == "auto_approved",
          "小额补偿自动通过")

    # 11) 非法参数校验
    r5 = one(await call_mcp_tool(base, "get_order", {"order_id": "12345"}))
    check(r5.get("status") == "invalid", "非法订单号被拒绝")

    # 12) 服务间鉴权：无 Key / 错误 Key 应被 401 拒绝（需在 .env.local 配置 MCP_API_KEY）
    if get_settings().mcp_api_key:
        payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
        async with httpx.AsyncClient(trust_env=False, timeout=10) as hc:
            r_no = await hc.post(f"{base}/mcp", json=payload,
                                 headers={"Content-Type": "application/json", "Accept": "application/json"})
            r_bad = await hc.post(f"{base}/mcp", json=payload,
                                  headers={"Content-Type": "application/json", "Accept": "application/json",
                                           "X-MCP-Key": "wrong-key"})
        check(r_no.status_code == 401, f"无 X-MCP-Key → 401（实际 {r_no.status_code}）")
        check(r_bad.status_code == 401, f"错误 X-MCP-Key → 401（实际 {r_bad.status_code}）")
    else:
        print("  （MCP_API_KEY 未配置，鉴权用例跳过）")

    print(f"\n{'='*46}")
    print(f"P2 验收：通过 {ok} / {ok + fail}")
    print(f"{'='*46}")


if __name__ == "__main__":
    asyncio.run(main())
