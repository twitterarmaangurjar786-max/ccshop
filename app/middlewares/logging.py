"""Lightweight request logging."""
from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from app.logger import get_logger

logger = get_logger("requests")


class LoggingMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tg_user = data.get("event_from_user")
        uid = tg_user.id if tg_user else "?"
        if isinstance(event, Message):
            logger.info("msg uid=%s text=%r", uid, (event.text or event.caption or "<media>")[:64])
        elif isinstance(event, CallbackQuery):
            logger.info("cb  uid=%s data=%r", uid, event.data)
        return await handler(event, data)
