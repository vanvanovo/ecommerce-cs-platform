# P1 意图路由评测报告

> 评测集：`backend/core/data/ecom_intent_eval.jsonl`（共 60 条；本次 60 条分层抽样）
> Provider：ollama_cpu / ollama_gpu / deepseek

## 总览

| Provider | JSON 有效 | 意图完全匹配 | 追问判断 | 订单号槽位 | 误抽槽位 | P50 | P95 |
|---|---|---|---|---|---|---|---|
| ollama_cpu | 100.0% | **91.7%** | 96.7% | 100.0% | 0.0% | 4129ms | 5849ms |
| ollama_gpu | 100.0% | **91.7%** | 96.7% | 100.0% | 0.0% | 4111ms | 6303ms |
| deepseek | 88.3% | **83.3%** | 88.3% | 79.2% | 0.0% | 820ms | 1306ms |

## 分类别准确率

| Provider | 正常 | 模糊 | 越界 | 多意图 |
|---|---|---|---|---|
| ollama_cpu | 90.3% | 100.0% | 100.0% | 83.3% |
| ollama_gpu | 90.3% | 100.0% | 100.0% | 83.3% |
| deepseek | 87.1% | 85.7% | 100.0% | 58.3% |

## 单标签指标（F1 / 准 / 召）

| 意图 | ollama_cpu | ollama_gpu | deepseek |
|---|---|---|---|
| product | 0.84 (0.80/0.89) | 0.84 (0.80/0.89) | 0.95 (0.90/1.00) |
| order | 0.82 (0.88/0.78) | 0.82 (0.88/0.78) | 0.94 (1.00/0.89) |
| logistics | 0.97 (0.94/1.00) | 0.97 (0.94/1.00) | 0.90 (0.93/0.87) |
| aftersale | 1.00 (1.00/1.00) | 1.00 (1.00/1.00) | 0.70 (1.00/0.54) |
| complaint | 1.00 (1.00/1.00) | 1.00 (1.00/1.00) | 0.78 (1.00/0.64) |
| human | 1.00 (1.00/1.00) | 1.00 (1.00/1.00) | 0.86 (0.75/1.00) |
| chitchat | 0.89 (0.80/1.00) | 0.89 (0.80/1.00) | 1.00 (1.00/1.00) |
| out_of_scope | 1.00 (1.00/1.00) | 1.00 (1.00/1.00) | 1.00 (1.00/1.00) |

## ollama_cpu · Badcase（前 7 条）

| 文本 | 期望 | 实际 | 追问(期望/实际) |
|---|---|---|---|
| 最近一笔订单到哪一步了？ | order | logistics | False/False |
| 订单A1002我要退货 | aftersale | aftersale+order | False/False |
| 退款一般多久到账？ | aftersale | aftersale+product | False/False |
| 包裹卡住了 | logistics | logistics | True/False |
| 我的包裹不见了 | logistics | logistics | True/False |
| 帮我查订单A1016，再推荐个家电 | order+product | order+chitchat | False/False |
| 订单A1043退款到账没？还有智能手表 S2能换货吗 | order+aftersale | aftersale+product | False/False |

## ollama_gpu · Badcase（前 7 条）

| 文本 | 期望 | 实际 | 追问(期望/实际) |
|---|---|---|---|
| 最近一笔订单到哪一步了？ | order | logistics | False/False |
| 订单A1002我要退货 | aftersale | aftersale+order | False/False |
| 退款一般多久到账？ | aftersale | aftersale+product | False/False |
| 包裹卡住了 | logistics | logistics | True/False |
| 我的包裹不见了 | logistics | logistics | True/False |
| 帮我查订单A1016，再推荐个家电 | order+product | order+chitchat | False/False |
| 订单A1043退款到账没？还有智能手表 S2能换货吗 | order+aftersale | aftersale+product | False/False |

## deepseek · Badcase（前 10 条）

| 文本 | 期望 | 实际 | 追问(期望/实际) |
|---|---|---|---|
| 再没人处理我就发小红书曝光 | complaint | ∅ | False/True |
| 最近一笔订单到哪一步了？ | order | logistics+order | False/True |
| 订单A1048的退款进度查一下 | aftersale | ∅ | False/True |
| 订单A1035的退款进度查一下 | aftersale | ∅ | False/True |
| 这个能退吗 | aftersale | ∅ | True/True |
| 物流A1034太慢了，我要退款还要投诉 | logistics+aftersale+complaint | ∅ | False/True |
| 物流A1015太慢了，我要退款还要投诉 | logistics+aftersale+complaint | ∅ | False/True |
| 物流A1005太慢，你们客服也不理我 | logistics+complaint | logistics+complaint+human | False/False |
| 订单A1043退款到账没？还有智能手表 S2能换货吗 | order+aftersale | aftersale+product | False/False |
| 我要投诉，订单A1030退款一直不到账 | complaint+aftersale | ∅ | False/True |
