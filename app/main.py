"""Application entrypoint: starts long-polling."""
from __future__ import annotations

import asyncio

from app.bot import create_bot, create_dispatcher, on_shutdown, on_startup
from app.logger import get_logger

logger = get_logger(__name__)


async def main() -> None:
    bot = create_bot()
    dp = create_dispatcher()

    scheduler = await on_startup(bot)
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await on_shutdown(scheduler)
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped.")
