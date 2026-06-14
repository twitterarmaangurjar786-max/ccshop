"""Model registry. Importing this module registers all tables on ``Base.metadata``."""
from app.models.base import Base
from app.models.user import User, Wallet, Referral
from app.models.seller import Seller
from app.models.inventory import SellerInventory, InventoryLine
from app.models.order import Order, Purchase
from app.models.finance import Transaction, Deposit, Withdrawal
from app.models.marketing import (
    Coupon,
    CouponRedemption,
    Banner,
    Broadcast,
    PreOrder,
)
from app.models.support import Ticket, TicketMessage, Refund
from app.models.system import AuditLog, Setting

__all__ = [
    "Base",
    "User",
    "Wallet",
    "Referral",
    "Seller",
    "SellerInventory",
    "InventoryLine",
    "Order",
    "Purchase",
    "Transaction",
    "Deposit",
    "Withdrawal",
    "Coupon",
    "CouponRedemption",
    "Banner",
    "Broadcast",
    "PreOrder",
    "Ticket",
    "TicketMessage",
    "Refund",
    "AuditLog",
    "Setting",
]
