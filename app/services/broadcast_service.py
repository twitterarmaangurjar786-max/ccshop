"""Broadcast delivery with per-recipient result counting."""
from __future__ import annotations

import asyncio
from typing import Optional, Sequence

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter

from app.logger import get_logger

logger = get_logger(__name__)


async def send_broadcast(
    bot: Bot,
    chat_ids: Sequence[int],
    *,
    content_type: str = "text",
    text: Optional[str] = None,
    file_id: Optional[str] = None,
) -> tuple[int, int, int]:
    """Send a broadcast to ``chat_ids``.

    Returns ``(delivered, failed, blocked)``.
    """
    delivered = failed = blocked = 0
    for chat_id in chat_ids:
        try:
            if content_type == "photo" and file_id:
                await bot.send_photo(chat_id, file_id, caption=text)
            elif content_type == "video" and file_id:
                await bot.send_video(chat_id, file_id, caption=text)
            elif content_type == "document" and file_id:
                await bot.send_document(chat_id, file_id, caption=text)
            else:
                await bot.send_message(chat_id, text or "")
            delivered += 1
        except TelegramForbiddenError:
            blocked += 1
        except TelegramRetryAfter as exc:
            await asyncio.sleep(exc.retry_after)
            try:
                await bot.send_message(chat_id, text or "")
                delivered += 1
            except Exception:
                failed += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("Broadcast to %s failed: %s", chat_id, exc)
            failed += 1
        await asyncio.sleep(0.05)  # ~20 msgs/sec, respect Telegram limits
    return delivered, failed, blocked
