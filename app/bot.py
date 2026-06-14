"""Bot/Dispatcher factory, middleware wiring, scheduler & lifecycle hooks."""
from __future__ import annotations

import asyncio

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import BotCommand
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import settings
from app.constants import OrderStatus
from app.database import async_session_factory, dispose_engine
from app.handlers import register_routers
from app.logger import get_logger, setup_logging
from app.middlewares import (
    AuthMiddleware,
    DbSessionMiddleware,
    LoggingMiddleware,
    ThrottlingMiddleware,
)
from app.redis_client import close_redis, get_redis
from app.repositories.inventory_repo import InventoryRepository
from app.repositories.order_repo import OrderRepository
from app.repositories.system_repo import SystemRepository
from app.services.crypto_service import CryptoService

logger = get_logger(__name__)


def create_bot() -> Bot:
    return Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def create_dispatcher() -> Dispatcher:
    storage = RedisStorage.from_url(settings.redis_url)
    dp = Dispatcher(storage=storage)

    # Inner middlewares (run after aiogram's user-context middleware so that
    # event_from_user is available to AuthMiddleware).
    for observer in (dp.message, dp.callback_query):
        observer.middleware(DbSessionMiddleware())
        observer.middleware(AuthMiddleware())
        observer.middleware(ThrottlingMiddleware())
        observer.middleware(LoggingMiddleware())

    register_routers(dp)
    return dp


# ----------------------------------------------------------------------
# Lifecycle
# ----------------------------------------------------------------------
async def set_commands(bot: Bot) -> None:
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Open the marketplace"),
            BotCommand(command="home", description="Home page"),
            BotCommand(command="search", description="Search a category"),
            BotCommand(command="profile", description="Your profile"),
            BotCommand(command="rules", description="Marketplace rules"),
            BotCommand(command="contacts", description="Contact info"),
            BotCommand(command="cancel", description="Cancel current action"),
        ]
    )


async def load_runtime_settings() -> None:
    """Hydrate mutable settings (e.g. commission split) from the database."""
    async with async_session_factory() as session:
        value = await SystemRepository(session).get("default_seller_percent")
        if value and value.isdigit():
            pct = int(value)
            settings.default_seller_percent = pct
            settings.default_owner_percent = 100 - pct
            logger.info("Loaded commission split from DB: seller %s%%", pct)


# ----------------------------------------------------------------------
# Scheduled maintenance
# ----------------------------------------------------------------------
async def release_expired_reservations() -> None:
    async with async_session_factory() as session:
        try:
            inv = InventoryRepository(session)
            orders = OrderRepository(session)
            expired = await orders.expired_reservations()
            for order in expired:
                await inv.release_reservation(order.id)
                await orders.set_status(order.id, OrderStatus.EXPIRED)
            await inv.release_expired()
            await session.commit()
            if expired:
                logger.info("Released %s expired reservation(s).", len(expired))
        except Exception:  # noqa: BLE001
            await session.rollback()
            logger.exception("Failed releasing expired reservations")


async def poll_deposits(bot: Bot) -> None:
    async with async_session_factory() as session:
        try:
            confirmed = await CryptoService(session).check_pending_payments()
            await session.commit()
        except Exception:  # noqa: BLE001
            await session.rollback()
            logger.exception("Deposit polling failed")
            return
    if confirmed:
        logger.info("Confirmed %s deposit(s).", len(confirmed))
        for note in confirmed:
            try:
                await bot.send_message(
                    note["telegram_id"],
                    "✅ <b>Deposit confirmed!</b>\n"
                    f"{settings.currency_symbol}{note['amount']} has been credited to your balance.",
                )
            except Exception:  # noqa: BLE001
                pass


def start_scheduler(bot: Bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=settings.timezone)
    scheduler.add_job(release_expired_reservations, "interval", seconds=60, id="reservations")
    scheduler.add_job(poll_deposits, "interval", seconds=120, id="deposits", args=[bot])
    scheduler.start()
    return scheduler


async def on_startup(bot: Bot) -> AsyncIOScheduler:
    setup_logging()
    await load_runtime_settings()
    await set_commands(bot)
    # warm redis connection
    await get_redis().ping()
    scheduler = start_scheduler(bot)
    me = await bot.get_me()
    logger.info("Bot @%s started. Owners: %s", me.username, settings.owner_ids)
    return scheduler


async def on_shutdown(scheduler: AsyncIOScheduler) -> None:
    logger.info("Shutting down...")
    scheduler.shutdown(wait=False)
    await close_redis()
    await dispose_engine()
