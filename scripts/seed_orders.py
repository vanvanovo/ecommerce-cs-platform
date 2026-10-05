# scripts/seed_orders.py
# 执行：python scripts/seed_orders.py [--force]
# 用途：执行 ecom_init.sql 建表 + 灌入电商模拟数据（客户/商品/订单/物流/售后）
# 特点：确定性随机（seed=42），覆盖售后规则边界（超 7 天 / 已拆封 / 金额阈值 / 超时未发货）

import asyncio
import random
import sys
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import asyncpg

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.config import get_settings

s = get_settings()
DB_DSN = (
    f"postgresql://{s.db_user}:{s.db_password}"
    f"@{s.db_host}:{s.db_port}/{s.db_name}"
)
SQL_FILE = Path(__file__).resolve().parent / "ecom_init.sql"
NOW = datetime.now(timezone.utc)
RNG = random.Random(42)

# ── 商品（15 个，覆盖两类售后规则）────────────────────────────
PRODUCTS = [
    # sku,        name,                  category,  price, warranty, returnable, unopened_required, stock
    ("SKU-1001", "无线蓝牙耳机 Pro",      "数码配件", 699,  12, True,  True,  80),
    ("SKU-1002", "智能手表 S2",           "智能设备", 1299, 24, True,  False, 45),
    ("SKU-1003", "便携充电宝 20000mAh",   "数码配件", 199,  12, True,  False, 200),
    ("SKU-1004", "机械键盘 K87",          "数码配件", 459,  12, True,  False, 60),
    ("SKU-1005", "游戏鼠标 轻量版",       "数码配件", 229,  12, True,  False, 120),
    ("SKU-1006", "USB-C 快充数据线 2m",   "数码配件", 49,   6,  True,  False, 500),
    ("SKU-1007", "27 英寸 2K 显示器",     "数码配件", 1499, 36, True,  False, 25),
    ("SKU-1008", "蓝牙音箱 Mini",         "数码配件", 399,  12, True,  False, 90),
    ("SKU-1009", "扫地机器人 X10",        "家用电器", 2199, 24, True,  False, 15),
    ("SKU-1010", "声波电动牙刷",          "家用电器", 299,  12, True,  True,  70),
    ("SKU-1011", "智能空气炸锅 5L",       "家用电器", 499,  12, True,  False, 40),
    ("SKU-1012", "IH 电饭煲 4L",          "家用电器", 399,  24, True,  False, 35),
    ("SKU-1013", "手机壳 磨砂防摔",       "数码配件", 59,   0,  True,  False, 300),
    ("SKU-1014", "平板电脑支架 铝合金",   "数码配件", 89,   6,  True,  False, 150),
    ("SKU-1015", "无线充电板 15W",        "数码配件", 129,  12, True,  False, 110),
]

CUSTOMERS = [
    ("张小北", "13800000001", "gold"),
    ("李  明", "13800000002", "normal"),
    ("王  芳", "13800000003", "silver"),
    ("陈  晨", "13800000004", "normal"),
    ("赵  磊", "13800000005", "gold"),
    ("刘  洋", "13800000006", "normal"),
    ("孙  悦", "13800000007", "silver"),
    ("周  琪", "13800000008", "normal"),
    ("吴  桐", "13800000009", "normal"),
    ("郑  好", "13800000010", "silver"),
]

CITIES = ["杭州", "上海", "南京", "苏州", "宁波", "合肥", "武汉", "成都"]


def d(days: float) -> datetime:
    return NOW - timedelta(days=days)


