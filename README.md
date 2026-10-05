# 电商多 Agent 智能客服平台（基于 LangGraph）

![CI](https://github.com/vanvanovo/ecommerce-cs-platform/actions/workflows/ci.yml/badge.svg)

> 从 EduAgent_Pro（教学版架构）迁移改造为电商客服业务，
> 借鉴 SmartVoyage 的 A2A / MCP 工程模式。
>
> **技术栈**：LangGraph + FastAPI + Vue3/Element Plus + PostgreSQL + Milvus + Redis + python-a2a + MCP(FastMCP) + 本地 Qwen / DeepSeek 混合路由

---

## 一、架构总览

```
┌───────────────────────── 前端工作台（Vue3 :3000）─────────────────────────┐
│  统一入口对话（意图卡/来源/转人工卡） · 主管审批（HitL） · 未解决问题池        │
└──────────────────────────────────┬──────────────────────────────────────┘
                                   │ SSE
┌────────────────────────── 后端（FastAPI :8000）──────────────────────────┐
│ 统一入口 unified_chat：规则前置 → 混合路由（本地 Qwen → 云端回退）           │
│    ├─ 单意图高置信 → 短路直出        ├─ 多意图 → asyncio 并行 + 汇总校验    │
│    └─ 低置信/转人工 → 交接摘要 + 未解决问题池                                │
│ Orchestrator（三层兜底：重试 3 次 1/2/4s → 兜底响应）                        │
│ 四 Agent（LangGraph）：商品咨询 / 订单物流 / 售后 HitL / 投诉转人工          │
└──────┬───────────────────────┬───────────────────────┬────────────────────┘
       │ MCP(带 X-MCP-Key)     │ A2A(python-a2a)       │ Redis
┌──────▼───────┐   ┌───────────▼──────────┐   ┌────────▼─────────┐
│ MCP 订单工具  │   │ RAG 知识库 Agent :5008 │   │ 缓存/写锁/指标    │
│ :8101 8 工具  │   │ （可插拔：mcp/inproc/  │   │ route/rag/logi   │
│ 幂等+审计     │   │   http[B后补预留]）    │   │ + 分布式锁       │
└──────┬───────┘   └───────────┬──────────┘   └──────────────────┘
       │                       │
   PostgreSQL :5433        Milvus :19531（BGE-M3 + Reranker）
```

## 二、快速开始（Windows / 本机演示）

```powershell
# 0) 约定：在仓库根目录执行；Python 环境任意（依赖见 requirements.txt）
$py = "python"
$env:PYTHONPATH = (Get-Location).Path

# 1) 中间件（PostgreSQL / Milvus / etcd / MinIO / Redis）
docker compose --env-file .env.local up -d

# 2) 配置：复制 .env.example → .env.local，填 DEEPSEEK_API_KEY / MCP_API_KEY 等

# 3) 后端 :8000
& $py -m uvicorn backend.main:app --host 0.0.0.0 --port 8000

# 4) RAG A2A Agent :5008（可选；RAG_VIA_A2A=true 时启用）
& $py services\rag_agent\server.py

# 5) 前端 :3000
cd frontend; npm install; npm run dev
```

**演示账号**：消费者 `student01@eduagent.local / Student@123456`；主管 `teacher01@eduagent.local / Teacher@123456`（可看审批页/问题池）。

## 三、端口与开关

| 服务 | 地址/端口 | 说明 |
|---|---|---|
| 后端 API | :8000（/docs 可调试） | `uvicorn backend.main:app` |
| 前端工作台 | :3000 | `vite`（dev proxy `/api → :8000`） |
| RAG A2A Agent | :5008 | `RAG_VIA_A2A=true` 时商品咨询走 A2A |
| MCP 订单工具 | 挂在后端 `/mcp/cs`；独立 :8101 | `X-MCP-Key` 鉴权 |
| PostgreSQL / Milvus / Redis | :5433 / :19531 / :6380 | docker compose |
| Mock OMS（可选） | :8200 | `ORDER_BACKEND=api` 时演示外部订单系统 |

关键环境变量：`ROUTER_PROVIDER=ollama_cpu`、`ORDER_BACKEND=db|api`、`RAG_VIA_A2A=true|false`、`RAG_AGENT_RETRIEVAL_MODE=mcp|inproc|http`、`REDIS_URL`。

## 四、验收 / 测试脚本

| 脚本 | 验收对象 |
|---|---|
| `scripts/check_order.py` / `check_aftersale.py` / `check_complaint.py` | P3 各 Agent（36 项断言） |
| `scripts/check_unified_p4.py` | P4 统一入口（短路/并行/转人工） |
| `scripts/check_rag_a2a.py direct\|chat` | P5 A2A（直连 / 在线 / 离线降级） |
| `scripts/check_p6_redis.py route\|rag\|logistics\|lock\|metrics` | P6 Redis 五项 |
| `scripts/bench_p6.py` | 实测数字（缓存省时 / 短路 vs 并行 / 工单统计） |
| `scripts/eval_intent.py` | 意图路由评测（275 条 → 86.5%） |
| `scripts/mock_oms_api.py` | 外部订单系统 Mock（数据源适配演示） |

## 五、文档

- `docs/客服平台实施计划.md`（P0–P6 清单与状态）
- `docs/p1_验收记录.md` ~ `docs/p6_实测数据与评测报告.md`（逐阶段验收与实测数字）
- `docs/客服平台流程图.html`（架构流程图）
- `services/rag_agent/README.md`（A2A 服务说明）

## 六、阶段状态

**P0–P6 全部完成** ✅ —— 环境基线 → 数据/知识库/路由 → MCP 工具 → 四 Agent → 统一入口 → A2A 独立知识库 Agent → 前端工作台/Redis/评测/部署文档。

---

> **仓库收录说明**：未收录模型权重（`backend/models/`，约 4.5GB）、前端 `node_modules/`、运行日志与 `.env.local`（密钥）；本地运行请按上文准备中间件，并从 `.env.example` 复制出 `.env.local` 填写自己的密钥。