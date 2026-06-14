"""Coupon validation and redemption."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import NamedTuple, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import CouponType
from app.models import Coupon
from app.repositories.marketing_repo import MarketingRepository
from app.services.exceptions import CouponError


class CouponPreview(NamedTuple):
    coupon: Coupon
    discount: Decimal


class CouponService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.marketing = MarketingRepository(session)

    async def preview(
        self, code: str, user_id: int, amount: Decimal
    ) -> CouponPreview:
        coupon = await self.marketing.get_coupon_by_code(code.strip())
        if coupon is None or not coupon.is_active:
            raise CouponError("Invalid or inactive coupon.")
        if coupon.expiry and coupon.expiry < datetime.now(timezone.utc):
            raise CouponError("This coupon has expired.")
        if coupon.usage_limit and coupon.used_count >= coupon.usage_limit:
            raise CouponError("This coupon reached its usage limit.")
        if amount < coupon.min_amount:
            raise CouponError(
                f"Minimum order amount for this coupon is {coupon.min_amount}."
            )
        if await self.marketing.has_redeemed(coupon.id, user_id):
            raise CouponError("You have already used this coupon.")

        if coupon.type == CouponType.PERCENT:
            discount = (amount * coupon.value / Decimal(100)).quantize(Decimal("0.01"))
        else:
            discount = Decimal(coupon.value)
        discount = min(discount, amount).quantize(Decimal("0.01"))
        return CouponPreview(coupon, discount)

    async def redeem(self, coupon_id: int, user_id: int) -> None:
        await self.marketing.increment_coupon_use(coupon_id)
        await self.marketing.add_redemption(coupon_id, user_id)