async def main(force: bool) -> None:
    conn = await asyncpg.connect(DB_DSN)
    try:
        # 1) 建表（拆分执行，避开多语句差异）
        sql = SQL_FILE.read_text(encoding="utf-8")
        for stmt in sql.split(";"):
            stmt = stmt.strip()
            if stmt:
                await conn.execute(stmt)
        print("✅ 电商表结构就绪（7 张表）")

        # 2) 幂等检查
        count = await conn.fetchval("SELECT count(*) FROM orders")
        if count and not force:
            print(f"⚠️  已有 {count} 条订单，跳过灌数据（要重建加 --force）")
            return
        if count:
            await conn.execute(
                "TRUNCATE refund_approvals, after_sales_tickets, logistics_tracks, "
                "order_items, orders, products, customers CASCADE"
            )
            print("🧹 已清空旧电商数据")

        # 3) 商品
        await conn.executemany(
            "INSERT INTO products (sku, name, category, price, warranty_months, returnable, unopened_required, stock) "
            "VALUES ($1,$2,$3,$4,$5,$6,$7,$8)",
            [(p[0], p[1], p[2], Decimal(str(p[3])), p[4], p[5], p[6], p[7]) for p in PRODUCTS],
        )

        # 4) 客户
        cust_ids = []
        for name, phone, tier in CUSTOMERS:
            cid = uuid.uuid4()
            cust_ids.append(cid)
            await conn.execute(
                "INSERT INTO customers (id, name, phone, email, tier, created_at) VALUES ($1,$2,$3,$4,$5,$6)",
                cid, name, phone, f"{phone}@example.com", tier, d(RNG.randint(60, 300)),
            )

        # 5) 订单（55 单：A1001–A1055，其中 A1024 为演示订单）
        order_plan = []
        # A1024：演示订单——耳机 699、已签收 3 天、已拆封 → 触发“金额>500 + 已拆封”人工审批
        order_plan.append(("A1024", 0, "delivered", 3, [(("SKU-1001"), 1, True)]))
        # 其余已签收
        for i in list(range(1001, 1024)) + list(range(1025, 1036)):
            oid = f"A{i}"
            cust = RNG.randrange(10)
            days = RNG.choice([0.5, 1, 2, 3, 5, 6, 6.5, 8, 10, 15, 25, 40])
            n_items = RNG.choice([1, 1, 1, 2, 2, 3])
            items = []
            for _ in range(n_items):
                sku, name, cat, price, wm, ret, uor, stock = RNG.choice(PRODUCTS)
                items.append((sku, 1, RNG.random() < 0.35))
            order_plan.append((oid, cust, "delivered", days, items))
        # 在途
        for i in range(1036, 1044):
            order_plan.append((f"A{i}", RNG.randrange(10), "in_transit", RNG.choice([1, 1.5, 2, 3]), [(RNG.choice(PRODUCTS)[0], 1, False)]))
        # 已发货
        for i in range(1044, 1049):
            order_plan.append((f"A{i}", RNG.randrange(10), "shipped", 1, [(RNG.choice(PRODUCTS)[0], 1, False)]))
        # 已付款未发货（含超时：>2 天）
        for i in range(1049, 1056):
            order_plan.append((f"A{i}", RNG.randrange(10), "paid", RNG.choice([0.2, 1, 3, 5, 8]), [(RNG.choice(PRODUCTS)[0], 1, False)]))

        price_map = {p[0]: Decimal(str(p[3])) for p in PRODUCTS}
        ticket_seq = 1001
        for oid, cust_idx, status, age_days, items in order_plan:
            if status == "delivered":
                # 以“签收时间”为锚点倒推：签收 → 发货 → 付款 → 下单，保证不出现未来时间
                delivered = d(age_days)
                shipped = delivered - timedelta(days=RNG.uniform(1, 3))
                paid = shipped - timedelta(hours=RNG.randint(4, 46))
                created = paid - timedelta(minutes=RNG.randint(2, 30))
            else:
                created = d(age_days + RNG.uniform(0.1, 0.5))
                paid = created + timedelta(minutes=RNG.randint(2, 30))
                shipped = (paid + timedelta(hours=RNG.randint(4, 46))) if status in ("shipped", "in_transit") else None
                delivered = None
            total = sum(price_map[sku] for sku, _, _ in items)
            await conn.execute(
                "INSERT INTO orders (id, customer_id, status, total_amount, created_at, paid_at, shipped_at, delivered_at) "
                "VALUES ($1,$2,$3,$4,$5,$6,$7,$8)",
                oid, cust_ids[cust_idx], status, total, created, paid, shipped, delivered,
            )
            for sku, qty, opened in items:
                await conn.execute(
                    "INSERT INTO order_items (order_id, sku, quantity, unit_price, opened) VALUES ($1,$2,$3,$4,$5)",
                    oid, sku, qty, price_map[sku], opened,
                )
            # 物流轨迹
            if status in ("shipped", "in_transit", "delivered"):
                base = shipped
                city = RNG.choice(CITIES)
                tracks = [
                    (base, f"{city}仓", "已揽收", "商品已出库，快递员已揽收"),
                    (base + timedelta(hours=8), f"{city}转运中心", "运输中", "包裹已发往下一站"),
                ]
                if status in ("in_transit", "delivered"):
                    tracks.append((base + timedelta(days=1), "目的地转运中心", "运输中", "包裹到达目的地城市"))
                if status == "in_transit":
                    tracks.append((base + timedelta(days=1, hours=6), "配送网点", "派送中", "快递员正在派送，请保持电话畅通"))
                if status == "delivered":
                    tracks.append((base + timedelta(days=1, hours=10), "收货地址", "派送中", "快递员正在派送"))
                    tracks.append((delivered, "收货地址", "已签收", "您的包裹已签收，感谢使用"))
                cap = NOW - timedelta(hours=2)
                await conn.executemany(
                    "INSERT INTO logistics_tracks (order_id, track_time, location, status, description) VALUES ($1,$2,$3,$4,$5)",
                    [(oid, min(t, cap), loc, st, desc) for t, loc, st, desc in tracks],
                )

        # 6) 售后样例工单（2 张：一自动通过、一待审批）
        await conn.execute(
            "INSERT INTO after_sales_tickets (id, order_id, customer_id, type, reason, status, auto_check, amount, created_at) "
            "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)",
            "RT-2026-1001", "A1010", cust_ids[0], "refund", "充电宝不想要了，未拆封",
            "auto_approved",
            '{"in_warranty": true, "opened": false, "amount_over_threshold": false, "rule": "7天无理由+未拆封+金额<500 自动通过"}',
            Decimal("199"), d(1),
        )
        await conn.execute(
            "INSERT INTO after_sales_tickets (id, order_id, customer_id, type, reason, status, auto_check, amount, created_at) "
            "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)",
            "RT-2026-1002", "A1005", cust_ids[3], "return", "手表已拆封使用，觉得不合适想退",
            "pending_review",
            '{"in_warranty": true, "opened": true, "amount_over_threshold": true, "rule": "已拆封且金额>500，转主管审批"}',
            Decimal("1299"), d(0.5),
        )
        print("✅ 售后样例工单：2 张（RT-2026-1001 自动通过 / RT-2026-1002 待审批）")

        # 7) 汇总
        n_orders = await conn.fetchval("SELECT count(*) FROM orders")
        n_items = await conn.fetchval("SELECT count(*) FROM order_items")
        n_tracks = await conn.fetchval("SELECT count(*) FROM logistics_tracks")
        print(f"\n📦 灌数完成：客户 {len(CUSTOMERS)} / 商品 {len(PRODUCTS)} / 订单 {n_orders} / 明细 {n_items} / 物流轨迹 {n_tracks}")
        print("   演示订单 A1024：无线蓝牙耳机 Pro ¥699，已签收 3 天，已拆封 → 应触发人工审批")
        print("   查询示例：SELECT o.id, o.status, o.total_amount, p.name, i.opened FROM orders o "
              "JOIN order_items i ON i.order_id=o.id JOIN products p ON p.sku=i.sku WHERE o.id='A1024';")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main(force="--force" in sys.argv))
