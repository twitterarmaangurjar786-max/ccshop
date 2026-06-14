"""Commission calculation (default seller 90% / owner 10%)."""
from __future__ import annotations

from decimal import Decimal
from typing import NamedTuple, Optional

from app.config import settings


class CommissionSplit(NamedTuple):
    seller_amount: Decimal
    owner_amount: Decimal
    seller_percent: int
    owner_percent: int


def calculate_split(
    total: Decimal, seller_percent: Optional[int] = None
) -> CommissionSplit:
    """Split ``total`` between seller and owner.

    ``seller_percent`` overrides the configured default when provided.
    The owner receives whatever remains so the split is always exact.
    """
    total = Decimal(total).quantize(Decimal("0.01"))
    s_pct = seller_percent if seller_percent is not None else settings.default_seller_percent
    s_pct = max(0, min(100, int(s_pct)))
    o_pct = 100 - s_pct

    seller_amount = (total * Decimal(s_pct) / Decimal(100)).quantize(Decimal("0.01"))
    owner_amount = (total - seller_amount).quantize(Decimal("0.01"))
    return CommissionSplit(seller_amount, owner_amount, s_pct, o_pct)
