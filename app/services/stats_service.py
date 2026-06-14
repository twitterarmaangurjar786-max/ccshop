"""Aggregated statistics for the home page and the owner dashboard."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import Role
from app.repositories.finance_repo import FinanceRepository
from app.repositories.inventory_repo import InventoryRepository
from app.repositories.order_repo import OrderRepository
from app.repositories.seller_repo import SellerRepository
from app.repositories.support_repo import SupportRepository
from app.repositories.user_repo import UserRepository
from app.services.online_service import online_count


@dataclass
class HomeStats:
    total_sellers: int
    total_stock: int
    total_sales: int
    online_users: int
    total_categories: int


@dataclass
class OwnerStats:
    total_users: int
    total_sellers: int
    total_inventory: int
    total_stock: int
    total_sales: int
    total_deposits: Decimal
    total_withdrawals: Decimal
    total_revenue: Decimal
    commission_earnings: Decimal
    open_tickets: int


class StatsService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.users = UserRepository(session)
        self.sellers = SellerRepository(session)
        self.inventory = InventoryRepository(session)
        self.orders = OrderRepository(session)
        self.finance = FinanceRepository(session)
        self.support = SupportRepository(session)

    async def home(self) -> HomeStats:
        return HomeStats(
            total_sellers=await self.sellers.count(),
            total_stock=await self.inventory.total_stock(),
            total_sales=await self.orders.total_sales_count(),
            online_users=await online_count(),
            total_categories=await self.inventory.category_count(),
        )

    async def owner_dashboard(self) -> OwnerStats:
        return OwnerStats(
            total_users=await self.users.count(),
            total_sellers=await self.sellers.count(),
            total_inventory=await self.inventory.total_lines(),
            total_stock=await self.inventory.total_stock(),
            total_sales=await self.orders.total_sales_count(),
            total_deposits=await self.finance.total_deposits(),
            total_withdrawals=await self.finance.total_withdrawals(),
            total_revenue=await self.orders.total_sales_amount(),
            commission_earnings=await self.finance.total_commission(),
            open_tickets=await self.support.open_ticket_count(),
        )
