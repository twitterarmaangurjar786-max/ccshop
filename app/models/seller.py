"""Seller model."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.constants import SellerStatus
from app.models.base import Base, IDMixin, TimestampMixin


class Seller(IDMixin, TimestampMixin, Base):
    __tablename__ = "sellers"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    telegram_id: Mapped[int] = mapped_column(
        BigInteger, unique=True, index=True, nullable=False
    )
    seller_name: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False
    )
    status: Mapped[SellerStatus] = mapped_column(
        String(16), default=SellerStatus.ACTIVE, nullable=False
    )

    # Commission override (percentage the seller keeps). Falls back to settings default.
    seller_percent: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    total_sales: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_revenue: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), default=Decimal("0.00"), nullable=False
    )

    join_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user = relationship("User", back_populates="seller")
