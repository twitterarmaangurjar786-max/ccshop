"""Track online users via Redis with a short TTL."""
from __future__ import annotations

from app.constants import ONLINE_TTL_SECONDS, RK_ONLINE
from app.redis_client import get_redis


async def mark_online(user_id: int) -> None:
    redis = get_redis()
    await redis.set(RK_ONLINE.format(user_id=user_id), "1", ex=ONLINE_TTL_SECONDS)


async def online_count() -> int:
    redis = get_redis()
    count = 0
    async for _ in redis.scan_iter(match="online:*", count=500):
        count += 1
    return count
