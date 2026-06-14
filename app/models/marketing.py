"""Marketing models: Coupon, CouponRedemption, Banner, Broadcast, PreOrder."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.constants import BannerType, BroadcastTarget, CouponType, PreOrderStatus
from app.models.base import Base, IDMixin, TimestampMixin


class Coupon(IDMixin, TimestampMixin, Base):
    __tablename__ = "coupons"

    code: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    type: Mapped[CouponType] = mapped_column(String(16), nullable=False)
    value: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    min_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), default=Decimal("0.00"), nullable=False
    )
    expiry: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    usage_limit: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # 0 = unlimited
    used_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class CouponRedemption(IDMixin, Base):
    __tablename__ = "coupon_redemptions"
    __table_args__ = (
        UniqueConstraint("coupon_id", "user_id", name="uq_coupon_user"),
    )

    coupon_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("coupons.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Banner(IDMixin, TimestampMixin, Base):
    __tablename__ = "banners"

    type: Mapped[BannerType] = mapped_column(String(16), default=BannerType.IMAGE, nullable=False)
    file_id: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    caption: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    button_text: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    button_url: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class Broadcast(IDMixin, Base):
    __tablename__ = "broadcasts"

    owner_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    target: Mapped[BroadcastTarget] = mapped_column(
        String(16), default=BroadcastTarget.ALL, nullable=False
    )
    content_type: Mapped[str] = mapped_column(String(16), default="text", nullable=False)
    text: Mapped[Optional[str]] = mapped_column(String(4096), nullable=True)
    file_id: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)

    delivered: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    blocked: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class PreOrder(IDMixin, Base):
    __tablename__ = "preorders"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    category: Mapped[str] = mapped_column(String(6), nullable=False, index=True)
    quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    max_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2), nullable=True)
    status: Mapped[PreOrderStatus] = mapped_column(
        String(16), default=PreOrderStatus.WAITING, nullable=False, index=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    notified_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
