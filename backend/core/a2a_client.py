# backend/core/a2a_client.py
# A2A 客户端：调用独立 RAG 知识库 Agent（P5）
#
# 设计要点：
#   - 统一超时（默认 3s，可按环境实测调整），失败抛 A2ACallError 由调用方降级；
#   - 解析 Task 状态：completed → 读 artifacts；input_required / failed → 报错；
#   - 与 services/rag_agent 的 artifacts 契约保持一致（JSON 字符串）。

import asyncio
import json
import uuid

from python_a2a import A2AClient, Message, MessageRole, Task, TextContent

from backend.config import get_settings
from backend.core.logger import get_logger

logger = get_logger(__name__)


class A2ACallError(Exception):
    """A2A 调用失败（超时 / 连接失败 / 任务非完成态）。"""


async def call_rag_agent(query: str) -> dict:
    """调用 RAG A2A Agent，返回：
    {"query", "docs": [{"content","source_name","score"}], "confidence", "is_high_confidence", "mode"}

    失败抛 A2ACallError（调用方决定降级策略）。
    """
    settings = get_settings()
    client = A2AClient(settings.rag_agent_url)

    message = Message(content=TextContent(text=query), role=MessageRole.USER)
    task = Task(id=f"task-{uuid.uuid4().hex[:10]}", message=message.to_dict())

    try:
        raw = await asyncio.wait_for(
            client.send_task_async(task),
            timeout=settings.a2a_timeout_seconds,
        )
    except asyncio.TimeoutError as e:
        raise A2ACallError(f"RAG Agent 超时（>{settings.a2a_timeout_seconds}s）") from e
    except Exception as e:  # noqa: BLE001
        raise A2ACallError(f"RAG Agent 调用失败：{e}") from e

    state = getattr(getattr(raw, "status", None), "state", None)
    state_val = getattr(state, "value", state)
    if state_val != "completed":
        msg = getattr(getattr(raw, "status", None), "message", None)
        raise A2ACallError(f"RAG Agent 任务未完成（state={state_val}）：{json.dumps(msg, ensure_ascii=False, default=str)[:200]}")

    try:
        text = raw.artifacts[0]["parts"][0]["text"]
        return json.loads(text)
    except Exception as e:  # noqa: BLE001
        raise A2ACallError(f"RAG Agent 返回解析失败：{e}") from e
