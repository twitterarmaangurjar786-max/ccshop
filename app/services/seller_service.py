"""Seller lifecycle managed exclusively by the Owner."""
from __future__ import annotations

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import Role, SellerStatus
from app.models import Seller
from app.repositories.seller_repo import SellerRepository
from app.repositories.system_repo import SystemRepository
from app.repositories.user_repo import UserRepository
from app.services.exceptions import InvalidInput, SellerExists, SellerNotFound


class SellerService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.sellers = SellerRepository(session)
        self.users = UserRepository(session)
        self.system = SystemRepository(session)

    async def add_seller(
        self,
        owner_id: int,
        telegram_id: int,
        seller_name: str,
        seller_percent: Optional[int] = None,
    ) -> Seller:
        seller_name = seller_name.strip()
        if not seller_name or len(seller_name) > 64:
            raise InvalidInput("Seller name must be 1-64 characters.")

        if await self.sellers.get_by_name(seller_name):
            raise SellerExists(f"Seller name '{seller_name}' is already taken.")
        if await self.sellers.get_by_telegram_id(telegram_id):
            raise SellerExists("This Telegram ID is already a seller.")

        # Ensure a user record exists for the future seller
        user = await self.users.get_by_telegram_id(telegram_id)
        if user is None:
            user = await self.users.create(
                telegram_id=telegram_id,
                username=None,
                full_name=seller_name,
                role=Role.SELLER,
            )
        else:
            await self.users.set_role(user.id, Role.SELLER)

        seller = await self.sellers.create(
            user_id=user.id,
            telegram_id=telegram_id,
            seller_name=seller_name,
            seller_percent=seller_percent,
        )
        await self.system.log(
            action="seller_added",
            actor_id=owner_id,
            entity="seller",
            entity_id=seller.id,
            detail={"telegram_id": telegram_id, "name": seller_name},
        )
        return seller

    async def remove_seller(self, owner_id: int, seller_id: int) -> Seller:
        seller = await self.sellers.get_by_id(seller_id)
        if seller is None:
            raise SellerNotFound("Seller not found.")
        await self.sellers.set_status(seller_id, SellerStatus.REMOVED)
        await self.users.set_role(seller.user_id, Role.BUYER)
        await self.system.log(
            action="seller_removed",
            actor_id=owner_id,
            entity="seller",
            entity_id=seller_id,
        )
        return seller

    async def suspend_seller(self, owner_id: int, seller_id: int) -> Seller:
        seller = await self.sellers.get_by_id(seller_id)
        if seller is None:
            raise SellerNotFound("Seller not found.")
        await self.sellers.set_status(seller_id, SellerStatus.SUSPENDED)
        await self.system.log(
            action="seller_suspended",
            actor_id=owner_id,
            entity="seller",
            entity_id=seller_id,
        )
        return seller

    async def unsuspend_seller(self, owner_id: int, seller_id: int) -> Seller:
        seller = await self.sellers.get_by_id(seller_id)
        if seller is None:
            raise SellerNotFound("Seller not found.")
        await self.sellers.set_status(seller_id, SellerStatus.ACTIVE)
        await self.users.set_role(seller.user_id, Role.SELLER)
        await self.system.log(
            action="seller_unsuspended",
            actor_id=owner_id,
            entity="seller",
            entity_id=seller_id,
        )
        return seller
