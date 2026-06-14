"""Resolve (or create) the user, attach role, block banned users, mark online."""
from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject, User as TgUser

from app.constants import Role
from app.services.online_service import mark_online
from app.services.user_service import UserService


class AuthMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tg_user: TgUser | None = data.get("event_from_user")
        session = data.get("session")
        if tg_user is None or session is None:
            return await handler(event, data)

        # Extract referral payload from /start <code>
        referral_code = None
        if isinstance(event, Message) and event.text and event.text.startswith("/start"):
            parts = event.text.split(maxsplit=1)
            if len(parts) == 2:
                referral_code = parts[1].strip()

        service = UserService(session)
        user = await service.get_or_create(
            telegram_id=tg_user.id,
            username=tg_user.username,
            full_name=tg_user.full_name,
            referral_code=referral_code,
        )

        if user.is_blocked:
            if isinstance(event, Message):
                await event.answer("⛔ You are blocked from using this bot.")
            elif isinstance(event, CallbackQuery):
                await event.answer("⛔ You are blocked.", show_alert=True)
            return None

        role = await service.resolve_role(user)
        data["user"] = user
        data["role"] = role
        data["is_owner"] = role == Role.OWNER
        data["is_seller"] = role == Role.SELLER

        await mark_online(user.id)
        return await handler(event, data)
