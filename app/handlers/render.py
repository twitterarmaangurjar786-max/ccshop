"""Shared rendering helpers (home page, profile, banners)."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.constants import Role
from app.models import User
from app.repositories.marketing_repo import MarketingRepository
from app.repositories.seller_repo import SellerRepository
from app.repositories.user_repo import UserRepository
from app.services.stats_service import StatsService
from app.services.system_settings import get_active_filter_text

CUR = settings.currency_symbol


async def render_home(session: AsyncSession, user: User, role: Role) -> tuple[str, object | None]:
    """Return (caption, banner) for the home page."""
    stats = await StatsService(session).home()
    marketing = MarketingRepository(session)
    banners = await marketing.list_banners(only_active=True)
    banner = banners[0] if banners else None

    filter_text = await get_active_filter_text(session, user.id)

    text = (
        "🏪 <b>FLAFA SPRITE CC SHOP</b>\n"
        "<i>CC inventory from verified sellers</i>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"👥 <b>Sellers:</b> {stats.total_sellers}\n"
        f"📦 <b>Total Stock:</b> {stats.total_stock:,}\n"
        f"🗂 <b>Categories:</b> {stats.total_categories}\n"
        f"🛒 <b>Total Sales:</b> {stats.total_sales:,}\n"
        f"🟢 <b>Online:</b> {stats.online_users}\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"🔎 <b>Active Filter:</b> {filter_text}\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Browse a category, search a 6-digit code, or pick a seller below."
    )
    return text, banner


async def render_profile(session: AsyncSession, user: User, role: Role) -> str:
    users = UserRepository(session)
    wallet = await users.get_wallet(user.id)
    ref_count = await users.referral_count(user.id)
    ref_earn = await users.referral_earnings(user.id)

    lines = [
        "👤 <b>YOUR PROFILE</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        f"🆔 <b>ID:</b> <code>{user.telegram_id}</code>",
        f"🎭 <b>Role:</b> {role.value.title()}",
        f"💰 <b>Balance:</b> {CUR}{wallet.balance}",
        f"📥 <b>Deposited:</b> {CUR}{wallet.total_deposited}",
        f"📤 <b>Spent:</b> {CUR}{wallet.total_spent}",
    ]
    if role == Role.SELLER:
        seller = await SellerRepository(session).get_by_user_id(user.id)
        if seller:
            lines += [
                "━━━━━━━━━━━━━━━━━━━━",
                f"🏪 <b>Store:</b> {seller.seller_name}",
                f"💵 <b>Earned:</b> {CUR}{wallet.total_earned}",
                f"🛒 <b>Sales:</b> {seller.total_sales}",
            ]
    lines += [
        "━━━━━━━━━━━━━━━━━━━━",
        f"🔗 <b>Referral code:</b> <code>{user.referral_code}</code>",
        f"👥 <b>Referrals:</b> {ref_count}  •  Earned: {CUR}{ref_earn}",
    ]
    return "\n".join(lines)
