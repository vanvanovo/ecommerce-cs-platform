# backend/core/cache.py
# Redis 工具层（P6）：缓存 / 分布式锁 / 指标计数
#
# 设计原则：全部优雅降级——Redis 不可用时缓存返回 None、锁直接放行、指标静默，
# 业务主链路绝不因为缓存故障而中断（复用 EduAgent 的"永不失败"思路）。

from __future__ import annotations

import asyncio
import json
import uuid as uuid_lib
from contextlib import asynccontextmanager
from typing import Any, Optional

from backend.config import get_settings
from backend.core.logger import get_logger

logger = get_logger(__name__)

_redis_client = None
_redis_failed = False

# TTL 约定
TTL_ROUTE = 600          # 路由决策 10 分钟
TTL_POLICY = 1800        # 政策类检索 30 分钟
TTL_LOGISTICS = 300      # 物流轨迹 5 分钟


def _get_client():
    global _redis_client, _redis_failed
    if _redis_client is None and not _redis_failed:
        try:
            import redis.asyncio as aioredis

            _redis_client = aioredis.from_url(
                get_settings().redis_url,
                decode_responses=True,
                socket_connect_timeout=1.5,
                socket_timeout=2.0,
            )
        except Exception as e:  # noqa: BLE001
            _redis_failed = True
            logger.warning("cache.client_init_failed", error=str(e)[:150])
    return _redis_client


async def cache_get(key: str) -> Optional[Any]:
    client = _get_client()
    if not client:
        return None
    try:
        raw = await client.get(key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except Exception:  # noqa: BLE001
            return raw
    except Exception as e:  # noqa: BLE001
        logger.warning("cache.get_failed", key=key[:60], error=str(e)[:120])
        return None


async def cache_set(key: str, value: Any, ttl: int = TTL_ROUTE) -> None:
    client = _get_client()
    if not client:
        return
    try:
        raw = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
        await client.set(key, raw, ex=ttl)
    except Exception as e:  # noqa: BLE001
        logger.warning("cache.set_failed", key=key[:60], error=str(e)[:120])


@asynccontextmanager
async def redis_lock(name: str, ttl: int = 10, wait: float = 2.0):
    """写操作防并发：SET NX EX 抢锁，抢不到短暂等待后抛 TimeoutError。

    Redis 不可用 → 直接放行（降级，不阻断业务）。
    """
    client = _get_client()
    if not client:
        yield True
        return

    token = uuid_lib.uuid4().hex
    key = f"lock:{name}"
    acquired = False
    deadline = asyncio.get_event_loop().time() + wait
    try:
        while True:
            try:
                acquired = bool(await client.set(key, token, nx=True, ex=ttl))
            except Exception as e:  # noqa: BLE001
                logger.warning("lock.redis_error_pass", name=name, error=str(e)[:120])
                yield True
                return
            if acquired:
                break
            if asyncio.get_event_loop().time() > deadline:
                raise TimeoutError(f"获取锁失败（key={key}）")
            await asyncio.sleep(0.1)
        yield True
    finally:
        if acquired:
            try:
                current = await client.get(key)
                if current == token:
                    await client.delete(key)
            except Exception:  # noqa: BLE001
                pass


async def incr_metric(name: str, amount: int = 1) -> None:
    """指标计数（监控埋点）：metric:<name>。失败静默。"""
    client = _get_client()
    if not client:
        return
    try:
        await client.incrby(f"metric:{name}", amount)
    except Exception:  # noqa: BLE001
        pass


async def get_metrics() -> dict[str, int]:
    """读取全部指标计数（供监控接口展示）。"""
    client = _get_client()
    if not client:
        return {}
    try:
        out: dict[str, int] = {}
        async for key in client.scan_iter(match="metric:*"):
            out[key.replace("metric:", "")] = int(await client.get(key) or 0)
        return dict(sorted(out.items()))
    except Exception as e:  # noqa: BLE001
        logger.warning("cache.metrics_failed", error=str(e)[:120])
        return {}
