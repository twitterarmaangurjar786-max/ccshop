"""Seller data access."""
from __future__ import annotations

from decimal import Decimal
from typing import Optional, Sequence

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import SellerStatus
from app.models import Seller


class SellerRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, seller_id: int) -> Optional[Seller]:
        return await self.session.get(Seller, seller_id)

    async def get_by_user_id(self, user_id: int) -> Optional[Seller]:
        res = await self.session.execute(
            select(Seller).where(Seller.user_id == user_id)
        )
        return res.scalar_one_or_none()

    async def get_by_telegram_id(self, telegram_id: int) -> Optional[Seller]:
        res = await self.session.execute(
            select(Seller).where(Seller.telegram_id == telegram_id)
        )
        return res.scalar_one_or_none()

    async def get_by_name(self, name: str) -> Optional[Seller]:
        res = await self.session.execute(
            select(Seller).where(func.lower(Seller.seller_name) == name.lower())
        )
        return res.scalar_one_or_none()

    async def create(
        self,
        user_id: int,
        telegram_id: int,
        seller_name: str,
        seller_percent: Optional[int] = None,
    ) -> Seller:
        seller = Seller(
            user_id=user_id,
            telegram_id=telegram_id,
            seller_name=seller_name,
            seller_percent=seller_percent,
            status=SellerStatus.ACTIVE,
        )
        self.session.add(seller)
        await self.session.flush()
        return seller

    async def set_status(self, seller_id: int, status: SellerStatus) -> None:
        await self.session.execute(
            update(Seller).where(Seller.id == seller_id).values(status=status)
        )

    async def list_all(
        self, include_removed: bool = False
    ) -> Sequence[Seller]:
        stmt = select(Seller).order_by(Seller.created_at.desc())
        if not include_removed:
            stmt = stmt.where(Seller.status != SellerStatus.REMOVED)
        res = await self.session.execute(stmt)
        return res.scalars().all()

    async def list_active(self) -> Sequence[Seller]:
        res = await self.session.execute(
            select(Seller)
            .where(Seller.status == SellerStatus.ACTIVE)
            .order_by(Seller.seller_name)
        )
        return res.scalars().all()

    async def count(self) -> int:
        res = await self.session.execute(
            select(func.count(Seller.id)).where(Seller.status != SellerStatus.REMOVED)
        )
        return int(res.scalar() or 0)

    async def add_sale(self, seller_id: int, amount: Decimal, quantity: int) -> None:
        await self.session.execute(
            update(Seller)
            .where(Seller.id == seller_id)
            .values(
                total_sales=Seller.total_sales + quantity,
                total_revenue=Seller.total_revenue + amount,
            )
        )
