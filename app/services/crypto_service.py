"""Crypto deposits — xRocket Pay + on-chain (USDT TRC20 / TRX).

Two deposit rails are supported:

* **xRocket Pay** (``asset == "XROCKET"``) — an invoice is created via the
  xRocket Pay API; the invoice id is stored in ``deposit.txid`` and the pay link
  in ``deposit.address``. Payment is detected by polling the invoice status.
* **On-chain TRON** (``USDT_TRC20`` / ``TRX``) — a deposit address is shown and a
  background poller watches for incoming funds (hook in ``_lookup_onchain_payment``).

When credentials are missing the relevant rail simply reports no confirmations,
so the rest of the bot keeps working in development.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.constants import CryptoAsset, DepositStatus, TransactionType
from app.logger import get_logger
from app.repositories.finance_repo import FinanceRepository
from app.services.wallet_service import WalletService
from app.services.xrocket_service import XRocketService

logger = get_logger(__name__)

DEPOSIT_EXPIRY_MINUTES = 60
XROCKET_ASSET = "XROCKET"


class CryptoService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.finance = FinanceRepository(session)
        self.wallets = WalletService(session)

    # ------------------------------------------------------------------
    # On-chain address generation
    # ------------------------------------------------------------------
    def _generate_address(self) -> str:
        if settings.deposit_master_wallet:
            return settings.deposit_master_wallet
        return "T" + secrets.token_hex(16)

    async def create_deposit(self, user_id: int, asset: CryptoAsset) -> "Deposit":
        from app.models import Deposit  # noqa: F401  (typing only)

        address = self._generate_address()
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=DEPOSIT_EXPIRY_MINUTES)
        return await self.finance.create_deposit(
            user_id=user_id,
            asset=asset.value,
            address=address,
            status=DepositStatus.PENDING,
            expires_at=expires_at,
        )

    # ------------------------------------------------------------------
    # xRocket Pay
    # ------------------------------------------------------------------
    @staticmethod
    def xrocket_enabled() -> bool:
        return XRocketService().enabled

    async def create_xrocket_deposit(self, user_id: int, amount: Decimal):
        """Create a pending xRocket deposit + invoice. Returns (deposit, pay_link)."""
        xr = XRocketService()
        if not xr.enabled:
            raise RuntimeError("xRocket is not configured (set XROCKET_API_KEY).")

        amount = Decimal(amount).quantize(Decimal("0.01"))
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=DEPOSIT_EXPIRY_MINUTES)
        deposit = await self.finance.create_deposit(
            user_id=user_id,
            asset=XROCKET_ASSET,
            amount=amount,
            address="pending",
            status=DepositStatus.PENDING,
            expires_at=expires_at,
        )
        invoice = await xr.create_invoice(amount, payload=f"dep:{deposit.id}")
        deposit.address = str(invoice["link"])[:128]
        deposit.txid = str(invoice["id"])[:128]
        await self.session.flush()
        return deposit, invoice["link"]

    async def _confirm_xrocket(self, deposit, xr: XRocketService) -> Optional[Decimal]:
        info = await xr.get_invoice(deposit.txid)
        if not info["paid"]:
            return None
        amount = info["amount"] or deposit.amount or Decimal("0")
        if amount <= 0:
            return None
        return await self.confirm_deposit(
            deposit.id, amount, txid=f"xrocket:{deposit.txid}"
        )

    async def check_one_xrocket(self, deposit_id: int) -> Optional[Decimal]:
        """Poll a single xRocket deposit on demand (used by the 'Check' button)."""
        deposit = await self.finance.get_deposit(deposit_id)
        if (
            deposit is None
            or deposit.asset != XROCKET_ASSET
            or deposit.status != DepositStatus.PENDING
        ):
            return None
        xr = XRocketService()
        if not xr.enabled:
            return None
        return await self._confirm_xrocket(deposit, xr)

    # ------------------------------------------------------------------
    # Confirmation / crediting
    # ------------------------------------------------------------------
    async def confirm_deposit(
        self, deposit_id: int, amount: Decimal, txid: str
    ) -> Optional[Decimal]:
        deposit = await self.finance.get_deposit(deposit_id)
        if deposit is None or deposit.status != DepositStatus.PENDING:
            return None

        credited_usd = Decimal(amount).quantize(Decimal("0.01"))
        deposit.amount = Decimal(amount)
        deposit.credited_usd = credited_usd
        await self.finance.set_deposit_status(deposit_id, DepositStatus.CONFIRMED, txid)

        await self.wallets.credit(
            deposit.user_id,
            credited_usd,
            TransactionType.DEPOSIT,
            reference=f"deposit:{deposit_id}",
            meta={"asset": deposit.asset, "txid": txid},
        )
        logger.info("Deposit %s confirmed: %s USD", deposit_id, credited_usd)
        return credited_usd

    async def _telegram_id(self, user_id: int) -> Optional[int]:
        from app.models import User

        user = await self.session.get(User, user_id)
        return user.telegram_id if user else None

    # ------------------------------------------------------------------
    # Background polling (called by the scheduler)
    # ------------------------------------------------------------------
    async def check_pending_payments(self) -> list[dict]:
        """Poll all pending deposits across both rails.

        Returns a list of ``{"telegram_id": int, "amount": Decimal}`` for every
        deposit confirmed in this pass so the caller can notify users.
        """
        notifications: list[dict] = []
        xr = XRocketService()
        tron_ready = bool(settings.tron_api_key and settings.deposit_master_wallet)

        pending = await self.finance.pending_deposits()
        for deposit in pending:
            credited: Optional[Decimal] = None

            if deposit.asset == XROCKET_ASSET:
                if not xr.enabled:
                    continue
                try:
                    credited = await self._confirm_xrocket(deposit, xr)
                except Exception:  # noqa: BLE001
                    logger.exception("xRocket poll failed for deposit %s", deposit.id)
                    continue
            else:
                if not tron_ready:
                    continue
                received = await self._lookup_onchain_payment(deposit.address)
                if received and received > 0:
                    credited = await self.confirm_deposit(
                        deposit.id, received, f"onchain_{secrets.token_hex(8)}"
                    )

            if credited:
                tg = await self._telegram_id(deposit.user_id)
                if tg:
                    notifications.append({"telegram_id": tg, "amount": credited})
        return notifications

    async def _lookup_onchain_payment(self, address: str) -> Optional[Decimal]:
        """Hook for real TRON balance/transaction lookup. Returns USD amount."""
        return None
