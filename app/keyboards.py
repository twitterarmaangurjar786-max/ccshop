"""Reply & inline keyboards for all roles."""
from __future__ import annotations

from typing import Sequence

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

from app.config import settings

# ----------------------------------------------------------------------
# Main reply menus
# ----------------------------------------------------------------------

def buyer_menu() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    kb.row(KeyboardButton(text="🔎 Search"), KeyboardButton(text="👥 Sellers"))
    kb.row(KeyboardButton(text="🔍 Filters"), KeyboardButton(text="📦 Pre-Order"))
    kb.row(KeyboardButton(text="💰 Top Up"), KeyboardButton(text="🎟 Discount"))
    kb.row(KeyboardButton(text="📄 Export"), KeyboardButton(text="📜 Rules"))
    kb.row(KeyboardButton(text="↩ Refund"), KeyboardButton(text="🎫 Support"))
    kb.row(KeyboardButton(text="📞 Contacts"), KeyboardButton(text="👤 Profile"))
    kb.row(KeyboardButton(text="🏠 Home"))
    return kb.as_markup(resize_keyboard=True)


def seller_menu() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    kb.row(KeyboardButton(text="📤 Upload Stock"), KeyboardButton(text="📦 Inventory"))
    kb.row(KeyboardButton(text="📊 Statistics"), KeyboardButton(text="💰 Earnings"))
    kb.row(KeyboardButton(text="🏦 Withdraw"), KeyboardButton(text="📜 Sales History"))
    kb.row(KeyboardButton(text="🏠 Home"))
    return kb.as_markup(resize_keyboard=True)


def owner_menu() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    kb.row(KeyboardButton(text="📊 Dashboard"), KeyboardButton(text="👤 Sellers"))
    kb.row(KeyboardButton(text="🏦 Withdrawals"), KeyboardButton(text="💵 Deposits"))
    kb.row(KeyboardButton(text="🖼 Banners"), KeyboardButton(text="📣 Broadcast"))
    kb.row(KeyboardButton(text="🎟 Coupons"), KeyboardButton(text="🎫 Tickets"))
    kb.row(KeyboardButton(text="↩ Refunds"), KeyboardButton(text="⚙ Settings"))
    kb.row(KeyboardButton(text="👥 Users"), KeyboardButton(text="🏠 Home"))
    return kb.as_markup(resize_keyboard=True)


def home_nav(is_owner: bool, is_seller: bool) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="🔎 Search", callback_data="buyer:search"),
        InlineKeyboardButton(text="👥 Sellers", callback_data="buyer:sellers"),
    )
    kb.row(
        InlineKeyboardButton(text="💰 Top Up", callback_data="buyer:topup"),
        InlineKeyboardButton(text="👤 Profile", callback_data="nav:profile"),
    )
    if is_seller:
        kb.row(InlineKeyboardButton(text="🏪 Seller Panel", callback_data="seller:panel"))
    if is_owner:
        kb.row(InlineKeyboardButton(text="👑 Owner Panel", callback_data="owner:panel"))
    return kb.as_markup()


# ----------------------------------------------------------------------
# Owner inline panels
# ----------------------------------------------------------------------

def owner_panel() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="📊 Dashboard", callback_data="owner:dashboard"),
        InlineKeyboardButton(text="👤 Sellers", callback_data="owner:sellers"),
    )
    kb.row(
        InlineKeyboardButton(text="🏦 Withdrawals", callback_data="owner:withdrawals"),
        InlineKeyboardButton(text="↩ Refunds", callback_data="owner:refunds"),
    )
    kb.row(
        InlineKeyboardButton(text="🖼 Banners", callback_data="owner:banners"),
        InlineKeyboardButton(text="📣 Broadcast", callback_data="owner:broadcast"),
    )
    kb.row(
        InlineKeyboardButton(text="🎟 Coupons", callback_data="owner:coupons"),
        InlineKeyboardButton(text="🎫 Tickets", callback_data="owner:tickets"),
    )
    kb.row(
        InlineKeyboardButton(text="👥 Users", callback_data="owner:users"),
        InlineKeyboardButton(text="⚙ Settings", callback_data="owner:settings"),
    )
    return kb.as_markup()


def owner_user_actions(target_user_id: int, blocked: bool) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="➕ Add Money", callback_data=f"owner:um_add:{target_user_id}"),
        InlineKeyboardButton(text="➖ Deduct", callback_data=f"owner:um_sub:{target_user_id}"),
    )
    kb.row(
        InlineKeyboardButton(text="✏ Set Balance", callback_data=f"owner:um_set:{target_user_id}")
    )
    if blocked:
        kb.row(
            InlineKeyboardButton(text="✅ Unblock", callback_data=f"owner:um_unblock:{target_user_id}")
        )
    else:
        kb.row(
            InlineKeyboardButton(text="🚫 Block", callback_data=f"owner:um_block:{target_user_id}")
        )
    kb.row(InlineKeyboardButton(text="🔎 Look up another", callback_data="owner:users"))
    kb.row(InlineKeyboardButton(text="⬅ Back", callback_data="owner:panel"))
    return kb.as_markup()


def owner_sellers_panel() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="➕ Add Seller", callback_data="owner:add_seller"),
        InlineKeyboardButton(text="📋 Seller List", callback_data="owner:seller_list"),
    )
    kb.row(InlineKeyboardButton(text="⬅ Back", callback_data="owner:panel"))
    return kb.as_markup()


