# scripts/gen_ecom_intent_eval.py
# 生成电商意图路由评测集（AI 起草版，待人工抽检扩充）
# 四类：normal（正常）/ vague（模糊）/ out_of_scope（越界）/ multi（多意图）
# 输出：backend/core/data/ecom_intent_eval.jsonl（每行一条：text / category / intents / slots / need_clarify）
# 执行：python scripts/gen_ecom_intent_eval.py

import json
import random
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "backend" / "core" / "data" / "ecom_intent_eval.jsonl"
RNG = random.Random(7)

PRODUCTS = ["无线蓝牙耳机 Pro", "智能手表 S2", "便携充电宝", "机械键盘 K87", "游戏鼠标",
            "27 英寸 2K 显示器", "蓝牙音箱 Mini", "扫地机器人 X10", "声波电动牙刷",
            "智能空气炸锅", "IH 电饭煲", "无线充电板", "手机壳", "平板支架"]
CATS = ["蓝牙耳机", "智能手表", "充电宝", "机械键盘", "显示器", "家电"]
OIDS = [f"A{i}" for i in list(range(1001, 1024)) + list(range(1025, 1049))]

# ── 正常样本模板：（模板, 是否带订单号槽位）────────────────────
NORMAL = {
    "product": [
        ("这款{product}多少钱？", False), ("{product}支持七天无理由退货吗？", False),
        ("{product}保修多久？", False), ("你们有什么{cat}推荐？", False),
        ("{product}和同类产品比有什么优势？", False), ("我想看下{product}的参数", False),
        ("{product}现在有货吗？", False), ("{product}适合送人吗？", False),
        ("{cat}类目里最值得买的是哪个？", False), ("{product}耗电快不快？", False),
        ("{product}颜色有哪些？", False), ("{product}实际体验怎么样？", False),
        ("这个{cat}能用多久？", False), ("{product}支持分期吗？", False),
        ("{product}支持以旧换新吗？", False),
    ],
    "order": [
        ("帮我查一下订单{oid}", True), ("订单{oid}买的是什么？", True),
        ("订单{oid}现在什么状态？", True), ("我上周下的单怎么还没动静？", False),
        ("订单{oid}总共花了多少钱？", True), ("帮我看看{oid}这单付款成功没", True),
        ("最近一笔订单到哪一步了？", False), ("订单{oid}能帮我取消吗？", True),
        ("帮我核对下订单{oid}的地址", True), ("订单{oid}的收货地址是哪？", True),
        ("订单{oid}能开发票吗？", True), ("我想改订单{oid}的收货信息", True),
        ("订单{oid}用的什么优惠？", True),
    ],
    "logistics": [
        ("订单{oid}的快递到哪了？", True), ("物流{oid}怎么三天没更新了？", True),
        ("我的包裹什么时候能到？", False), ("订单{oid}显示已发货但查不到轨迹", True),
        ("快递{oid}为什么一直停在转运中心？", True), ("发什么快递？几天能到货？", False),
        ("订单{oid}派送中多久能送到？", True), ("包裹{oid}现在到哪个城市了？", True),
        ("订单{oid}今天能送到吗？", True), ("物流信息一直没动，帮我催一下", False),
        ("订单{oid}显示签收了但我没收到", True), ("{oid}大概几天能到？", True), ("订单{oid}什么时候发货？", True),
    ],
    "aftersale": [
        ("订单{oid}我要退货", True), ("{product}拆封了还能退吗？", False),
        ("退款一般多久到账？", False), ("以旧换新怎么操作？", False),
        ("订单{oid}申请退款怎么操作？", True), ("保修期内坏了怎么维修？", False),
        ("订单{oid}想换个新的", True), ("无理由退货运费谁出？", False),
        ("{product}退货要包装盒吗？", False), ("订单{oid}退款到哪张卡？", True),
        ("订单{oid}怎么申请退货？", True), ("换货运费谁承担？", False),
        ("退款审核要多久？", False), ("订单{oid}的退款进度查一下", True),
        ("拆封了还能换货吗？", False),
    ],
    "complaint": [
        ("你们服务太差了，我要投诉", False), ("再不解决我就去12315投诉", False),
        ("我要给差评并且曝光你们", False), ("催了三次都没人理，什么破服务", False),
        ("客服态度特别差，我要投诉他", False), ("退款拖了半个月，我要投诉", False),
        ("你们这是欺诈，我要去平台投诉", False), ("买东西体验极差，考虑投诉", False),
        ("我要投诉你们客服", False), ("这单体验太差，我要投诉到平台", False),
        ("再没人处理我就发小红书曝光", False), ("你们承诺的时间没做到，我要投诉", False),
        ("投诉渠道在哪？", False),
    ],
    "human": [
        ("转人工", False), ("我要找人工客服", False), ("帮我转接真人", False),
        ("人工客服在哪？", False), ("不想跟机器人说，转人工", False), ("找客服", False),
        ("我要人工", False), ("转接人工客服谢谢", False), ("请人工客服回复我", False),
        ("机器人别回复了，转人工", False), ("给我接一个客服", False),
    ],
    "chitchat": [
        ("你好", False), ("在吗？", False), ("谢谢", False), ("你们几点上班？", False),
        ("早上好", False), ("辛苦了", False), ("再见", False), ("哈喽", False),
        ("谢谢啦", False), ("晚上好", False), ("你们客服真耐心", False), ("节日快乐", False),
    ],
}

