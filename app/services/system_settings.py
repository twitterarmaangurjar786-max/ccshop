"""Per-user filters (Redis) and editable Owner pages (DB settings)."""
from __future__ import annotations

import json
from decimal import Decimal
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.redis_client import get_redis
from app.repositories.system_repo import SystemRepository

FILTER_KEY = "filter:{user_id}"
FILTER_TTL = 3600  # 1 hour

# DB setting keys for editable pages
KEY_RULES = "page_rules"
KEY_CONTACTS = "page_contacts"
KEY_REFUND = "page_refund"

DEFAULT_RULES = (
    "📜 <b>MARKETPLACE RULES</b>\n\n"
    "1. All sales are final unless covered by the refund policy.\n"
    "2. Reserved stock is held for a limited time.\n"
    "3. Do not share or resell delivered codes fraudulently.\n"
    "4. Abuse leads to a permanent ban.\n\n"
    "<i>The Owner can edit this page.</i>"
)
DEFAULT_CONTACTS = (
    "📞 <b>CONTACT</b>\n\n"
    "For help, open a Support ticket from the menu.\n"
    "<i>The Owner can edit this page.</i>"
)
DEFAULT_REFUND = (
    "↩ <b>REFUND POLICY</b>\n\n"
    "Submit a refund request with your order ID and reason.\n"
    "The Owner reviews each request manually.\n"
    "<i>The Owner can edit this page.</i>"
)


# ----------------------------------------------------------------------
# Filters
# ----------------------------------------------------------------------
async def save_filter(user_id: int, data: dict) -> None:
    redis = get_redis()
    await redis.set(FILTER_KEY.format(user_id=user_id), json.dumps(data), ex=FILTER_TTL)


async def get_filter(user_id: int) -> dict:
    redis = get_redis()
    raw = await redis.get(FILTER_KEY.format(user_id=user_id))
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return {}


async def clear_filter(user_id: int) -> None:
    redis = get_redis()
    await redis.delete(FILTER_KEY.format(user_id=user_id))


async def get_active_filter_text(session: AsyncSession, user_id: int) -> str:
    data = await get_filter(user_id)
    if not data:
        return "None (showing all)"
    parts = []
    if data.get("category"):
        parts.append(f"Category {data['category']}")
    if data.get("seller_name"):
        parts.append(f"Seller {data['seller_name']}")
    if data.get("min_price") is not None:
        parts.append(f"Min {data['min_price']}")
    if data.get("max_price") is not None:
        parts.append(f"Max {data['max_price']}")
    if data.get("only_available"):
        parts.append("In stock")
    return " | ".join(parts) if parts else "None (showing all)"


# ----------------------------------------------------------------------
# Editable pages
# ----------------------------------------------------------------------
async def get_page(session: AsyncSession, key: str, default: str) -> str:
    value = await SystemRepository(session).get(key)
    return value or default


async def set_page(session: AsyncSession, key: str, value: str) -> None:
    await SystemRepository(session).set(key, value)
