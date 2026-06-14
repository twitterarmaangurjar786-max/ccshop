"""Inventory data access: offers, lines, reservations, category aggregation."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Iterable, Optional, Sequence

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import SellerStatus
from app.models import InventoryLine, Seller, SellerInventory


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class InventoryRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    # ------------------------------------------------------------------
    # Duplicate detection
    # ------------------------------------------------------------------
    async def existing_hashes(self, candidate_hashes: Sequence[str]) -> set[str]:
        if not candidate_hashes:
            return set()
        found: set[str] = set()
        # chunk to avoid oversized IN clauses
        chunk = 5000
        for i in range(0, len(candidate_hashes), chunk):
            part = candidate_hashes[i : i + chunk]
            res = await self.session.execute(
                select(InventoryLine.content_hash).where(
                    InventoryLine.content_hash.in_(part)
                )
            )
            found.update(row[0] for row in res.all())
        return found

    # ------------------------------------------------------------------
    # Offers (SellerInventory)
    # ------------------------------------------------------------------
    async def get_offer(self, seller_inventory_id: int) -> Optional[SellerInventory]:
        return await self.session.get(SellerInventory, seller_inventory_id)

    async def get_offer_for_update(self, seller_inventory_id: int) -> Optional[SellerInventory]:
        res = await self.session.execute(
            select(SellerInventory)
            .where(SellerInventory.id == seller_inventory_id)
            .with_for_update()
        )
        return res.scalar_one_or_none()

    async def get_offer_by_seller_category(
        self, seller_id: int, category: str
    ) -> Optional[SellerInventory]:
        res = await self.session.execute(
            select(SellerInventory).where(
                SellerInventory.seller_id == seller_id,
                SellerInventory.category == category,
            )
        )
        return res.scalar_one_or_none()

    async def get_or_create_offer(
        self, seller_id: int, category: str, price: Decimal
    ) -> SellerInventory:
        offer = await self.get_offer_by_seller_category(seller_id, category)
        if offer is None:
            offer = SellerInventory(
                seller_id=seller_id,
                category=category,
                price=price,
                total_lines=0,
                sold_count=0,
            )
            self.session.add(offer)
            await self.session.flush()
        return offer

    async def set_price(self, seller_inventory_id: int, price: Decimal) -> None:
        await self.session.execute(
            update(SellerInventory)
            .where(SellerInventory.id == seller_inventory_id)
            .values(price=price)
        )

    async def increment_total(self, seller_inventory_id: int, count: int) -> None:
        await self.session.execute(
            update(SellerInventory)
            .where(SellerInventory.id == seller_inventory_id)
            .values(total_lines=SellerInventory.total_lines + count)
        )

    async def delete_offer(self, seller_inventory_id: int) -> None:
        offer = await self.session.get(SellerInventory, seller_inventory_id)
        if offer is not None:
            await self.session.delete(offer)

    # ------------------------------------------------------------------
    # Lines
    # ------------------------------------------------------------------
    async def bulk_insert_lines(self, rows: Iterable[dict]) -> int:
        rows = list(rows)
        if not rows:
            return 0
        self.session.add_all([InventoryLine(**r) for r in rows])
        await self.session.flush()
        return len(rows)

    async def available_count(self, seller_inventory_id: int) -> int:
        now = _utcnow()
        res = await self.session.execute(
            select(func.count(InventoryLine.id)).where(
                InventoryLine.seller_inventory_id == seller_inventory_id,
                InventoryLine.is_sold.is_(False),
                or_(
                    InventoryLine.is_reserved.is_(False),
                    InventoryLine.reserved_until < now,
                ),
            )
        )
        return int(res.scalar() or 0)

    # ------------------------------------------------------------------
    # Reservation (atomic, lock-based)
    # ------------------------------------------------------------------
    async def reserve_lines(
        self, seller_inventory_id: int, quantity: int, order_id: int, reserved_until: datetime
    ) -> list[InventoryLine]:
        """Atomically lock & reserve up to ``quantity`` sellable lines.

        Uses ``FOR UPDATE SKIP LOCKED`` so concurrent buyers never grab the
        same line. Returns the reserved lines (empty if not enough stock).
        """
        now = _utcnow()
        res = await self.session.execute(
            select(InventoryLine)
            .where(
                InventoryLine.seller_inventory_id == seller_inventory_id,
                InventoryLine.is_sold.is_(False),
                or_(
                    InventoryLine.is_reserved.is_(False),
                    InventoryLine.reserved_until < now,
                ),
            )
            .order_by(InventoryLine.id)
            .limit(quantity)
            .with_for_update(skip_locked=True)
        )
        lines = list(res.scalars().all())
        if len(lines) < quantity:
            return []
        for line in lines:
            line.is_reserved = True
            line.reserved_until = reserved_until
            line.reserved_by_order_id = order_id
        await self.session.flush()
        return lines

    async def mark_sold(self, line_ids: Sequence[int], order_id: int) -> None:
        if not line_ids:
            return
        now = _utcnow()
        await self.session.execute(
            update(InventoryLine)
            .where(InventoryLine.id.in_(line_ids))
            .values(
                is_sold=True,
                is_reserved=False,
                reserved_until=None,
                order_id=order_id,
                sold_at=now,
            )
        )

    async def release_reservation(self, order_id: int) -> None:
        await self.session.execute(
            update(InventoryLine)
            .where(
                InventoryLine.reserved_by_order_id == order_id,
                InventoryLine.is_sold.is_(False),
            )
            .values(is_reserved=False, reserved_until=None, reserved_by_order_id=None)
        )

    async def release_expired(self) -> int:
        now = _utcnow()
        res = await self.session.execute(
            update(InventoryLine)
            .where(
                InventoryLine.is_reserved.is_(True),
                InventoryLine.is_sold.is_(False),
                InventoryLine.reserved_until < now,
            )
            .values(is_reserved=False, reserved_until=None, reserved_by_order_id=None)
        )
        return res.rowcount or 0

    # ------------------------------------------------------------------
    # Category aggregation / browsing
    # ------------------------------------------------------------------
    async def all_categories(self) -> Sequence[tuple[str, int, int]]:
        """Return (category, total_stock, seller_count) across active sellers."""
        stock_expr = func.sum(SellerInventory.total_lines - SellerInventory.sold_count)
        res = await self.session.execute(
            select(
                SellerInventory.category,
                stock_expr,
                func.count(func.distinct(SellerInventory.seller_id)),
            )
            .join(Seller, Seller.id == SellerInventory.seller_id)
            .where(
                Seller.status == SellerStatus.ACTIVE,
                SellerInventory.is_active.is_(True),
            )
            .group_by(SellerInventory.category)
            .having(stock_expr > 0)
            .order_by(SellerInventory.category)
        )
        return [(row[0], int(row[1] or 0), int(row[2] or 0)) for row in res.all()]

    async def offers_for_category(
        self,
        category: str,
        *,
        min_price: Optional[Decimal] = None,
        max_price: Optional[Decimal] = None,
        seller_id: Optional[int] = None,
        only_available: bool = True,
    ) -> Sequence[tuple[SellerInventory, Seller]]:
        """Offers for a category as (offer, seller) — what the buyer sees."""
        stmt = (
            select(SellerInventory, Seller)
            .join(Seller, Seller.id == SellerInventory.seller_id)
            .where(
                SellerInventory.category == category,
                Seller.status == SellerStatus.ACTIVE,
                SellerInventory.is_active.is_(True),
            )
        )
        if only_available:
            stmt = stmt.where(SellerInventory.total_lines > SellerInventory.sold_count)
        if min_price is not None:
            stmt = stmt.where(SellerInventory.price >= min_price)
        if max_price is not None:
            stmt = stmt.where(SellerInventory.price <= max_price)
        if seller_id is not None:
            stmt = stmt.where(SellerInventory.seller_id == seller_id)
        stmt = stmt.order_by(SellerInventory.price.asc())
        res = await self.session.execute(stmt)
        return [(row[0], row[1]) for row in res.all()]

    async def seller_offers(self, seller_id: int) -> Sequence[SellerInventory]:
        res = await self.session.execute(
            select(SellerInventory)
            .where(SellerInventory.seller_id == seller_id)
            .order_by(SellerInventory.category)
        )
        return res.scalars().all()

    async def register_first_sale(self, seller_inventory_id: int) -> None:
        await self.session.execute(
            update(SellerInventory)
            .where(
                SellerInventory.id == seller_inventory_id,
                SellerInventory.first_sale_at.is_(None),
            )
            .values(first_sale_at=func.now())
        )

    async def increment_sold(self, seller_inventory_id: int, count: int) -> None:
        await self.session.execute(
            update(SellerInventory)
            .where(SellerInventory.id == seller_inventory_id)
            .values(sold_count=SellerInventory.sold_count + count)
        )

    # ------------------------------------------------------------------
    # Global statistics
    # ------------------------------------------------------------------
    async def total_stock(self) -> int:
        res = await self.session.execute(
            select(func.coalesce(func.sum(SellerInventory.total_lines - SellerInventory.sold_count), 0))
        )
        return int(res.scalar() or 0)

    async def total_lines(self) -> int:
        res = await self.session.execute(
            select(func.coalesce(func.sum(SellerInventory.total_lines), 0))
        )
        return int(res.scalar() or 0)

    async def category_count(self) -> int:
        res = await self.session.execute(
            select(func.count(func.distinct(SellerInventory.category)))
        )
        return int(res.scalar() or 0)

    async def export_lines(
        self, *, category: Optional[str], seller_id: Optional[int], limit: int
    ) -> Sequence[str]:
        """Owner export of available (unsold) lines for backup/migration."""
        stmt = select(InventoryLine.line_data).where(InventoryLine.is_sold.is_(False))
        if category:
            stmt = stmt.where(InventoryLine.category == category)
        if seller_id:
            stmt = stmt.where(InventoryLine.seller_id == seller_id)
        stmt = stmt.limit(limit)
        res = await self.session.execute(stmt)
        return [row[0] for row in res.all()]