# ── 模糊样本（缺关键信息，need_clarify=True）──────────────────
VAGUE = [
    ("我想退货", ["aftersale"]), ("帮我查一下订单", ["order"]), ("我的快递好像有问题", ["logistics"]),
    ("这个东西坏了怎么办", ["aftersale"]), ("我要退款", ["aftersale"]), ("帮我查查物流", ["logistics"]),
    ("这个能退吗", ["aftersale"]), ("我的单子到哪了", ["logistics"]), ("怎么申请售后", ["aftersale"]),
    ("订单有点问题", ["order"]), ("帮我处理下退货", ["aftersale"]), ("快递出问题了", ["logistics"]),
    ("我想问下我的订单", ["order"]), ("保修怎么弄", ["aftersale"]), ("怎么退款呢", ["aftersale"]),
    ("查一下我的包裹", ["logistics"]), ("我想退货但找不到订单号", ["aftersale"]), ("帮我退下这个", ["aftersale"]),
    ("快递怎么还没到", ["logistics"]), ("我的包裹不见了", ["logistics"]), ("想查一下物流", ["logistics"]),
    ("退货运费怎么算", ["aftersale"]), ("订单状态帮我看看", ["order"]), ("帮我看看买了啥", ["order"]),
    ("想换个货", ["aftersale"]), ("想把买的东西换个颜色", ["aftersale"]), ("这个坏了能退吗", ["aftersale"]), ("麻烦查下快递", ["logistics"]),
    ("钱什么时候退", ["aftersale"]), ("订单查不到", ["order"]), ("怎么退钱", ["aftersale"]),
    ("包裹卡住了", ["logistics"]), ("想售后", ["aftersale"]),
]

# ── 越界样本（与商城无关）───────────────────────────────────
OUT_OF_SCOPE = [
    "帮我写个 Python 爬虫", "今天天气怎么样？", "帮我订一张去北京的机票",
    "推荐几部好看的电影", "怎么用 Excel 做透视表", "帮我写一篇作文",
    "比特币现在多少钱", "帮我翻译一段英文", "明天股市会涨吗",
    "帮我算一下微积分题目", "怎么减肥最快", "给我讲个笑话",
    "帮我做一份 PPT 大纲", "周末去哪儿玩比较好", "怎么学好英语",
    "帮我写封辞职信", "该怎么跟老板谈加薪", "推荐一款好玩的游戏",
    "怎么申请签证", "帮我规划一条旅游路线", "帮我写周报",
    "推荐个理财产品", "怎么考驾照", "帮我预约体检", "今天有什么新闻",
    "讲个历史故事", "怎么养猫", "帮我算房贷利率", "怎么做红烧肉",
    "推荐几本书", "帮我修图", "怎么注册公司", "帮我写周报",
    "学吉他要多久", "怎么戒烟", "帮我改作文", "股票怎么开户",
    "怎么去杭州东站", "帮我查个单词", "房间怎么除甲醛",
    "帮我起个网名", "怎么做短视频", "推荐个健身计划", "帮我解个方程", "怎么写论文",
]

