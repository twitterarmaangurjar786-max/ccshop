"""User, Wallet and Referral data access."""
from __future__ import annotations

from decimal import Decimal
from typing import Optional, Sequence

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import Role
from app.models import Referral, User, Wallet
from app.utils.text import gen_referral_code


class UserRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_telegram_id(self, telegram_id: int) -> Optional[User]:
        res = await self.session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        return res.scalar_one_or_none()

    async def get_by_id(self, user_id: int) -> Optional[User]:
        return await self.session.get(User, user_id)

    async def get_by_username(self, username: str) -> Optional[User]:
        username = username.lstrip("@")
        res = await self.session.execute(
            select(User).where(func.lower(User.username) == username.lower())
        )
        return res.scalar_one_or_none()

    async def get_by_referral_code(self, code: str) -> Optional[User]:
        res = await self.session.execute(
            select(User).where(User.referral_code == code)
        )
        return res.scalar_one_or_none()

    async def create(
        self,
        telegram_id: int,
        username: Optional[str],
        full_name: Optional[str],
        role: Role = Role.BUYER,
        referred_by_id: Optional[int] = None,
    ) -> User:
        user = User(
            telegram_id=telegram_id,
            username=username,
            full_name=full_name,
            role=role,
            referral_code=gen_referral_code(),
            referred_by_id=referred_by_id,
        )
        self.session.add(user)
        await self.session.flush()
        wallet = Wallet(user_id=user.id)
        self.session.add(wallet)
        await self.session.flush()
        return user

    async def get_wallet(self, user_id: int) -> Optional[Wallet]:
        res = await self.session.execute(
            select(Wallet).where(Wallet.user_id == user_id)
        )
        wallet = res.scalar_one_or_none()
        if wallet is None:
            wallet = Wallet(user_id=user_id)
            self.session.add(wallet)
            await self.session.flush()
        return wallet

    async def get_wallet_for_update(self, user_id: int) -> Wallet:
        """Row-locked wallet fetch for safe balance mutations."""
        res = await self.session.execute(
            select(Wallet).where(Wallet.user_id == user_id).with_for_update()
        )
        wallet = res.scalar_one_or_none()
        if wallet is None:
            wallet = Wallet(user_id=user_id)
            self.session.add(wallet)
            await self.session.flush()
        return wallet

    async def set_role(self, user_id: int, role: Role) -> None:
        await self.session.execute(
            update(User).where(User.id == user_id).values(role=role)
        )

    async def set_blocked(self, user_id: int, blocked: bool) -> None:
        await self.session.execute(
            update(User).where(User.id == user_id).values(is_blocked=blocked)
        )

    async def touch_last_seen(self, user_id: int) -> None:
        await self.session.execute(
            update(User).where(User.id == user_id).values(last_seen=func.now())
        )

    async def count(self) -> int:
        res = await self.session.execute(select(func.count(User.id)))
        return int(res.scalar() or 0)

    async def count_by_role(self, role: Role) -> int:
        res = await self.session.execute(
            select(func.count(User.id)).where(User.role == role)
        )
        return int(res.scalar() or 0)

    async def all_telegram_ids(self, role: Optional[Role] = None) -> Sequence[int]:
        stmt = select(User.telegram_id).where(User.is_blocked.is_(False))
        if role is not None:
            stmt = stmt.where(User.role == role)
        res = await self.session.execute(stmt)
        return [row[0] for row in res.all()]

    # --- Referrals ---
    async def add_referral(
        self, referrer_id: int, referred_id: int, reward: Decimal
    ) -> Referral:
        referral = Referral(
            referrer_id=referrer_id,
            referred_id=referred_id,
            reward_amount=reward,
        )
        self.session.add(referral)
        await self.session.flush()
        return referral

    async def referral_exists(self, referred_id: int) -> bool:
        res = await self.session.execute(
            select(func.count(Referral.id)).where(Referral.referred_id == referred_id)
        )
        return bool(res.scalar())

    async def referral_count(self, referrer_id: int) -> int:
        res = await self.session.execute(
            select(func.count(Referral.id)).where(Referral.referrer_id == referrer_id)
        )
        return int(res.scalar() or 0)

    async def referral_earnings(self, referrer_id: int) -> Decimal:
        res = await self.session.execute(
            select(func.coalesce(func.sum(Referral.reward_amount), 0)).where(
                Referral.referrer_id == referrer_id
            )
        )
        return Decimal(res.scalar() or 0)
