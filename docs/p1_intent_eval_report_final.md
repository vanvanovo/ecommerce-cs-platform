# P1 意图路由评测报告

> 评测集：`backend/core/data/ecom_intent_eval.jsonl`（共 275 条；本次 275 条分层抽样）
> Provider：ollama_cpu

## 总览

| Provider | JSON 有效 | 意图完全匹配 | 追问判断 | 订单号槽位 | 误抽槽位 | P50 | P95 |
|---|---|---|---|---|---|---|---|
| ollama_cpu | 100.0% | **86.5%** | 94.9% | 100.0% | 0.0% | 5008ms | 6845ms |

## 分类别准确率

| Provider | 正常 | 模糊 | 越界 | 多意图 |
|---|---|---|---|---|
| ollama_cpu | 94.3% | 90.9% | 82.2% | 67.9% |

## 单标签指标（F1 / 准 / 召）

| 意图 | ollama_cpu |
|---|---|
| product | 0.91 (0.84/1.00) |
| order | 0.84 (0.95/0.76) |
| logistics | 0.90 (0.94/0.86) |
| aftersale | 0.91 (0.85/0.98) |
| complaint | 0.96 (1.00/0.93) |
| human | 1.00 (1.00/1.00) |
| chitchat | 0.75 (0.75/0.75) |
| out_of_scope | 0.90 (1.00/0.82) |

## ollama_cpu · Badcase（前 15 条）

| 文本 | 期望 | 实际 | 追问(期望/实际) |
|---|---|---|---|
| 订单A1006能帮我取消吗？ | order | aftersale | False/False |
| 订单A1040能开发票吗？ | order | product | False/False |
| 订单A1018能帮我取消吗？ | order | aftersale | False/False |
| 订单A1043能开发票吗？ | order | product | False/False |
| 我的包裹什么时候能到？ | logistics | logistics | False/True |
| 订单A1015显示签收了但我没收到 | logistics | logistics+aftersale | False/False |
| 订单A1012什么时候发货？ | logistics | order | False/False |
| 订单A1027显示签收了但我没收到 | logistics | logistics+aftersale | False/False |
| 订单A1011什么时候发货？ | logistics | order | False/False |
| 这个东西坏了怎么办 | aftersale | aftersale | True/False |
| 帮我查查物流 | logistics | logistics | True/False |
| 我的单子到哪了 | logistics | logistics | True/False |
| 怎么申请售后 | aftersale | aftersale | True/False |
| 订单有点问题 | order | aftersale | True/True |
| 保修怎么弄 | aftersale | product | True/False |