# ── 多意图模板（2~3 个意图，可带订单号）──────────────────────
MULTI = [
    ("{product}多少钱？另外订单{oid}到哪了", ["product", "logistics"], True),
    ("我要退货，顺便问下{product}保修期多久", ["aftersale", "product"], False),
    ("订单{oid}没收到，而且客服态度很差我要投诉", ["logistics", "complaint"], True),
    ("查下订单{oid}，再告诉我{product}怎么保修", ["order", "product"], True),
    ("{product}拆封能退吗？订单{oid}在这", ["product", "aftersale"], True),
    ("物流{oid}太慢了，我要退款还要投诉", ["logistics", "aftersale", "complaint"], True),
    ("帮我转人工，顺便查下订单{oid}", ["human", "order"], True),
    ("{product}有货吗？订单{oid}什么时候能发", ["product", "order"], True),
    ("订单{oid}退款到账没？还有{product}能换货吗", ["order", "aftersale"], True),
    ("我要投诉物流，订单{oid}一直不动", ["complaint", "logistics"], True),
    ("你好，帮我查下订单{oid}", ["chitchat", "order"], True),
    ("{product}和显示器哪个值得买？订单{oid}能一起退吗", ["product", "aftersale"], True),
    ("{product}多少钱，另外帮我转人工", ["product", "human"], False),
    ("订单{oid}物流不动了，我要退款", ["logistics", "aftersale"], True),
    ("我要投诉，订单{oid}退款一直不到账", ["complaint", "aftersale"], True),
    ("{product}保修多久？订单{oid}要退", ["product", "aftersale"], True),
    ("帮我查订单{oid}，再推荐个{cat}", ["order", "product"], True),
    ("物流{oid}太慢，你们客服也不理我", ["logistics", "complaint"], True),
    ("你好，我想查下物流", ["chitchat", "logistics"], False),
    ("订单{oid}没收到，想问下{product}怎么赔", ["logistics", "aftersale"], True),
]


def fill(template: str, with_oid: bool) -> tuple[str, dict]:
    slots: dict = {}
    text = template.replace("{product}", RNG.choice(PRODUCTS)).replace("{cat}", RNG.choice(CATS))
    if "{oid}" in text or with_oid:
        oid = RNG.choice(OIDS)
        slots["order_id"] = oid
        text = text.replace("{oid}", oid)
    return text, slots


def main() -> None:
    items: list[dict] = []

    def add(text: str, category: str, intents: list[str], slots: dict, need_clarify: bool) -> None:
        items.append({"text": text, "category": category, "intents": intents,
                      "slots": slots, "need_clarify": need_clarify})

    # normal：每类标签 30 条（模板轮换 + 随机槽位，去重后约 180+）
    for label, templates in NORMAL.items():
        for i in range(30):
            tpl, with_oid = templates[i % len(templates)]
            text, slots = fill(tpl, with_oid)
            if "{oid}" in tpl and "order_id" not in slots:
                slots["order_id"] = RNG.choice(OIDS)
            add(text, "normal", [label], slots, False)

    # vague：32 条（全部保留）
    for text, intents in VAGUE:
        add(text, "vague", intents, {}, True)

    # out_of_scope：45 条
    for text in OUT_OF_SCOPE:
        add(text, "out_of_scope", ["out_of_scope"], {}, False)

    # multi：20 模板 × 3 轮 = 60 条
    for _ in range(3):
        for tpl, intents, with_oid in MULTI:
            text, slots = fill(tpl, with_oid)
            add(text, "multi", intents, slots, False)

    # 去重（按文本）
    seen: set[str] = set()
    unique: list[dict] = []
    for it in items:
        if it["text"] in seen:
            continue
        seen.add(it["text"])
        unique.append(it)

    order = {"normal": 0, "vague": 1, "out_of_scope": 2, "multi": 3}
    unique.sort(key=lambda x: order[x["category"]])
    for i, it in enumerate(unique, 1):
        it["id"] = f"E{i:04d}"

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as f:
        for it in unique:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")

    from collections import Counter
    c = Counter(it["category"] for it in unique)
    print(f"✅ 评测集已生成：{OUT}")
    print(f"   总数 {len(unique)} 条 | " + " / ".join(f"{k}:{v}" for k, v in c.items()))


if __name__ == "__main__":
    main()
