"""Coupons, Banners, Broadcasts, PreOrders data access."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Sequence

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import PreOrderStatus
from app.models import (
    Banner,
    Broadcast,
    Coupon,
    CouponRedemption,
    PreOrder,
)


class MarketingRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    # ----- Coupons -----
    async def create_coupon(self, **kwargs) -> Coupon:
        coupon = Coupon(**kwargs)
        self.session.add(coupon)
        await self.session.flush()
        return coupon

    async def get_coupon_by_code(self, code: str) -> Optional[Coupon]:
        res = await self.session.execute(
            select(Coupon).where(func.lower(Coupon.code) == code.lower())
        )
        return res.scalar_one_or_none()

    async def list_coupons(self) -> Sequence[Coupon]:
        res = await self.session.execute(select(Coupon).order_by(Coupon.created_at.desc()))
        return res.scalars().all()

    async def increment_coupon_use(self, coupon_id: int) -> None:
        await self.session.execute(
            update(Coupon)
            .where(Coupon.id == coupon_id)
            .values(used_count=Coupon.used_count + 1)
        )

    async def set_coupon_active(self, coupon_id: int, active: bool) -> None:
        await self.session.execute(
            update(Coupon).where(Coupon.id == coupon_id).values(is_active=active)
        )

    async def has_redeemed(self, coupon_id: int, user_id: int) -> bool:
        res = await self.session.execute(
            select(func.count(CouponRedemption.id)).where(
                CouponRedemption.coupon_id == coupon_id,
                CouponRedemption.user_id == user_id,
            )
        )
        return bool(res.scalar())

    async def add_redemption(self, coupon_id: int, user_id: int) -> None:
        self.session.add(CouponRedemption(coupon_id=coupon_id, user_id=user_id))
        await self.session.flush()

    # ----- Banners -----
    async def create_banner(self, **kwargs) -> Banner:
        banner = Banner(**kwargs)
        self.session.add(banner)
        await self.session.flush()
        return banner

    async def list_banners(self, only_active: bool = False) -> Sequence[Banner]:
        stmt = select(Banner).order_by(Banner.sort_order, Banner.id)
        if only_active:
            stmt = stmt.where(Banner.is_active.is_(True))
        res = await self.session.execute(stmt)
        return res.scalars().all()

    async def get_banner(self, banner_id: int) -> Optional[Banner]:
        return await self.session.get(Banner, banner_id)

    async def set_banner_active(self, banner_id: int, active: bool) -> None:
        await self.session.execute(
            update(Banner).where(Banner.id == banner_id).values(is_active=active)
        )

    async def delete_banner(self, banner_id: int) -> None:
        banner = await self.session.get(Banner, banner_id)
        if banner:
            await self.session.delete(banner)

    # ----- Broadcasts -----
    async def create_broadcast(self, **kwargs) -> Broadcast:
        broadcast = Broadcast(**kwargs)
        self.session.add(broadcast)
        await self.session.flush()
        return broadcast

    async def finalize_broadcast(
        self, broadcast_id: int, delivered: int, failed: int, blocked: int
    ) -> None:
        await self.session.execute(
            update(Broadcast)
            .where(Broadcast.id == broadcast_id)
            .values(
                delivered=delivered,
                failed=failed,
                blocked=blocked,
                finished_at=datetime.now(timezone.utc),
            )
        )

    # ----- PreOrders -----
    async def create_preorder(self, **kwargs) -> PreOrder:
        preorder = PreOrder(**kwargs)
        self.session.add(preorder)
        await self.session.flush()
        return preorder

    async def user_preorders(self, user_id: int) -> Sequence[PreOrder]:
        res = await self.session.execute(
            select(PreOrder)
            .where(PreOrder.user_id == user_id)
            .order_by(PreOrder.created_at.desc())
        )
        return res.scalars().all()

    async def waiting_preorders_for_category(self, category: str) -> Sequence[PreOrder]:
        res = await self.session.execute(
            select(PreOrder).where(
                PreOrder.category == category,
                PreOrder.status == PreOrderStatus.WAITING,
            )
        )
        return res.scalars().all()

    async def mark_preorder_notified(self, preorder_id: int) -> None:
        await self.session.execute(
            update(PreOrder)
            .where(PreOrder.id == preorder_id)
            .values(status=PreOrderStatus.NOTIFIED, notified_at=datetime.now(timezone.utc))
        )

    async def cancel_preorder(self, preorder_id: int) -> None:
        await self.session.execute(
            update(PreOrder)
            .where(PreOrder.id == preorder_id)
            .values(status=PreOrderStatus.CANCELLED)
        )
