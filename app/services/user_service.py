"""User onboarding, role resolution and referral handling."""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.constants import Role, SellerStatus, TransactionType

from app.models import User
from app.repositories.seller_repo import SellerRepository
from app.repositories.system_repo import SystemRepository
from app.repositories.user_repo import UserRepository
from app.services.wallet_service import WalletService

REFERRAL_REWARD_KEY = "referral_reward"
DEFAULT_REFERRAL_REWARD = Decimal("0.00")


class UserService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.users = UserRepository(session)
        self.sellers = SellerRepository(session)
        self.system = SystemRepository(session)
        self.wallets = WalletService(session)

    async def resolve_role(self, user: User) -> Role:
        """Determine the effective role for a user."""
        if settings.is_owner(user.telegram_id):
            return Role.OWNER
        seller = await self.sellers.get_by_user_id(user.id)
        if seller is not None and seller.status == SellerStatus.ACTIVE:
            return Role.SELLER

        return Role.BUYER

    async def get_or_create(
        self,
        telegram_id: int,
        username: Optional[str],
        full_name: Optional[str],
        referral_code: Optional[str] = None,
    ) -> User:
        user = await self.users.get_by_telegram_id(telegram_id)
        if user is not None:
            # Keep profile fields fresh
            changed = False
            if user.username != username:
                user.username = username
                changed = True
            if user.full_name != full_name:
                user.full_name = full_name
                changed = True
            # Promote owner if configured after first contact
            if settings.is_owner(telegram_id) and user.role != Role.OWNER:
                user.role = Role.OWNER
                changed = True
            if changed:
                await self.session.flush()
            return user

        # New user
        referred_by_id: Optional[int] = None
        if referral_code:
            referrer = await self.users.get_by_referral_code(referral_code.strip())
            if referrer and referrer.telegram_id != telegram_id:
                referred_by_id = referrer.id

        role = Role.OWNER if settings.is_owner(telegram_id) else Role.BUYER
        user = await self.users.create(
            telegram_id=telegram_id,
            username=username,
            full_name=full_name,
            role=role,
            referred_by_id=referred_by_id,
        )

        if referred_by_id:
            await self._reward_referral(referred_by_id, user.id)

        await self.system.log(
            action="user_created",
            actor_id=telegram_id,
            entity="user",
            entity_id=user.id,
            detail={"role": role.value, "referred_by": referred_by_id},
        )
        return user

    async def _reward_referral(self, referrer_id: int, referred_id: int) -> None:
        if await self.users.referral_exists(referred_id):
            return
        reward_raw = await self.system.get(REFERRAL_REWARD_KEY)
        reward = Decimal(reward_raw) if reward_raw else DEFAULT_REFERRAL_REWARD
        await self.users.add_referral(referrer_id, referred_id, reward)
        if reward > 0:
            await self.wallets.credit(
                referrer_id,
                reward,
                TransactionType.REFERRAL,
                reference=f"referral:{referred_id}",
            )
