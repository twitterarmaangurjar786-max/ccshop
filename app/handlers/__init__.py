"""Router registration."""
from __future__ import annotations

from aiogram import Dispatcher

from app.handlers import buyer, common, owner, seller


def register_routers(dp: Dispatcher) -> None:
    # Order matters: owner & seller specific routers first, buyer/common last.
    dp.include_router(common.router)
    dp.include_router(owner.router)
    dp.include_router(seller.router)
    dp.include_router(buyer.router)
