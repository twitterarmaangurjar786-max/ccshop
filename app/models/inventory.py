"""Inventory models: SellerInventory (offer per category) and InventoryLine."""
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
    Index,
    func,
)

from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IDMixin, TimestampMixin


class SellerInventory(IDMixin, TimestampMixin, Base):
    """A seller's offer for an auto-generated category (first 6 digits)."""

    __tablename__ = "seller_inventory"
    __table_args__ = (
        UniqueConstraint("seller_id", "category", name="uq_seller_category"),
        Index("ix_seller_inventory_category", "category"),
    )

    seller_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sellers.id", ondelete="CASCADE"), nullable=False
    )
    category: Mapped[str] = mapped_column(String(6), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)

    total_lines: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sold_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    first_sale_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    seller = relationship("Seller")
    lines: Mapped[list["InventoryLine"]] = relationship(
        back_populates="inventory", cascade="all, delete-orphan"
    )

    @property
    def remaining(self) -> int:
        return self.total_lines - self.sold_count

    @property
    def can_edit_price(self) -> bool:
        return self.first_sale_at is None


class InventoryLine(IDMixin, Base):
    """A single redeem-code line. The first 6 chars of the line define the category."""

    __tablename__ = "inventory_lines"
    __table_args__ = (
        UniqueConstraint("content_hash", name="uq_line_hash"),
        Index("ix_lines_inventory_state", "seller_inventory_id", "is_sold", "is_reserved"),
        Index("ix_lines_category", "category"),
    )

    seller_inventory_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("seller_inventory.id", ondelete="CASCADE"), nullable=False
    )
    seller_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sellers.id", ondelete="CASCADE"), nullable=False
    )
    category: Mapped[str] = mapped_column(String(6), nullable=False, index=True)

    line_data: Mapped[str] = mapped_column(String(1024), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    is_sold: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    is_reserved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    reserved_until: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reserved_by_order_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    order_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    sold_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    inventory = relationship("SellerInventory", back_populates="lines")
