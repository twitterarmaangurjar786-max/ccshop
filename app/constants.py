"""Shared enums and constant values."""
from __future__ import annotations

import enum


class Role(str, enum.Enum):
    OWNER = "owner"
    SELLER = "seller"
    BUYER = "buyer"


class SellerStatus(str, enum.Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    REMOVED = "removed"


class TransactionType(str, enum.Enum):
    DEPOSIT = "deposit"
    PURCHASE = "purchase"
    SALE = "sale"
    COMMISSION = "commission"
    WITHDRAWAL = "withdrawal"
    REFUND = "refund"
    REFERRAL = "referral"
    ADJUSTMENT = "adjustment"


class DepositStatus(str, enum.Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    EXPIRED = "expired"
    FAILED = "failed"


class WithdrawalStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    PAID = "paid"


class OrderStatus(str, enum.Enum):
    RESERVED = "reserved"
    PAID = "paid"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    REFUNDED = "refunded"


class CouponType(str, enum.Enum):
    PERCENT = "percent"
    FIXED = "fixed"


class TicketStatus(str, enum.Enum):
    OPEN = "open"
    ANSWERED = "answered"
    CLOSED = "closed"


class RefundStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class PreOrderStatus(str, enum.Enum):
    WAITING = "waiting"
    NOTIFIED = "notified"
    FULFILLED = "fulfilled"
    CANCELLED = "cancelled"


class BannerType(str, enum.Enum):
    IMAGE = "image"
    VIDEO = "video"
    GIF = "gif"


class BroadcastTarget(str, enum.Enum):
    ALL = "all"
    BUYERS = "buyers"
    SELLERS = "sellers"


class CryptoAsset(str, enum.Enum):
    USDT_TRC20 = "USDT_TRC20"
    TRX = "TRX"


def enum_str(value) -> str:
    """Return the plain string value for an Enum member or a raw string.

    Status/type columns are stored as ``String`` so the ORM returns plain
    ``str`` values when loaded from the database, while freshly built objects
    may still hold the ``Enum`` member. This helper normalises both cases so
    display/formatting code never crashes on ``.value``.
    """
    return value.value if isinstance(value, enum.Enum) else str(value)


# Redis key namespaces

RK_RESERVATION = "reservation:{order_id}"
RK_RATE_LIMIT = "ratelimit:{user_id}"
RK_ONLINE = "online:{user_id}"
RK_LINE_LOCK = "linelock:{line_id}"
RK_CACHE_HOME = "cache:home_stats"

ONLINE_TTL_SECONDS = 300  # 5 minutes => considered "online"
CATEGORY_PREFIX_LENGTH = 6
