"""Purchase flow: reservation, confirmation, delivery, commission split."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import List, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.constants import OrderStatus, Role, TransactionType
from app.models import Order
from app.repositories.inventory_repo import InventoryRepository
from app.repositories.order_repo import OrderRepository
from app.repositories.seller_repo import SellerRepository
from app.repositories.system_repo import SystemRepository
from app.repositories.user_repo import UserRepository
from app.services.commission_service import calculate_split
from app.services.coupon_service import CouponService
from app.services.exceptions import (
    InsufficientFunds,
    InvalidInput,
    OutOfStock,
    ReservationExpired,
)
from app.services.wallet_service import WalletService


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PurchaseService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.inventory = InventoryRepository(session)
        self.orders = OrderRepository(session)
        self.sellers = SellerRepository(session)
        self.users = UserRepository(session)
        self.system = SystemRepository(session)
        self.wallets = WalletService(session)
        self.coupons = CouponService(session)

    # ------------------------------------------------------------------
    # Reservation
    # ------------------------------------------------------------------
    async def reserve(
        self,
        buyer_id: int,
        seller_inventory_id: int,
        quantity: int,
        coupon_code: Optional[str] = None,
    ) -> Order:
        if quantity <= 0:
            raise InvalidInput("Quantity must be greater than zero.")

        offer = await self.inventory.get_offer_for_update(seller_inventory_id)
        if offer is None or not offer.is_active:
            raise OutOfStock("This offer is no longer available.")

        unit_price = Decimal(offer.price)
        subtotal = (unit_price * quantity).quantize(Decimal("0.01"))

        discount = Decimal("0.00")
        coupon_id: Optional[int] = None
        if coupon_code:
            preview = await self.coupons.preview(coupon_code, buyer_id, subtotal)
            discount = preview.discount
            coupon_id = preview.coupon.id

        total = (subtotal - discount).quantize(Decimal("0.01"))
        reserved_until = _utcnow() + timedelta(minutes=settings.reservation_minutes)

        order = await self.orders.create(
            buyer_id=buyer_id,
            seller_id=offer.seller_id,
            seller_inventory_id=offer.id,
            category=offer.category,
            quantity=quantity,
            unit_price=unit_price,
            subtotal=subtotal,
            discount=discount,
            total=total,
            coupon_id=coupon_id,
            status=OrderStatus.RESERVED,
            reserved_until=reserved_until,
        )

        reserved = await self.inventory.reserve_lines(
            offer.id, quantity, order.id, reserved_until
        )
        if not reserved:
            await self.orders.set_status(order.id, OrderStatus.CANCELLED)
            raise OutOfStock(
                f"Not enough stock. Only {offer.remaining} line(s) remaining."
            )

        await self.system.log(
            action="order_reserved",
            actor_id=buyer_id,
            entity="order",
            entity_id=order.id,
            detail={"qty": quantity, "total": str(total)},
        )
        return order

    # ------------------------------------------------------------------
    # Confirmation / delivery
    # ------------------------------------------------------------------
    async def confirm(self, order_id: int, buyer_id: int) -> Tuple[Order, List[str]]:
        order = await self.orders.get_for_update(order_id)
        if order is None or order.buyer_id != buyer_id:
            raise InvalidInput("Order not found.")
        if order.status != OrderStatus.RESERVED:
            raise InvalidInput("This order can no longer be paid.")
        if order.reserved_until and order.reserved_until < _utcnow():
            await self._cancel_expired(order)
            raise ReservationExpired("Your reservation expired. Please order again.")

        # Charge the buyer
        await self.wallets.debit(
            buyer_id,
            order.total,
            TransactionType.PURCHASE,
            reference=f"order:{order.id}",
            meta={"category": order.category, "qty": order.quantity},
        )

        # Collect reserved lines and mark them sold
        from sqlalchemy import select  # local import to avoid cycle at top

        from app.models import InventoryLine

        res = await self.session.execute(
            select(InventoryLine).where(
                InventoryLine.reserved_by_order_id == order.id,
                InventoryLine.is_sold.is_(False),
            )
        )
        lines = list(res.scalars().all())
        if len(lines) < order.quantity:
            # Safety net — should not happen because lines were locked
            await self.wallets.credit(
                buyer_id,
                order.total,
                TransactionType.REFUND,
                reference=f"order_refund:{order.id}",
            )
            await self._cancel_expired(order)
            raise OutOfStock("Stock changed during checkout. You were not charged.")

        line_ids = [ln.id for ln in lines]
        delivered = [ln.line_data for ln in lines]
        await self.inventory.mark_sold(line_ids, order.id)

        # Purchase history rows
        await self.orders.add_purchases(
            [
                {
                    "order_id": order.id,
                    "buyer_id": buyer_id,
                    "seller_id": order.seller_id,
                    "line_id": ln.id,
                    "line_data": ln.line_data,
                    "category": order.category,
                }
                for ln in lines
            ]
        )

        # Inventory counters
        await self.inventory.increment_sold(order.seller_inventory_id, order.quantity)
        await self.inventory.register_first_sale(order.seller_inventory_id)

        # Commission split
        seller = await self.sellers.get_by_id(order.seller_id)
        split = calculate_split(order.total, seller.seller_percent if seller else None)

        if seller:
            await self.wallets.credit(
                seller.user_id,
                split.seller_amount,
                TransactionType.SALE,
                reference=f"order:{order.id}",
                meta={"order": order.id, "qty": order.quantity},
            )
            await self.sellers.add_sale(seller.id, split.seller_amount, order.quantity)

        owner_user_id = await self._owner_user_id()
        if owner_user_id is not None and split.owner_amount > 0:
            await self.wallets.credit(
                owner_user_id,
                split.owner_amount,
                TransactionType.COMMISSION,
                reference=f"order:{order.id}",
                meta={"order": order.id},
            )

        # Coupon redemption
        if order.coupon_id:
            await self.coupons.redeem(order.coupon_id, buyer_id)

        await self.orders.set_status(order.id, OrderStatus.DELIVERED)
        await self.system.log(
            action="order_delivered",
            actor_id=buyer_id,
            entity="order",
            entity_id=order.id,
            detail={
                "total": str(order.total),
                "seller_amount": str(split.seller_amount),
                "owner_amount": str(split.owner_amount),
            },
        )
        return order, delivered

    async def cancel(self, order_id: int, buyer_id: int) -> None:
        order = await self.orders.get_for_update(order_id)
        if order is None or order.buyer_id != buyer_id:
            return
        if order.status == OrderStatus.RESERVED:
            await self._cancel_expired(order)

    async def _cancel_expired(self, order: Order) -> None:
        await self.inventory.release_reservation(order.id)
        await self.orders.set_status(order.id, OrderStatus.CANCELLED)

    async def _owner_user_id(self) -> Optional[int]:
        for tg_id in settings.owner_ids:
            user = await self.users.get_by_telegram_id(tg_id)
            if user is None:
                user = await self.users.create(
                    telegram_id=tg_id,
                    username=None,
                    full_name="Owner",
                    role=Role.OWNER,
                )
            return user.id
        return None

    async def delivered_lines(self, order_id: int) -> List[str]:
        purchases = await self.orders.order_purchases(order_id)
        return [p.line_data for p in purchases]
