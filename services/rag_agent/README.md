# services/rag_agent · 独立 RAG 知识库 A2A Agent（P5）

## 是什么

把平台的"知识库检索能力"独立成一个 A2A 服务（`python-a2a`）：

- 对平台：**A2A 协议**调用（AgentCard 能力发现 + Task 状态机 + artifacts 返回）；
- 对内：检索后端**可插拔**（`RAG_AGENT_RETRIEVAL_MODE`）：
  - `mcp`（默认）：调平台现有 MCP 知识库工具 `search_knowledge_base`（零额外模型加载，本机内存友好）；
  - `inproc`：进程内加载 BGE-M3 + Reranker（"真独立"但吃内存）；
  - `http`（B 后补预留）：调用外部 RAG 服务（一期 `ecommerce_rag` 包成 HTTP 后接这里）。

## 运行

```powershell
cd D:\work\cs-platform
& C:\Users\97916\.conda\envs\Edu_Agent\python.exe services\rag_agent\server.py
# → http://localhost:5008
```

## 平台侧开关

`.env.local`：

```ini
RAG_VIA_A2A=true                     # 打开后，商品咨询 Agent 的检索走 A2A
RAG_AGENT_URL=http://localhost:5008
RAG_AGENT_RETRIEVAL_MODE=mcp
A2A_TIMEOUT_SECONDS=3
```

- 打开：商品咨询检索经 A2A → 独立 RAG Agent；回答带来源；
- 关掉 RAG Agent（或超时）：检索返回空 → 走既有 `llm_direct` 低置信分支（**只降级、不 500**）。

## 返回契约（artifacts JSON）

```json
{
  "query": "七天无理由退货的规则是什么？",
  "docs": [{"content": "...", "source_name": "02-售后政策 > ...", "score": 0.97}],
  "confidence": 0.97,
  "is_high_confidence": true,
  "mode": "mcp"
}
```

## B 后补（一期 ecommerce_rag 接入）

1. 把 `D:\新建文件夹\阳\ecommerce_rag` 的检索服务跑起来（需先解决端口/依赖/Key）；
2. 给它套一个 `GET /search?query=..&top_k=..&tenant_id=..` 接口；
3. 本服务设 `RAG_AGENT_RETRIEVAL_MODE=http` + `RAG_EXTERNAL_URL=...` 即可切换——**A2A 契约与平台侧零改动**。
