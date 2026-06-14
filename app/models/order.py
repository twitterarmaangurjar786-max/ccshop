"""Order and Purchase models."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.constants import OrderStatus
from app.models.base import Base, IDMixin


class Order(IDMixin, Base):
    __tablename__ = "orders"

    buyer_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    seller_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sellers.id", ondelete="CASCADE"), nullable=False
    )
    seller_inventory_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("seller_inventory.id", ondelete="CASCADE"), nullable=False
    )
    category: Mapped[str] = mapped_column(String(6), nullable=False)

    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    discount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), default=Decimal("0.00"), nullable=False
    )
    total: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)

    coupon_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("coupons.id", ondelete="SET NULL"), nullable=True
    )

    status: Mapped[OrderStatus] = mapped_column(
        String(16), default=OrderStatus.RESERVED, nullable=False, index=True
    )
    reserved_until: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    purchases: Mapped[list["Purchase"]] = relationship(
        back_populates="order", cascade="all, delete-orphan"
    )


class Purchase(IDMixin, Base):
    """A single delivered line belonging to an order (kept for history/export)."""

    __tablename__ = "purchases"

    order_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("orders.id", ondelete="CASCADE"), index=True, nullable=False
    )
    buyer_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    seller_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sellers.id", ondelete="CASCADE"), nullable=False
    )
    line_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    line_data: Mapped[str] = mapped_column(String(1024), nullable=False)
    category: Mapped[str] = mapped_column(String(6), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    order: Mapped["Order"] = relationship(back_populates="purchases")
