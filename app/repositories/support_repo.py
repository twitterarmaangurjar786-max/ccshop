"""Tickets and Refunds data access."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Sequence

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.constants import RefundStatus, TicketStatus
from app.models import Refund, Ticket, TicketMessage


class SupportRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    # ----- Tickets -----
    async def create_ticket(self, user_id: int, subject: str, first_message: str) -> Ticket:
        ticket = Ticket(user_id=user_id, subject=subject, status=TicketStatus.OPEN)
        self.session.add(ticket)
        await self.session.flush()
        self.session.add(
            TicketMessage(
                ticket_id=ticket.id,
                sender_id=user_id,
                is_owner=False,
                text=first_message,
            )
        )
        await self.session.flush()
        return ticket

    async def get_ticket(self, ticket_id: int) -> Optional[Ticket]:
        res = await self.session.execute(
            select(Ticket)
            .where(Ticket.id == ticket_id)
            .options(selectinload(Ticket.messages))
        )
        return res.scalar_one_or_none()

    async def add_message(
        self, ticket_id: int, sender_id: int, text: str, is_owner: bool
    ) -> TicketMessage:
        msg = TicketMessage(
            ticket_id=ticket_id, sender_id=sender_id, text=text, is_owner=is_owner
        )
        self.session.add(msg)
        new_status = TicketStatus.ANSWERED if is_owner else TicketStatus.OPEN
        await self.session.execute(
            update(Ticket).where(Ticket.id == ticket_id).values(status=new_status)
        )
        await self.session.flush()
        return msg

    async def close_ticket(self, ticket_id: int) -> None:
        await self.session.execute(
            update(Ticket)
            .where(Ticket.id == ticket_id)
            .values(status=TicketStatus.CLOSED, closed_at=datetime.now(timezone.utc))
        )

    async def user_tickets(self, user_id: int) -> Sequence[Ticket]:
        res = await self.session.execute(
            select(Ticket)
            .where(Ticket.user_id == user_id)
            .order_by(Ticket.updated_at.desc())
        )
        return res.scalars().all()

    async def open_tickets(self) -> Sequence[Ticket]:
        res = await self.session.execute(
            select(Ticket)
            .where(Ticket.status != TicketStatus.CLOSED)
            .order_by(Ticket.updated_at.desc())
        )
        return res.scalars().all()

    async def open_ticket_count(self) -> int:
        res = await self.session.execute(
            select(func.count(Ticket.id)).where(Ticket.status != TicketStatus.CLOSED)
        )
        return int(res.scalar() or 0)

    # ----- Refunds -----
    async def create_refund(self, **kwargs) -> Refund:
        refund = Refund(**kwargs)
        self.session.add(refund)
        await self.session.flush()
        return refund

    async def get_refund(self, refund_id: int) -> Optional[Refund]:
        return await self.session.get(Refund, refund_id)

    async def user_refunds(self, user_id: int) -> Sequence[Refund]:
        res = await self.session.execute(
            select(Refund)
            .where(Refund.user_id == user_id)
            .order_by(Refund.created_at.desc())
        )
        return res.scalars().all()

    async def pending_refunds(self) -> Sequence[Refund]:
        res = await self.session.execute(
            select(Refund)
            .where(Refund.status == RefundStatus.PENDING)
            .order_by(Refund.created_at)
        )
        return res.scalars().all()

    async def set_refund_status(
        self, refund_id: int, status: RefundStatus, owner_note: Optional[str] = None
    ) -> None:
        await self.session.execute(
            update(Refund)
            .where(Refund.id == refund_id)
            .values(
                status=status,
                owner_note=owner_note,
                processed_at=datetime.now(timezone.utc),
            )
        )
