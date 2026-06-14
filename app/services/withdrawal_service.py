"""Withdrawal requests and Owner approval flow."""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import TransactionType, WithdrawalStatus
from app.models import Withdrawal
from app.repositories.finance_repo import FinanceRepository
from app.repositories.system_repo import SystemRepository
from app.repositories.user_repo import UserRepository
from app.services.exceptions import InsufficientFunds, InvalidInput
from app.services.wallet_service import WalletService

MIN_WITHDRAWAL = Decimal("5.00")


class WithdrawalService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.finance = FinanceRepository(session)
        self.users = UserRepository(session)
        self.system = SystemRepository(session)
        self.wallets = WalletService(session)

    async def request(
        self, user_id: int, amount: Decimal, wallet_address: str, asset: str = "USDT_TRC20"
    ) -> Withdrawal:
        amount = Decimal(amount).quantize(Decimal("0.01"))
        if amount < MIN_WITHDRAWAL:
            raise InvalidInput(f"Minimum withdrawal is {MIN_WITHDRAWAL}.")
        if len(wallet_address.strip()) < 20:
            raise InvalidInput("Invalid wallet address.")

        # Hold the funds immediately to prevent double spending.
        await self.wallets.debit(
            user_id,
            amount,
            TransactionType.WITHDRAWAL,
            reference="withdrawal_request",
        )
        withdrawal = await self.finance.create_withdrawal(
            user_id=user_id,
            amount=amount,
            asset=asset,
            wallet_address=wallet_address.strip(),
            status=WithdrawalStatus.PENDING,
        )
        await self.system.log(
            action="withdrawal_requested",
            actor_id=user_id,
            entity="withdrawal",
            entity_id=withdrawal.id,
            detail={"amount": str(amount)},
        )
        return withdrawal

    async def approve(
        self, owner_id: int, withdrawal_id: int, txid: Optional[str] = None
    ) -> Withdrawal:
        withdrawal = await self.finance.get_withdrawal(withdrawal_id)
        if withdrawal is None or withdrawal.status != WithdrawalStatus.PENDING:
            raise InvalidInput("Withdrawal not found or already processed.")
        status = WithdrawalStatus.PAID if txid else WithdrawalStatus.APPROVED
        await self.finance.set_withdrawal_status(withdrawal_id, status, txid=txid)
        await self.system.log(
            action="withdrawal_approved",
            actor_id=owner_id,
            entity="withdrawal",
            entity_id=withdrawal_id,
        )
        return withdrawal

    async def reject(
        self, owner_id: int, withdrawal_id: int, note: Optional[str] = None
    ) -> Withdrawal:
        withdrawal = await self.finance.get_withdrawal(withdrawal_id)
        if withdrawal is None or withdrawal.status != WithdrawalStatus.PENDING:
            raise InvalidInput("Withdrawal not found or already processed.")
        # Refund the held amount back to the seller.
        await self.wallets.credit(
            withdrawal.user_id,
            withdrawal.amount,
            TransactionType.REFUND,
            reference=f"withdrawal_rejected:{withdrawal_id}",
        )
        await self.finance.set_withdrawal_status(
            withdrawal_id, WithdrawalStatus.REJECTED, owner_note=note
        )
        await self.system.log(
            action="withdrawal_rejected",
            actor_id=owner_id,
            entity="withdrawal",
            entity_id=withdrawal_id,
            detail={"note": note},
        )
        return withdrawal
