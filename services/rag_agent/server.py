# services/rag_agent/server.py
# 独立 RAG 知识库 A2A Agent（P5）
#
# 定位：把"知识库检索能力"独立成一个 A2A 服务——
#   - 对平台：通过 A2A 协议调用（AgentCard 能力发现 + Task 状态机）
#   - 对内：检索后端可插拔（mcp 默认 / inproc / http[B 预留]）
#
# 运行：python services/rag_agent/server.py     → http://localhost:5008
# 平台侧调用：backend/core/a2a_client.py::call_rag_agent

from __future__ import annotations

import asyncio
import json
import sys
import threading
import uuid
from pathlib import Path

# 让独立进程也能 import backend.*（repo 根目录）
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from python_a2a import (  # noqa: E402
    A2AServer,
    AgentCard,
    AgentSkill,
    Task,
    TaskState,
    TaskStatus,
    run_server,
)

from backend.config import get_settings  # noqa: E402
from backend.core.logger import get_logger  # noqa: E402
from services.rag_agent.retriever import retrieve_docs  # noqa: E402

logger = get_logger(__name__)

AGENT_NAME = "RagKnowledgeAgent"
AGENT_DESCRIPTION = "电商知识库 RAG 检索服务：商品参数 / 售后政策 / 物流规则 / 保修条款"


def build_agent_card(port: int) -> AgentCard:
    return AgentCard(
        name=AGENT_NAME,
        description=AGENT_DESCRIPTION,
        url=f"http://localhost:{port}",
        version="1.0.0",
        capabilities={"streaming": False, "memory": False},
        skills=[
            AgentSkill(name="faq_search",
                       description="FAQ 与商品知识检索",
                       examples=["七天无理由退货的规则是什么？"]),
            AgentSkill(name="policy_lookup",
                       description="售后 / 物流 / 保修政策查询",
                       examples=["退款一般多久到账？"]),
            AgentSkill(name="product_params",
                       description="商品参数与价格查询",
                       examples=["无线蓝牙耳机 Pro 的参数和价格"]),
        ],
    )


class RagKnowledgeAgent(A2AServer):
    """A2A 知识库检索 Agent：接收 Task → 检索 → artifacts 返回结构化结果。

    工程细节（P6）：服务内常驻一个事件循环——
    若每个请求都 asyncio.run() 新建循环，Redis 异步连接池会绑定在"上一请求已关闭的循环"上，
    表现为缓存第二次读取必失败（Event loop is closed）。改为 run_coroutine_threadsafe 提交到常驻循环。
    """

    def __init__(self, port: int):
        super().__init__(agent_card=build_agent_card(port))
        self._port = port
        self._loop = asyncio.new_event_loop()
        threading.Thread(target=self._loop.run_forever, daemon=True).start()

    async def _handle(self, query: str) -> dict:
        result = await retrieve_docs(query, "tenant_default", top_k=3)
        logger.info("rag_agent.answered", query=query[:50],
                    hits=len(result["docs"]), confidence=result["confidence"])
        return {"query": query, **result}

    def _run_sync(self, coro, timeout: float = 120.0):
        """把协程提交到常驻循环并等待结果。"""
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result(timeout=timeout)

    # python-a2a 的同步任务处理器（服务进程内常驻循环，见类docstring）
    def handle_task(self, task: Task) -> Task:
        try:
            text = (((task.message or {}).get("content") or {}) or {}).get("text", "")
        except Exception:
            text = ""
        text = (text or "").strip()

        if not text:
            task.status = TaskStatus(state=TaskState.INPUT_REQUIRED)
            task.message = {"role": "agent",
                            "content": {"text": "请提供要查询的问题，例如：七天无理由退货的规则是什么？"}}
            return task

        try:
            result = self._run_sync(self._handle(text))
            task.artifacts = [{"parts": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}]}]
            task.status = TaskStatus(state=TaskState.COMPLETED)
        except Exception as e:  # noqa: BLE001 —— 异常要落到 TaskState.FAILED，别炸服务
            logger.error("rag_agent.failed", error=str(e)[:300])
            task.status = TaskStatus(state=TaskState.FAILED)
            task.message = {"role": "agent", "content": {"text": f"知识库服务异常：{e}"}}
        return task


if __name__ == "__main__":
    settings = get_settings()
    port = settings.rag_agent_port
    agent = RagKnowledgeAgent(port)
    print(f"RAG Knowledge A2A Agent → http://localhost:{port}")
    print(f"  AgentCard: {AGENT_NAME} | retrieval_mode={settings.rag_agent_retrieval_mode}")
    run_server(agent, host="0.0.0.0", port=port)
