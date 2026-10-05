# backend/core/retry.py
# 三层兜底机制：自动重试 → Agent 级降级 → 系统级兜底

import asyncio                                   # 异步：用于超时控制和等待
from functools import wraps                      # @wraps：装饰器里保留原函数的名字/文档
from typing import Callable, Any, Optional       # 类型注解：可调用对象 / 任意 / 可选

from backend.core.exceptions import (            # 引入 3.3 定义的异常（已去掉 Judge0 的 Sandbox 异常）
    LLMAPIError,
    MilvusConnectionError,
    InvalidInputError,
    AuthenticationError,
)
from backend.core.logger import get_logger,configure_logging
logger = get_logger(__name__)

# ── 异常分类 ───────────────────────────────────────────────
# 可重试：多半是短暂故障（网络抖动、超时），重试一下可能就好
RETRYABLE_ERRORS = (
    LLMAPIError,
    MilvusConnectionError,
    TimeoutError,
    ConnectionError,
)
# 不可重试：重试也没用（输入非法、认证失败），应立即抛出
NON_RETRYABLE_ERRORS = (
    InvalidInputError,
    AuthenticationError,
)

MAX_RETRIES = 3                  # 最多重试 3 次（加上首次 = 共 4 次尝试）
RETRY_DELAYS = [1.0, 2.0, 4.0]   # 指数退避：1s / 2s / 4s
TIMEOUT_PER_ATTEMPT = 30.0       # 单次调用最多等 30 秒，超时算失败


def with_retry(agent_type: str = ""):
    """三层兜底装饰器工厂。给异步函数套上「重试 → 降级 → 系统兜底」三层保护。

    用法：
        @with_retry(agent_type="qa")
        async def _invoke():
            return await graph.ainvoke(state, config=config)
    """
    def decorator(func: Callable) -> Callable:       # 中间层：接收被装饰的函数
        @wraps(func)                                 # 保留原函数的元信息（名字、docstring）
        async def wrapper(*args, **kwargs) -> Any:   # 最内层：真正的执行逻辑

            # ── 第一层：自动重试 ──────────────────────────
            # last_error可以为Exception类型，也可以为None
            last_error: Optional[Exception] = None   # 记录最后一次的错误，留给后面降级用
            for attempt in range(MAX_RETRIES + 1):   # 循环 3 次：attempt = 0, 1, 2
                try:
                    # 给单次调用套一个超时；超过 30 秒就抛 TimeoutError
                    # 只要错误不在不可重试错误元组中，都会进行重试2次，包括超时错误
                    result = await asyncio.wait_for(
                        func(*args, **kwargs),
                        timeout=TIMEOUT_PER_ATTEMPT,
                    )
                    if attempt > 0:                  # 如果是重试后成功的，记一条日志
                        logger.info("retry.succeeded", agent_type=agent_type, attempt=attempt + 1)
                    return result                    # 成功，直接返回，结束

                except NON_RETRYABLE_ERRORS as e:    # 不可重试异常：立即抛出，不再重试
                    logger.warning("retry.non_retryable_error", agent_type=agent_type, error=str(e))
                    raise                            # 原样抛出，交给上层处理

                except Exception as e:               # 其它（可重试）异常
                    last_error = e                   # 记下来
                    if attempt < MAX_RETRIES:        # 还没到上限：等待后重试
                        delay = RETRY_DELAYS[attempt]
                        logger.warning(
                            "retry.attempt_failed", agent_type=agent_type,
                            attempt=attempt + 1, max_retries=MAX_RETRIES, delay=delay, error=str(e),
                        )
                        await asyncio.sleep(delay)   # 等 1s 或 3s 再重试
                    else:                            # 到上限了：记录失败，跳出循环去降级
                        logger.error("retry.all_attempts_failed", agent_type=agent_type, error=str(e))

            # ── 第二层：Agent 级降级 ──────────────────────
            try:
                fallback_result = await AgentFallbackHandler.handle(  # 按 agent_type 找降级策略
                    agent_type=agent_type, original_error=last_error,
                )
                logger.info("retry.fallback_succeeded", agent_type=agent_type)
                return fallback_result               # 降级成功，返回降级结果
            except Exception as fallback_error:      # 连降级都失败
                logger.error("retry.fallback_failed", agent_type=agent_type, error=str(fallback_error))

            # ── 第三层：系统级兜底 ────────────────────────
            logger.error("retry.system_fallback", agent_type=agent_type, original_error=str(last_error))
            return _system_fallback_response(agent_type)  # 最后的保底，永远不会再失败
        return wrapper
    return decorator



