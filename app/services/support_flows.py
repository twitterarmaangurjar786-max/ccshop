"""Tickets & Refunds business logic."""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import OrderStatus, RefundStatus, TransactionType
from app.models import Refund, Ticket
from app.repositories.order_repo import OrderRepository
from app.repositories.support_repo import SupportRepository
from app.repositories.system_repo import SystemRepository
from app.services.exceptions import InvalidInput
from app.services.wallet_service import WalletService


class SupportFlowService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.support = SupportRepository(session)
        self.orders = OrderRepository(session)
        self.system = SystemRepository(session)
        self.wallets = WalletService(session)

    # ----- Tickets -----
    async def open_ticket(self, user_id: int, subject: str, message: str) -> Ticket:
        ticket = await self.support.create_ticket(user_id, subject or "Support", message)
        await self.system.log(
            action="ticket_opened", actor_id=user_id, entity="ticket", entity_id=ticket.id
        )
        return ticket

    async def reply_ticket(
        self, ticket_id: int, sender_id: int, text: str, is_owner: bool
    ) -> Optional[Ticket]:
        ticket = await self.support.get_ticket(ticket_id)
        if ticket is None:
            return None
        await self.support.add_message(ticket_id, sender_id, text, is_owner)
        return ticket

    async def close_ticket(self, ticket_id: int) -> None:
        await self.support.close_ticket(ticket_id)

    # ----- Refunds -----
    async def create_refund(
        self, user_id: int, order_id: int, amount: Decimal, reason: str
    ) -> Refund:
        refund = await self.support.create_refund(
            order_id=order_id,
            user_id=user_id,
            amount=amount,
            reason=reason[:1000],
            status=RefundStatus.PENDING,
        )
        await self.system.log(
            action="refund_requested", actor_id=user_id, entity="refund", entity_id=refund.id
        )
        return refund

    async def approve_refund(self, owner_id: int, refund_id: int) -> Refund:
        refund = await self.support.get_refund(refund_id)
        if refund is None or refund.status != RefundStatus.PENDING:
            raise InvalidInput("Refund not found or already processed.")
        # Credit the buyer back.
        await self.wallets.credit(
            refund.user_id,
            refund.amount,
            TransactionType.REFUND,
            reference=f"refund:{refund_id}",
        )
        await self.support.set_refund_status(refund_id, RefundStatus.APPROVED)
        await self.orders.set_status(refund.order_id, OrderStatus.REFUNDED)
        await self.system.log(
            action="refund_approved", actor_id=owner_id, entity="refund", entity_id=refund_id
        )
        return refund

    async def reject_refund(
        self, owner_id: int, refund_id: int, note: Optional[str] = None
    ) -> Refund:
        refund = await self.support.get_refund(refund_id)
        if refund is None or refund.status != RefundStatus.PENDING:
            raise InvalidInput("Refund not found or already processed.")
        await self.support.set_refund_status(refund_id, RefundStatus.REJECTED, owner_note=note)
        await self.system.log(
            action="refund_rejected", actor_id=owner_id, entity="refund", entity_id=refund_id
        )
        return refund
