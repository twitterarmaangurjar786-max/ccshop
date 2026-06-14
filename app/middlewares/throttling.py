"""Redis-backed rate limiting / anti-spam."""
from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from app.config import settings
from app.constants import RK_RATE_LIMIT
from app.redis_client import get_redis


class ThrottlingMiddleware(BaseMiddleware):
    def __init__(self, limit: int | None = None, window: int = 1):
        self.limit = limit or settings.rate_limit_per_second
        self.window = window

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tg_user = data.get("event_from_user")
        if tg_user is None:
            return await handler(event, data)

        redis = get_redis()
        key = RK_RATE_LIMIT.format(user_id=tg_user.id)
        try:
            current = await redis.incr(key)
            if current == 1:
                await redis.expire(key, self.window)
        except Exception:
            # Never block traffic on a Redis hiccup
            return await handler(event, data)

        if current > self.limit:
            if isinstance(event, CallbackQuery):
                await event.answer("⏳ Slow down, please.", show_alert=False)
            elif isinstance(event, Message):
                # Silently drop spam beyond a small threshold
                if current <= self.limit + 1:
                    await event.answer("⏳ You're sending requests too fast.")
            return None

        return await handler(event, data)
