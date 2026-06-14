"""Wallet operations with atomic, row-locked balance mutations + ledger."""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import TransactionType
from app.models import Transaction
from app.repositories.finance_repo import FinanceRepository
from app.repositories.user_repo import UserRepository
from app.services.exceptions import InsufficientFunds

# Transaction types that increase the wallet balance.
_CREDIT_TYPES = {
    TransactionType.DEPOSIT,
    TransactionType.SALE,
    TransactionType.COMMISSION,
    TransactionType.REFUND,
    TransactionType.REFERRAL,
}


class WalletService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.users = UserRepository(session)
        self.finance = FinanceRepository(session)

    async def get_balance(self, user_id: int) -> Decimal:
        wallet = await self.users.get_wallet(user_id)
        return wallet.balance

    async def credit(
        self,
        user_id: int,
        amount: Decimal,
        type_: TransactionType,
        reference: Optional[str] = None,
        meta: Optional[dict[str, Any]] = None,
    ) -> Transaction:
        amount = Decimal(amount).quantize(Decimal("0.01"))
        wallet = await self.users.get_wallet_for_update(user_id)
        wallet.balance += amount
        if type_ == TransactionType.DEPOSIT:
            wallet.total_deposited += amount
        elif type_ in (TransactionType.SALE, TransactionType.COMMISSION):
            wallet.total_earned += amount
        await self.session.flush()
        return await self.finance.add_transaction(
            user_id, type_, amount, wallet.balance, reference, meta
        )

    async def debit(
        self,
        user_id: int,
        amount: Decimal,
        type_: TransactionType,
        reference: Optional[str] = None,
        meta: Optional[dict[str, Any]] = None,
        allow_negative: bool = False,
    ) -> Transaction:
        amount = Decimal(amount).quantize(Decimal("0.01"))
        wallet = await self.users.get_wallet_for_update(user_id)
        if not allow_negative and wallet.balance < amount:
            raise InsufficientFunds(
                f"Insufficient balance. Need {amount}, have {wallet.balance}."
            )
        wallet.balance -= amount
        if type_ == TransactionType.PURCHASE:
            wallet.total_spent += amount
        elif type_ == TransactionType.WITHDRAWAL:
            wallet.total_withdrawn += amount
        await self.session.flush()
        return await self.finance.add_transaction(
            user_id, type_, -amount, wallet.balance, reference, meta
        )
