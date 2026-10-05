# P1 意图路由评测报告

> 评测集：`backend/core/data/ecom_intent_eval.jsonl`（共 273 条；本次 273 条分层抽样）
> Provider：ollama_cpu

## 总览

| Provider | JSON 有效 | 意图完全匹配 | 追问判断 | 订单号槽位 | 误抽槽位 | P50 | P95 |
|---|---|---|---|---|---|---|---|
| ollama_cpu | 100.0% | **83.2%** | 92.3% | 100.0% | 0.0% | 4484ms | 6277ms |

## 分类别准确率

| Provider | 正常 | 模糊 | 越界 | 多意图 |
|---|---|---|---|---|
| ollama_cpu | 83.6% | 87.5% | 95.6% | 69.6% |

## 单标签指标（F1 / 准 / 召）

| 意图 | ollama_cpu |
|---|---|
| product | 0.83 (0.74/0.95) |
| order | 0.82 (0.85/0.80) |
| logistics | 0.87 (0.85/0.89) |
| aftersale | 0.95 (0.94/0.97) |
| complaint | 1.00 (1.00/1.00) |
| human | 1.00 (1.00/1.00) |
| chitchat | 0.77 (0.80/0.75) |
| out_of_scope | 0.98 (1.00/0.96) |

## ollama_cpu · Badcase（前 15 条）

| 文本 | 期望 | 实际 | 追问(期望/实际) |
|---|---|---|---|
| IH 电饭煲发什么快递？ | product | logistics | False/False |
| 声波电动牙刷发什么快递？ | product | logistics | False/False |
| 我上周下的单怎么还没动静？ | order | order+logistics | False/False |
| 最近一笔订单到哪一步了？ | order | logistics | False/False |
| 订单A1035什么时候发货？ | order | logistics | False/False |
| 订单A1044什么时候发货？ | order | logistics | False/False |
| 订单A1018派送中多久能送到？ | logistics | logistics+product | False/False |
| 订单A1015显示签收了但我没收到 | logistics | order+logistics | False/False |
| 订单A1007显示签收了但我没收到 | logistics | order+logistics | False/False |
| 订单A1002我要退货 | aftersale | aftersale+order | False/False |
| 智能手表 S2拆封了还能退吗？ | aftersale | aftersale+product | False/False |
| 退款一般多久到账？ | aftersale | aftersale+product | False/False |
| 我想把便携充电宝换成别的颜色 | aftersale | aftersale | False/True |
| 保修期内坏了怎么维修？ | aftersale | product+aftersale | False/False |
| 订单A1033想换个新的 | aftersale | aftersale+order | False/False |
