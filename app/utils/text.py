"""Text / inventory parsing helpers."""
from __future__ import annotations

import hashlib
import re
import secrets
from decimal import Decimal, InvalidOperation
from typing import Optional

from app.config import settings
from app.constants import CATEGORY_PREFIX_LENGTH

# A valid inventory line starts with at least 6 digits which define the category.
LINE_RE = re.compile(r"^(?P<prefix>\d{6})\S*")


def extract_category(line: str) -> Optional[str]:
    """Return the first 6 characters as the category, or None if invalid.

    The category is ALWAYS the first 6 digits of an inventory line.
    """
    line = line.strip()
    if not line:
        return None
    match = LINE_RE.match(line)
    if not match:
        return None
    return match.group("prefix")


def is_valid_line(line: str) -> bool:
    return extract_category(line) is not None


def line_hash(line: str) -> str:
    """Stable hash used for duplicate detection."""
    normalized = line.strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def parse_price(raw: str) -> Optional[Decimal]:
    raw = raw.strip().replace(",", ".").lstrip(settings.currency_symbol)
    try:
        value = Decimal(raw)
    except (InvalidOperation, ValueError):
        return None
    if value <= 0:
        return None
    return value.quantize(Decimal("0.01"))


def parse_int(raw: str) -> Optional[int]:
    raw = raw.strip()
    if not raw.isdigit():
        return None
    value = int(raw)
    return value if value > 0 else None


def money(amount) -> str:
    return f"{settings.currency_symbol}{Decimal(amount):,.2f}"


def gen_referral_code(length: int = 8) -> str:
    return secrets.token_hex(length // 2 + 1)[:length].upper()


def short(text: str, length: int = 40) -> str:
    text = (text or "").strip()
    return text if len(text) <= length else text[: length - 1] + "…"