class AgentFallbackHandler:
    """第二层降级：各 Agent 的专项降级策略（尽量保留核心功能，退化为更简单的实现）。"""

    @classmethod
    async def handle(cls, agent_type: str, original_error: Exception) -> Any:
        """根据 agent_type 选择对应的降级策略。"""
        fallback_map = {                              # 类型 → 降级方法 的映射表
            "qa":               cls._qa_fallback,
            "order":            cls._order_fallback,      # P3 客服新 Agent
            "aftersale":        cls._aftersale_fallback,
            "complaint":        cls._complaint_fallback,
        }
        handler = fallback_map.get(agent_type)        # 查表
        if handler:
            return await handler()
        raise original_error                          # 没有对应降级策略，原样抛出（交给系统兜底）

    @classmethod
    async def _qa_fallback(cls) -> dict:
        """问答降级：知识库或模型不可用，返回提示语。"""
        logger.info("fallback.qa_service_unavailable")
        return {
            "fallback_used": True, # 是否用到了错误回调
            "content": "⚠️ 知识库检索暂时不可用，请稍后重试，或转人工客服为你处理。",
            "structured_output": None, # 结构化输出
        }

    @classmethod
    async def _order_fallback(cls) -> dict:
        """订单查询降级：订单系统不可用 → 转人工。"""
        logger.info("fallback.order_service_unavailable")
        return {
            "fallback_used": True,
            "content": "订单系统暂时繁忙，暂时无法查询。已为你转接人工客服，请稍候。",
            "need_human": True,
            "structured_output": None,
        }

    @classmethod
    async def _aftersale_fallback(cls) -> dict:
        """售后降级：审核链路不可用 → 转人工。"""
        logger.info("fallback.aftersale_service_unavailable")
        return {
            "fallback_used": True,
            "content": "售后审核服务暂时不可用，你的申请已记录，将转人工客服继续处理。",
            "need_human": True,
            "structured_output": None,
        }

    @classmethod
    async def _complaint_fallback(cls) -> dict:
        """投诉降级：直接转人工（情绪场景优先保人工兜底）。"""
        logger.info("fallback.complaint_to_human")
        return {
            "fallback_used": True,
            "content": "非常抱歉给你带来不好的体验，已为你优先转接人工专员处理，请稍候。",
            "need_human": True,
            "structured_output": None,
        }


def _system_fallback_response(agent_type: str) -> dict:
    """第三层：系统级兜底。所有降级都失败后返回它，保证用户始终能收到响应。"""
    messages = {                                      # 按 agent_type 给不同的友好提示
        "qa":        "非常抱歉，商品咨询服务暂时不可用，请稍后再试，或转人工客服为你处理。",
        "order":     "非常抱歉，订单查询服务暂时不可用，已为你转接人工客服，请稍候。",
        "aftersale": "非常抱歉，售后服务暂时不可用，你的申请已记录，将转人工客服继续处理。",
        "complaint": "非常抱歉给你带来不好的体验，已优先转接人工专员，请稍候。",
    }
    content = messages.get(agent_type, "服务暂时不可用，请稍后再试。")  # 找不到就用通用提示
    return {
        "messages": [],
        "content": content,
        "fallback_used": True,
        "system_fallback": True,                      # 标记：走到了最后一层系统兜底
        "structured_output": None,
    }
