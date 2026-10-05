# backend/agents/common.py
# 客服新 Agent（订单/售后/投诉）的共享工具：
#   1) MCP 工具调用（超时 5s、传输失败重试 3 次、退避 1s/2s/4s、结果解包）
#   2) 转人工交接摘要生成

import asyncio
import json

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage

from backend.config import get_settings
from backend.core.cache import incr_metric
from backend.core.logger import get_logger
from backend.mcp.client import call_mcp_tool

logger = get_logger(__name__)

MCP_TIMEOUT_SECONDS = 5.0             # MCP 调用超时 5s
MCP_RETRY_DELAYS = (1.0, 2.0, 4.0)    # 失败重试 3 次，指数退避 1s/2s/4s


def unwrap_mcp_result(res):
    """兼容通用 client 的返回约定：单条结果被包成 [item]。"""
    if isinstance(res, list) and len(res) == 1 and isinstance(res[0], dict):
        return res[0]
    return res


async def call_cs_tool(tool_name: str, arguments: dict) -> dict:
    """调用客服订单 MCP 工具：超时 5s；传输层失败重试 3 次（1/2/4s）。

    业务状态（success/not_found/invalid/rejected/duplicate）原样返回、不重试。
    """
    settings = get_settings()
    last_error: Exception | None = None
    await incr_metric("tool_call_total")        # P6 监控埋点：工具调用总数

    for i in range(len(MCP_RETRY_DELAYS) + 1):
        if i > 0:
            await asyncio.sleep(MCP_RETRY_DELAYS[i - 1])
            await incr_metric("tool_call_retry")
        try:
            res = await call_mcp_tool(
                settings.cs_mcp_url, tool_name, arguments, timeout=MCP_TIMEOUT_SECONDS,
            )
        except Exception as e:                      # 传输层失败才重试
            last_error = e
            logger.warning("agent.mcp_call_failed", tool=tool_name, attempt=i + 1, error=str(e)[:150])
            continue

        data = unwrap_mcp_result(res)
        if isinstance(data, dict):
            return data
        return {"status": "error", "message": f"MCP 工具 {tool_name} 返回了非结构化结果"}

    await incr_metric("tool_call_failed")
    raise RuntimeError(f"MCP 工具 {tool_name} 调用失败（重试 {len(MCP_RETRY_DELAYS)} 次）：{last_error}")


def build_handoff_summary(messages: list[BaseMessage], slots: dict, extra: str = "") -> str:
    """生成转人工交接摘要：最近对话要点 + 已收集信息 + 补充说明。"""
    lines = []
    for m in (messages or [])[-6:]:
        if isinstance(m, HumanMessage):
            role = "用户"
        elif isinstance(m, AIMessage):
            role = "客服"
        else:
            continue
        text = m.content if isinstance(m.content, str) else str(m.content)
        lines.append(f"{role}：{text[:120]}")

    parts = ["【对话摘要】", "\n".join(lines) if lines else "（无）"]
    if slots:
        parts += ["【已收集信息】", json.dumps(slots, ensure_ascii=False)]
    if extra:
        parts += ["【补充】", extra]
    return "\n".join(parts)


def last_human_text(messages: list[BaseMessage]) -> str:
    """取最近一条用户消息文本。"""
    for m in reversed(messages or []):
        if isinstance(m, HumanMessage):
            return m.content if isinstance(m.content, str) else str(m.content)
    return ""
