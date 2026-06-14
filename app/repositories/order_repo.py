"""Order and Purchase data access."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, Sequence

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import OrderStatus
from app.models import Order, Purchase


class OrderRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, **kwargs) -> Order:
        order = Order(**kwargs)
        self.session.add(order)
        await self.session.flush()
        return order

    async def get(self, order_id: int) -> Optional[Order]:
        return await self.session.get(Order, order_id)

    async def get_for_update(self, order_id: int) -> Optional[Order]:
        res = await self.session.execute(
            select(Order).where(Order.id == order_id).with_for_update()
        )
        return res.scalar_one_or_none()

    async def set_status(self, order_id: int, status: OrderStatus) -> None:
        values = {"status": status}
        if status == OrderStatus.DELIVERED:
            values["delivered_at"] = datetime.now(timezone.utc)
        if status == OrderStatus.PAID:
            values["paid_at"] = datetime.now(timezone.utc)
        await self.session.execute(
            update(Order).where(Order.id == order_id).values(**values)
        )

    async def add_purchases(self, rows: Sequence[dict]) -> None:
        if not rows:
            return
        self.session.add_all([Purchase(**r) for r in rows])
        await self.session.flush()

    async def buyer_orders(
        self, buyer_id: int, limit: int = 20
    ) -> Sequence[Order]:
        res = await self.session.execute(
            select(Order)
            .where(Order.buyer_id == buyer_id, Order.status == OrderStatus.DELIVERED)
            .order_by(Order.created_at.desc())
            .limit(limit)
        )
        return res.scalars().all()

    async def seller_sales(self, seller_id: int, limit: int = 30) -> Sequence[Order]:
        res = await self.session.execute(
            select(Order)
            .where(Order.seller_id == seller_id, Order.status == OrderStatus.DELIVERED)
            .order_by(Order.created_at.desc())
            .limit(limit)
        )
        return res.scalars().all()

    async def order_purchases(self, order_id: int) -> Sequence[Purchase]:
        res = await self.session.execute(
            select(Purchase).where(Purchase.order_id == order_id).order_by(Purchase.id)
        )
        return res.scalars().all()

    async def expired_reservations(self) -> Sequence[Order]:
        now = datetime.now(timezone.utc)
        res = await self.session.execute(
            select(Order).where(
                Order.status == OrderStatus.RESERVED,
                Order.reserved_until < now,
            )
        )
        return res.scalars().all()

    # --- statistics ---
    async def total_sales_count(self) -> int:
        res = await self.session.execute(
            select(func.count(Order.id)).where(Order.status == OrderStatus.DELIVERED)
        )
        return int(res.scalar() or 0)

    async def total_sales_amount(self) -> Decimal:
        res = await self.session.execute(
            select(func.coalesce(func.sum(Order.total), 0)).where(
                Order.status == OrderStatus.DELIVERED
            )
        )
        return Decimal(res.scalar() or 0)

    async def seller_sales_amount(self, seller_id: int) -> Decimal:
        res = await self.session.execute(
            select(func.coalesce(func.sum(Order.total), 0)).where(
                Order.seller_id == seller_id, Order.status == OrderStatus.DELIVERED
            )
        )
        return Decimal(res.scalar() or 0)

    async def seller_sales_count(self, seller_id: int) -> int:
        res = await self.session.execute(
            select(func.coalesce(func.sum(Order.quantity), 0)).where(
                Order.seller_id == seller_id, Order.status == OrderStatus.DELIVERED
            )
        )
        return int(res.scalar() or 0)
