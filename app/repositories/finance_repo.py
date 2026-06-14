"""Transactions, Deposits and Withdrawals data access."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional, Sequence

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import DepositStatus, TransactionType, WithdrawalStatus
from app.models import Deposit, Transaction, Withdrawal


class FinanceRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    # --- transactions ---
    async def add_transaction(
        self,
        user_id: int,
        type_: TransactionType,
        amount: Decimal,
        balance_after: Decimal,
        reference: Optional[str] = None,
        meta: Optional[dict[str, Any]] = None,
    ) -> Transaction:
        tx = Transaction(
            user_id=user_id,
            type=type_,
            amount=amount,
            balance_after=balance_after,
            reference=reference,
            meta=meta,
        )
        self.session.add(tx)
        await self.session.flush()
        return tx

    async def user_transactions(self, user_id: int, limit: int = 20) -> Sequence[Transaction]:
        res = await self.session.execute(
            select(Transaction)
            .where(Transaction.user_id == user_id)
            .order_by(Transaction.created_at.desc())
            .limit(limit)
        )
        return res.scalars().all()

    # --- deposits ---
    async def create_deposit(self, **kwargs) -> Deposit:
        deposit = Deposit(**kwargs)
        self.session.add(deposit)
        await self.session.flush()
        return deposit

    async def get_deposit(self, deposit_id: int) -> Optional[Deposit]:
        return await self.session.get(Deposit, deposit_id)

    async def pending_deposits(self) -> Sequence[Deposit]:
        res = await self.session.execute(
            select(Deposit).where(Deposit.status == DepositStatus.PENDING)
        )
        return res.scalars().all()

    async def set_deposit_status(
        self, deposit_id: int, status: DepositStatus, txid: Optional[str] = None
    ) -> None:
        values: dict[str, Any] = {"status": status}
        if status == DepositStatus.CONFIRMED:
            values["confirmed_at"] = datetime.now(timezone.utc)
        if txid:
            values["txid"] = txid
        await self.session.execute(
            update(Deposit).where(Deposit.id == deposit_id).values(**values)
        )

    async def total_deposits(self) -> Decimal:
        res = await self.session.execute(
            select(func.coalesce(func.sum(Deposit.credited_usd), 0)).where(
                Deposit.status == DepositStatus.CONFIRMED
            )
        )
        return Decimal(res.scalar() or 0)

    # --- withdrawals ---
    async def create_withdrawal(self, **kwargs) -> Withdrawal:
        withdrawal = Withdrawal(**kwargs)
        self.session.add(withdrawal)
        await self.session.flush()
        return withdrawal

    async def get_withdrawal(self, withdrawal_id: int) -> Optional[Withdrawal]:
        return await self.session.get(Withdrawal, withdrawal_id)

    async def pending_withdrawals(self) -> Sequence[Withdrawal]:
        res = await self.session.execute(
            select(Withdrawal)
            .where(Withdrawal.status == WithdrawalStatus.PENDING)
            .order_by(Withdrawal.created_at)
        )
        return res.scalars().all()

    async def user_withdrawals(self, user_id: int, limit: int = 20) -> Sequence[Withdrawal]:
        res = await self.session.execute(
            select(Withdrawal)
            .where(Withdrawal.user_id == user_id)
            .order_by(Withdrawal.created_at.desc())
            .limit(limit)
        )
        return res.scalars().all()

    async def set_withdrawal_status(
        self,
        withdrawal_id: int,
        status: WithdrawalStatus,
        owner_note: Optional[str] = None,
        txid: Optional[str] = None,
    ) -> None:
        values: dict[str, Any] = {
            "status": status,
            "processed_at": datetime.now(timezone.utc),
        }
        if owner_note:
            values["owner_note"] = owner_note
        if txid:
            values["txid"] = txid
        await self.session.execute(
            update(Withdrawal).where(Withdrawal.id == withdrawal_id).values(**values)
        )

    async def total_withdrawals(self) -> Decimal:
        res = await self.session.execute(
            select(func.coalesce(func.sum(Withdrawal.amount), 0)).where(
                Withdrawal.status.in_([WithdrawalStatus.APPROVED, WithdrawalStatus.PAID])
            )
        )
        return Decimal(res.scalar() or 0)

    async def total_commission(self) -> Decimal:
        res = await self.session.execute(
            select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                Transaction.type == TransactionType.COMMISSION
            )
        )
        return Decimal(res.scalar() or 0)
