"""FSM state groups."""
from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class AddSellerStates(StatesGroup):
    telegram_id = State()
    seller_name = State()


class UploadStates(StatesGroup):
    waiting_file = State()
    waiting_price = State()
    confirm = State()


class EditPriceStates(StatesGroup):
    waiting_price = State()


class SearchStates(StatesGroup):
    waiting_query = State()


class BuyStates(StatesGroup):
    waiting_quantity = State()
    waiting_coupon = State()


class WithdrawStates(StatesGroup):
    amount = State()
    address = State()


class TopUpStates(StatesGroup):
    amount = State()


class ManualDepositStates(StatesGroup):
    amount = State()
    proof = State()



class CouponStates(StatesGroup):
    code = State()
    type = State()
    value = State()
    limit = State()


class BroadcastStates(StatesGroup):
    target = State()
    content = State()


class BannerStates(StatesGroup):
    media = State()
    caption = State()
    button = State()


class SupportStates(StatesGroup):
    subject = State()
    message = State()
    reply = State()


class RefundStates(StatesGroup):
    order_id = State()
    reason = State()


class PreOrderStates(StatesGroup):
    category = State()
    quantity = State()


class SettingStates(StatesGroup):
    waiting_value = State()


class WithdrawDecisionStates(StatesGroup):
    reject_note = State()


class ManageUserStates(StatesGroup):
    lookup = State()
    add_amount = State()
    deduct_amount = State()
    set_amount = State()
