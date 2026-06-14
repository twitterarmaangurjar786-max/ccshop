"""xRocket Pay integration (Telegram crypto payments).

Docs: https://pay.xrocket.tg/  (API base: ``https://pay.xrocket.tg``)
Auth: header ``Rocket-Pay-Key: <app key>``.

This service creates *tg-invoices* and polls their status. It is intentionally
defensive about response field names so it keeps working across minor API
changes. When ``XROCKET_API_KEY`` is empty the service reports ``enabled=False``
and the deposit flow falls back to the on-chain crypto path.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

import aiohttp

from app.config import settings
from app.logger import get_logger

logger = get_logger(__name__)

_TIMEOUT = aiohttp.ClientTimeout(total=20)


class XRocketError(Exception):
    pass


class XRocketService:
    def __init__(self) -> None:
        self.base = settings.xrocket_base_url.rstrip("/")
        self.key = settings.xrocket_api_key
        self.currency = settings.xrocket_currency or "USDT"

    @property
    def enabled(self) -> bool:
        return bool(self.key)

    def _headers(self) -> dict[str, str]:
        return {"Rocket-Pay-Key": self.key, "Content-Type": "application/json"}

    # ------------------------------------------------------------------
    async def create_invoice(
        self, amount: Decimal, payload: str, description: str = "Balance top-up"
    ) -> dict:
        """Create a tg-invoice. Returns ``{"id": str, "link": str}``."""
        body = {
            "amount": float(Decimal(amount)),
            "numPayments": 1,
            "currency": self.currency,
            "description": description,
            "payload": payload,
            "expiredIn": 3600,
        }
        async with aiohttp.ClientSession(timeout=_TIMEOUT) as s:
            async with s.post(
                f"{self.base}/tg-invoices", json=body, headers=self._headers()
            ) as r:
                data = await r.json(content_type=None)
        if isinstance(data, dict) and data.get("success") is False:
            raise XRocketError(str(data.get("message") or data))
        d = data.get("data", data) if isinstance(data, dict) else {}
        invoice_id = d.get("id") or d.get("invoiceId") or d.get("invoice_id")
        link = (
            d.get("link")
            or d.get("payLink")
            or d.get("paymentUrl")
            or d.get("url")
        )
        if not invoice_id or not link:
            raise XRocketError(f"Unexpected xRocket response: {data}")
        return {"id": str(invoice_id), "link": str(link)}

    # ------------------------------------------------------------------
    async def get_invoice(self, invoice_id: str) -> dict:
        """Fetch invoice status. Returns ``{"paid": bool, "amount": Decimal|None}``."""
        async with aiohttp.ClientSession(timeout=_TIMEOUT) as s:
            async with s.get(
                f"{self.base}/tg-invoices/{invoice_id}", headers=self._headers()
            ) as r:
                data = await r.json(content_type=None)
        d = data.get("data", data) if isinstance(data, dict) else {}
        status = str(d.get("status") or "").lower()
        payments = d.get("payments") or d.get("activations") or []
        paid_flag = d.get("paid")
        is_paid = (
            status in {"paid", "completed", "success"}
            or bool(payments)
            or (isinstance(paid_flag, bool) and paid_flag)
            or (isinstance(d.get("activationsLeft"), int)
                and isinstance(d.get("numPayments"), int)
                and d["activationsLeft"] < d["numPayments"])
        )
        amount = d.get("amount")
        # If we have an explicit paid amount, prefer it.
        if payments and isinstance(payments, list) and isinstance(payments[0], dict):
            amount = payments[0].get("amount", amount)
        parsed: Optional[Decimal] = None
        if amount is not None:
            try:
                parsed = Decimal(str(amount))
            except Exception:  # noqa: BLE001
                parsed = None
        return {"paid": bool(is_paid), "amount": parsed}