def seller_actions(seller_id: int, suspended: bool) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if suspended:
        kb.row(
            InlineKeyboardButton(
                text="✅ Unsuspend", callback_data=f"owner:unsuspend:{seller_id}"
            )
        )
    else:
        kb.row(
            InlineKeyboardButton(
                text="⏸ Suspend", callback_data=f"owner:suspend:{seller_id}"
            )
        )
    kb.row(
        InlineKeyboardButton(text="🗑 Remove", callback_data=f"owner:remove:{seller_id}")
    )
    kb.row(InlineKeyboardButton(text="⬅ Back", callback_data="owner:seller_list"))
    return kb.as_markup()


def withdrawal_actions(withdrawal_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="✅ Approve", callback_data=f"owner:wd_ok:{withdrawal_id}"),
        InlineKeyboardButton(text="❌ Reject", callback_data=f"owner:wd_no:{withdrawal_id}"),
    )
    return kb.as_markup()


def refund_actions(refund_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="✅ Approve", callback_data=f"owner:rf_ok:{refund_id}"),
        InlineKeyboardButton(text="❌ Reject", callback_data=f"owner:rf_no:{refund_id}"),
    )
    return kb.as_markup()


def broadcast_targets() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="📢 All", callback_data="owner:bc:all"),
        InlineKeyboardButton(text="🛒 Buyers", callback_data="owner:bc:buyers"),
        InlineKeyboardButton(text="🏪 Sellers", callback_data="owner:bc:sellers"),
    )
    return kb.as_markup()


# ----------------------------------------------------------------------
# Seller inline panel
# ----------------------------------------------------------------------

def seller_panel() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="📤 Upload Stock", callback_data="seller:upload"),
        InlineKeyboardButton(text="📦 Inventory", callback_data="seller:inventory"),
    )
    kb.row(
        InlineKeyboardButton(text="📊 Statistics", callback_data="seller:stats"),
        InlineKeyboardButton(text="💰 Earnings", callback_data="seller:earnings"),
    )
    kb.row(
        InlineKeyboardButton(text="🏦 Withdraw", callback_data="seller:withdraw"),
        InlineKeyboardButton(text="📜 Sales History", callback_data="seller:sales"),
    )
    return kb.as_markup()


def upload_confirm() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="✅ Confirm Upload", callback_data="seller:upload_confirm"),
        InlineKeyboardButton(text="❌ Cancel", callback_data="seller:upload_cancel"),
    )
    return kb.as_markup()


def offer_edit(offer_id: int, can_edit_price: bool) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if can_edit_price:
        kb.row(
            InlineKeyboardButton(text="✏ Edit Price", callback_data=f"seller:price:{offer_id}"),
            InlineKeyboardButton(text="🗑 Delete", callback_data=f"seller:del:{offer_id}"),
        )
    return kb.as_markup()


# ----------------------------------------------------------------------
# Buyer inline panels
# ----------------------------------------------------------------------

def topup_assets() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(
            text="⚡ Pay with xRocket", callback_data="buyer:topup:XROCKET"
        )
    )
    if settings.manual_bep20_address:
        kb.row(
            InlineKeyboardButton(
                text="🏦 Manual Payment (USDT BEP20)",
                callback_data="buyer:topup:MANUAL",
            )
        )
    return kb.as_markup()


def manual_deposit_actions(deposit_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="✅ Approve", callback_data=f"owner:dep_ok:{deposit_id}"),
        InlineKeyboardButton(text="❌ Reject", callback_data=f"owner:dep_no:{deposit_id}"),
    )
    return kb.as_markup()


def xrocket_pay(link: str, deposit_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="⚡ Pay with xRocket", url=link))
    kb.row(
        InlineKeyboardButton(
            text="✅ I've Paid — Check now", callback_data=f"buyer:xrcheck:{deposit_id}"
        )
    )
    return kb.as_markup()


def category_list(categories: Sequence[tuple[str, int, int]]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for category, stock, sellers in categories[:30]:
        kb.row(
            InlineKeyboardButton(
                text=f"🗂 {category}  •  {stock} in stock  •  {sellers} seller(s)",
                callback_data=f"buyer:cat:{category}",
            )
        )
    return kb.as_markup()


def offer_list(offers: Sequence[tuple]) -> InlineKeyboardMarkup:
    """offers: list of (offer, seller)."""
    kb = InlineKeyboardBuilder()
    for offer, seller in offers[:30]:
        kb.row(
            InlineKeyboardButton(
                text=f"🏪 {seller.seller_name} • ${offer.price} • {offer.remaining} stock",
                callback_data=f"buyer:offer:{offer.id}",
            )
        )
    return kb.as_markup()


def buy_confirm(offer_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="✅ Confirm & Pay", callback_data=f"buyer:pay:{offer_id}"),
        InlineKeyboardButton(text="❌ Cancel", callback_data="buyer:cancel"),
    )
    return kb.as_markup()


def order_pay(order_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="✅ Pay Now", callback_data=f"buyer:confirm:{order_id}"),
        InlineKeyboardButton(text="❌ Cancel", callback_data=f"buyer:abort:{order_id}"),
    )
    return kb.as_markup()


def delivery_actions(order_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="📥 Download TXT", callback_data=f"buyer:dl:{order_id}")
    )
    return kb.as_markup()


def back_button(callback: str = "nav:home") -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="⬅ Back", callback_data=callback))
    return kb.as_markup()
