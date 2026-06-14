"""Owner handlers: dashboard, sellers, withdrawals, refunds, banners,
broadcasts, coupons, tickets, settings."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app import keyboards as kb
from app.config import settings
from app.constants import (
    BannerType,
    BroadcastTarget,
    CouponType,
    DepositStatus,
    Role,
    SellerStatus,
    TransactionType,
    enum_str,
)


from app.models import User
from app.repositories.finance_repo import FinanceRepository
from app.repositories.inventory_repo import InventoryRepository
from app.repositories.marketing_repo import MarketingRepository
from app.repositories.seller_repo import SellerRepository
from app.repositories.support_repo import SupportRepository
from app.repositories.system_repo import SystemRepository
from app.repositories.user_repo import UserRepository
from app.services import system_settings as ss
from app.services.broadcast_service import send_broadcast
from app.services.crypto_service import CryptoService
from app.services.exceptions import ServiceError

from app.services.seller_service import SellerService
from app.services.stats_service import StatsService
from app.services.support_flows import SupportFlowService
from app.services.wallet_service import WalletService
from app.services.withdrawal_service import WithdrawalService
from app.states import (
    AddSellerStates,
    BannerStates,
    BroadcastStates,
    CouponStates,
    ManageUserStates,
    SettingStates,
    SupportStates,
)

router = Router(name="owner")
CUR = settings.currency_symbol


def _is_owner(role: Role) -> bool:
    return role == Role.OWNER


async def _guard(event, role: Role) -> bool:
    if _is_owner(role):
        return True
    msg = event.message if isinstance(event, CallbackQuery) else event
    await msg.answer("⛔ Owner only.")
    if isinstance(event, CallbackQuery):
        await event.answer()
    return False


# ======================================================================
# MANAGE USERS (balances, block / unblock)
# ======================================================================
async def _render_user_card(message: Message, session: AsyncSession, target: User) -> None:
    wallet = await UserRepository(session).get_wallet(target.id)
    uname = f"@{target.username}" if target.username else "—"
    status = "🚫 Blocked" if target.is_blocked else "✅ Active"
    await message.answer(
        "👤 <b>USER</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"Name: {target.full_name or '—'}\n"
        f"Username: {uname}\n"
        f"Telegram ID: <code>{target.telegram_id}</code>\n"
        f"Role: {enum_str(target.role).title()}\n"
        f"Status: {status}\n"
        f"💰 Balance: {CUR}{wallet.balance}\n"
        "━━━━━━━━━━━━━━━━━━━━",
        reply_markup=kb.owner_user_actions(target.id, target.is_blocked),
    )


def _parse_amount(text: str | None):
    try:
        amt = Decimal((text or "").strip().lstrip(CUR))
    except (InvalidOperation, ValueError):
        return None
    return amt


@router.message(F.text == "👥 Users")
@router.callback_query(F.data == "owner:users")
async def users_entry(event, role: Role, state: FSMContext):
    if not await _guard(event, role):
        return
    message = event.message if isinstance(event, CallbackQuery) else event
    await state.set_state(ManageUserStates.lookup)
    await message.answer(
        "👥 <b>MANAGE USERS</b>\n"
        "Send a <b>Telegram ID</b> or <b>@username</b> to look up a user."
    )
    if isinstance(event, CallbackQuery):
        await event.answer()


@router.message(ManageUserStates.lookup)
async def users_lookup(message: Message, session: AsyncSession, role: Role, state: FSMContext):
    if not _is_owner(role):
        return
    await state.clear()
    q = (message.text or "").strip()
    repo = UserRepository(session)
    if q.startswith("@"):
        target = await repo.get_by_username(q)
    elif q.isdigit():
        target = await repo.get_by_telegram_id(int(q))
    else:
        target = await repo.get_by_username(q)
    if target is None:
        await message.answer("❌ User not found. Open 👥 Users to try again.")
        return
    await _render_user_card(message, session, target)


@router.callback_query(F.data.startswith("owner:um_add:"))
async def um_add_start(call: CallbackQuery, role: Role, state: FSMContext):
    if not await _guard(call, role):
        return
    target_id = int(call.data.split(":")[2])
    await state.set_state(ManageUserStates.add_amount)
    await state.update_data(target_id=target_id)
    await call.message.answer(f"➕ Enter amount to <b>ADD</b> (e.g. <code>{CUR}10</code>):")
    await call.answer()


@router.callback_query(F.data.startswith("owner:um_sub:"))
async def um_sub_start(call: CallbackQuery, role: Role, state: FSMContext):
    if not await _guard(call, role):
        return
    target_id = int(call.data.split(":")[2])
    await state.set_state(ManageUserStates.deduct_amount)
    await state.update_data(target_id=target_id)
    await call.message.answer(f"➖ Enter amount to <b>DEDUCT</b> (e.g. <code>{CUR}10</code>):")
    await call.answer()


@router.callback_query(F.data.startswith("owner:um_set:"))
async def um_set_start(call: CallbackQuery, role: Role, state: FSMContext):
    if not await _guard(call, role):
        return
    target_id = int(call.data.split(":")[2])
    await state.set_state(ManageUserStates.set_amount)
    await state.update_data(target_id=target_id)
    await call.message.answer(f"✏ Enter the <b>NEW</b> balance (e.g. <code>{CUR}25</code>):")
    await call.answer()


@router.message(ManageUserStates.add_amount)
async def um_add_apply(message: Message, session: AsyncSession, user: User, role: Role, state: FSMContext):
    if not _is_owner(role):
        return
    amt = _parse_amount(message.text)
    data = await state.get_data()
    await state.clear()
    if amt is None or amt <= 0:
        await message.answer("❌ Invalid amount.")
        return
    target_id = int(data["target_id"])
    await WalletService(session).credit(
        target_id, amt, TransactionType.ADJUSTMENT, reference=f"owner_add:{user.id}"
    )
    target = await UserRepository(session).get_by_id(target_id)
    await message.answer(f"✅ Added {CUR}{amt}.")
    await _render_user_card(message, session, target)


@router.message(ManageUserStates.deduct_amount)
async def um_sub_apply(message: Message, session: AsyncSession, user: User, role: Role, state: FSMContext):
    if not _is_owner(role):
        return
    amt = _parse_amount(message.text)
    data = await state.get_data()
    await state.clear()
    if amt is None or amt <= 0:
        await message.answer("❌ Invalid amount.")
        return
    target_id = int(data["target_id"])
    await WalletService(session).debit(
        target_id, amt, TransactionType.ADJUSTMENT,
        reference=f"owner_deduct:{user.id}", allow_negative=True,
    )
    target = await UserRepository(session).get_by_id(target_id)
    await message.answer(f"✅ Deducted {CUR}{amt}.")
    await _render_user_card(message, session, target)


@router.message(ManageUserStates.set_amount)
async def um_set_apply(message: Message, session: AsyncSession, user: User, role: Role, state: FSMContext):
    if not _is_owner(role):
        return
    new_balance = _parse_amount(message.text)
    data = await state.get_data()
    await state.clear()
    if new_balance is None or new_balance < 0:
        await message.answer("❌ Invalid amount.")
        return
    target_id = int(data["target_id"])
    wallet = await UserRepository(session).get_wallet(target_id)
    delta = new_balance - wallet.balance
    svc = WalletService(session)
    if delta > 0:
        await svc.credit(target_id, delta, TransactionType.ADJUSTMENT, reference=f"owner_set:{user.id}")
    elif delta < 0:
        await svc.debit(target_id, -delta, TransactionType.ADJUSTMENT,
                        reference=f"owner_set:{user.id}", allow_negative=True)
    target = await UserRepository(session).get_by_id(target_id)
    await message.answer(f"✅ Balance set to {CUR}{new_balance}.")
    await _render_user_card(message, session, target)


@router.callback_query(F.data.startswith("owner:um_block:"))
async def um_block(call: CallbackQuery, session: AsyncSession, role: Role):
    if not await _guard(call, role):
        return
    target_id = int(call.data.split(":")[2])
    await UserRepository(session).set_blocked(target_id, True)
    target = await UserRepository(session).get_by_id(target_id)
    await call.message.answer("🚫 User blocked.")
    await _render_user_card(call.message, session, target)
    await call.answer()


@router.callback_query(F.data.startswith("owner:um_unblock:"))
async def um_unblock(call: CallbackQuery, session: AsyncSession, role: Role):
    if not await _guard(call, role):
        return
    target_id = int(call.data.split(":")[2])
    await UserRepository(session).set_blocked(target_id, False)
    target = await UserRepository(session).get_by_id(target_id)
    await call.message.answer("✅ User unblocked.")
    await _render_user_card(call.message, session, target)
    await call.answer()


# ======================================================================
# PANEL + DASHBOARD
# ======================================================================
@router.message(F.text == "📊 Dashboard")
@router.callback_query(F.data.in_({"owner:panel", "owner:dashboard"}))
async def dashboard(event, session: AsyncSession, role: Role):
    if not await _guard(event, role):
        return
    message = event.message if isinstance(event, CallbackQuery) else event
    s = await StatsService(session).owner_dashboard()
    await message.answer(
        "👑 <b>OWNER DASHBOARD</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 Users: {s.total_users}\n"
        f"🏪 Sellers: {s.total_sellers}\n"
        f"📦 Inventory (lines): {s.total_inventory:,}\n"
        f"✅ Stock available: {s.total_stock:,}\n"
        f"🛒 Sales: {s.total_sales:,}\n"
        f"💵 Deposits: {CUR}{s.total_deposits}\n"
        f"🏦 Withdrawals: {CUR}{s.total_withdrawals}\n"
        f"💰 Revenue: {CUR}{s.total_revenue}\n"
        f"🤝 Commission earnings: {CUR}{s.commission_earnings}\n"
        f"🎫 Open tickets: {s.open_tickets}\n"
        "━━━━━━━━━━━━━━━━━━━━",
        reply_markup=kb.owner_panel(),
    )
    if isinstance(event, CallbackQuery):
        await event.answer()


# ======================================================================
# SELLERS
# ======================================================================
@router.message(F.text == "👤 Sellers")
@router.callback_query(F.data == "owner:sellers")
async def sellers_panel(event, role: Role):
    if not await _guard(event, role):
        return
    message = event.message if isinstance(event, CallbackQuery) else event
    await message.answer("👤 <b>SELLER MANAGEMENT</b>", reply_markup=kb.owner_sellers_panel())
    if isinstance(event, CallbackQuery):
        await event.answer()


@router.callback_query(F.data == "owner:add_seller")
async def add_seller_start(call: CallbackQuery, role: Role, state: FSMContext):
    if not await _guard(call, role):
        return
    await state.set_state(AddSellerStates.telegram_id)
    await call.message.answer("➕ <b>Add Seller</b>\nSend the seller's <b>Telegram ID</b>:")
    await call.answer()


@router.message(AddSellerStates.telegram_id)
async def add_seller_id(message: Message, state: FSMContext):
    if not (message.text or "").strip().isdigit():
        await message.answer("❌ Send a numeric Telegram ID.")
        return
    await state.update_data(telegram_id=int(message.text))
    await state.set_state(AddSellerStates.seller_name)
    await message.answer("Now send the <b>Seller Marketplace Name</b>:")


@router.message(AddSellerStates.seller_name)
async def add_seller_name(message: Message, session: AsyncSession, user: User, state: FSMContext, bot: Bot):
    data = await state.get_data()
    await state.clear()
    try:
        seller = await SellerService(session).add_seller(
            owner_id=user.id,
            telegram_id=data["telegram_id"],
            seller_name=(message.text or "").strip(),
        )
    except ServiceError as exc:
        await message.answer(f"⚠ {exc}")
        return
    await message.answer(
        "✅ <b>Seller created</b>\n"
        f"🏪 {seller.seller_name}\n"
        f"🆔 {seller.telegram_id}\n"
        "They now have seller permissions."
    )
    try:
        await bot.send_message(
            seller.telegram_id,
            f"🎉 You are now a seller: <b>{seller.seller_name}</b>!\n"
            "Open the menu and use 📤 Upload Stock to begin.",
        )
    except Exception:
        pass


@router.callback_query(F.data == "owner:seller_list")
async def seller_list(call: CallbackQuery, session: AsyncSession, role: Role):
    if not await _guard(call, role):
        return
    sellers = await SellerRepository(session).list_all()
    if not sellers:
        await call.message.answer("📭 No sellers yet.")
        await call.answer()
        return
    inv = InventoryRepository(session)
    await call.message.answer("📋 <b>SELLER LIST</b>")
    for s in sellers:
        offers = await inv.seller_offers(s.id)
        stock = sum(o.remaining for o in offers)
        suspended = s.status == SellerStatus.SUSPENDED
        await call.message.answer(
            f"🏪 <b>{s.seller_name}</b>\n"
            f"🆔 {s.telegram_id}\n"
            f"📊 Status: {enum_str(s.status).title()}\n"

            f"📦 Stock: {stock:,}\n"
            f"🛒 Sales: {s.total_sales}\n"
            f"💰 Revenue: {CUR}{s.total_revenue}\n"
            f"📅 {s.join_date:%Y-%m-%d}",
            reply_markup=kb.seller_actions(s.id, suspended),
        )
    await call.answer()


@router.callback_query(F.data.startswith("owner:suspend:"))
async def suspend_seller(call: CallbackQuery, session: AsyncSession, user: User, role: Role):
    if not await _guard(call, role):
        return
    sid = int(call.data.split(":")[2])
    await SellerService(session).suspend_seller(user.id, sid)
    await call.message.edit_text("⏸ Seller suspended.")
    await call.answer()


@router.callback_query(F.data.startswith("owner:unsuspend:"))
async def unsuspend_seller(call: CallbackQuery, session: AsyncSession, user: User, role: Role):
    if not await _guard(call, role):
        return
    sid = int(call.data.split(":")[2])
    await SellerService(session).unsuspend_seller(user.id, sid)
    await call.message.edit_text("✅ Seller unsuspended.")
    await call.answer()


@router.callback_query(F.data.startswith("owner:remove:"))
async def remove_seller(call: CallbackQuery, session: AsyncSession, user: User, role: Role):
    if not await _guard(call, role):
        return
    sid = int(call.data.split(":")[2])
    await SellerService(session).remove_seller(user.id, sid)
    await call.message.edit_text("🗑 Seller removed.")
    await call.answer()


# ======================================================================
# WITHDRAWALS
# ======================================================================
@router.message(F.text == "🏦 Withdrawals")
@router.callback_query(F.data == "owner:withdrawals")
async def withdrawals(event, session: AsyncSession, role: Role):
    if not await _guard(event, role):
        return
    message = event.message if isinstance(event, CallbackQuery) else event
    pending = await FinanceRepository(session).pending_withdrawals()
    if not pending:
        await message.answer("✅ No pending withdrawals.")
        if isinstance(event, CallbackQuery):
            await event.answer()
        return
    await message.answer("🏦 <b>PENDING WITHDRAWALS</b>")
    for w in pending:
        await message.answer(
            f"🆔 #{w.id}\n"
            f"💵 {CUR}{w.amount} ({w.asset})\n"
            f"🏦 <code>{w.wallet_address}</code>\n"
            f"📅 {w.created_at:%Y-%m-%d %H:%M}",
            reply_markup=kb.withdrawal_actions(w.id),
        )
    if isinstance(event, CallbackQuery):
        await event.answer()


@router.callback_query(F.data.startswith("owner:wd_ok:"))
async def withdraw_approve(call: CallbackQuery, session: AsyncSession, user: User, role: Role, bot: Bot):
    if not await _guard(call, role):
        return
    wid = int(call.data.split(":")[2])
    try:
        wd = await WithdrawalService(session).approve(user.id, wid)
    except ServiceError as exc:
        await call.answer(str(exc), show_alert=True)
        return
    await call.message.edit_text(f"✅ Withdrawal #{wid} approved.")
    target = await session.get(User, wd.user_id)
    if target:
        try:
            await bot.send_message(target.telegram_id, f"✅ Your withdrawal #{wid} was approved.")
        except Exception:
            pass
    await call.answer()


@router.callback_query(F.data.startswith("owner:wd_no:"))
async def withdraw_reject(call: CallbackQuery, session: AsyncSession, user: User, role: Role, bot: Bot):
    if not await _guard(call, role):
        return
    wid = int(call.data.split(":")[2])
    try:
        wd = await WithdrawalService(session).reject(user.id, wid, note="Rejected by owner")
    except ServiceError as exc:
        await call.answer(str(exc), show_alert=True)
        return
    await call.message.edit_text(f"❌ Withdrawal #{wid} rejected and refunded.")
    target = await session.get(User, wd.user_id)
    if target:
        try:
            await bot.send_message(
                target.telegram_id, f"❌ Your withdrawal #{wid} was rejected. Funds returned."
            )
        except Exception:
            pass
    await call.answer()


# ======================================================================
# DEPOSITS
# ======================================================================
@router.message(F.text == "💵 Deposits")
@router.callback_query(F.data == "owner:deposits")
async def deposits(event, session: AsyncSession, role: Role):
    if not await _guard(event, role):
        return
    message = event.message if isinstance(event, CallbackQuery) else event
    finance = FinanceRepository(session)
    total = await finance.total_deposits()
    pending = await finance.pending_deposits()
    manual_pending = [d for d in pending if d.asset == "MANUAL_BEP20"]
    other_pending = [d for d in pending if d.asset != "MANUAL_BEP20"]
    lines = [
        "💵 <b>DEPOSITS</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        f"✅ Total confirmed: {CUR}{total}",
        f"⏳ Pending: {len(pending)}",
        f"🏦 Manual to review: {len(manual_pending)}",
    ]
    for d in other_pending[:15]:
        lines.append(f"• #{d.id} • {d.asset} • <code>{d.address}</code>")
    await message.answer("\n".join(lines))

    # One actionable card per pending manual deposit
    for d in manual_pending[:15]:
        target = await session.get(User, d.user_id)
        tg = target.telegram_id if target else "?"
        await message.answer(
            "🏦 <b>MANUAL DEPOSIT — REVIEW</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"🧾 Ref: <code>DEP-{d.id}</code>\n"
            f"👤 User: <code>{tg}</code>\n"
            f"💲 Amount: <b>{CUR}{d.amount}</b>\n"
            f"🌐 To: <code>{d.address}</code>\n"
            f"🔗 Proof/TXID: <code>{d.txid or '—'}</code>",
            reply_markup=kb.manual_deposit_actions(d.id),
        )
    if isinstance(event, CallbackQuery):
        await event.answer()


@router.callback_query(F.data.startswith("owner:dep_ok:"))
async def deposit_approve(call: CallbackQuery, session: AsyncSession, role: Role, bot: Bot):
    if not _is_owner(role):
        await call.answer("Owner only.", show_alert=True)
        return
    dep_id = int(call.data.split(":")[2])
    finance = FinanceRepository(session)
    deposit = await finance.get_deposit(dep_id)
    if deposit is None:
        await call.answer("Deposit not found.", show_alert=True)
        return
    if deposit.status != DepositStatus.PENDING:
        await call.answer("Already processed.", show_alert=True)
        return
    target_id = deposit.user_id
    amount = deposit.amount
    credited = await CryptoService(session).confirm_deposit(
        dep_id, amount, txid=deposit.txid or f"manual:{dep_id}"
    )
    await session.commit()
    target = await session.get(User, target_id)
    if target:
        try:
            await bot.send_message(
                target.telegram_id,
                f"✅ <b>Deposit approved!</b>\n"
                f"{CUR}{credited} has been credited to your balance.\n"
                f"Reference: <code>DEP-{dep_id}</code>",
            )
        except Exception:  # noqa: BLE001
            pass
    await call.message.edit_text(
        f"✅ Approved DEP-{dep_id} • Credited {CUR}{credited}."
    )
    await call.answer("Approved & credited.")


@router.callback_query(F.data.startswith("owner:dep_no:"))
async def deposit_reject(call: CallbackQuery, session: AsyncSession, role: Role, bot: Bot):
    if not _is_owner(role):
        await call.answer("Owner only.", show_alert=True)
        return
    dep_id = int(call.data.split(":")[2])
    finance = FinanceRepository(session)
    deposit = await finance.get_deposit(dep_id)
    if deposit is None:
        await call.answer("Deposit not found.", show_alert=True)
        return
    if deposit.status != DepositStatus.PENDING:
        await call.answer("Already processed.", show_alert=True)
        return
    target_id = deposit.user_id
    await finance.set_deposit_status(dep_id, DepositStatus.FAILED, deposit.txid)
    await session.commit()
    target = await session.get(User, target_id)
    if target:
        try:
            await bot.send_message(
                target.telegram_id,
                f"❌ <b>Deposit rejected</b>\n"
                f"Reference: <code>DEP-{dep_id}</code>\n"
                "If you believe this is a mistake, contact support.",
            )
        except Exception:  # noqa: BLE001
            pass
    await call.message.edit_text(f"❌ Rejected DEP-{dep_id}.")
    await call.answer("Rejected.")


# ======================================================================
# REFUNDS
# ======================================================================

@router.message(F.text == "↩ Refunds")
@router.callback_query(F.data == "owner:refunds")
async def refunds(event, session: AsyncSession, role: Role):
    if not await _guard(event, role):
        return
    message = event.message if isinstance(event, CallbackQuery) else event
    pending = await SupportRepository(session).pending_refunds()
    if not pending:
        await message.answer("✅ No pending refunds.")
        if isinstance(event, CallbackQuery):
            await event.answer()
        return
    await message.answer("↩ <b>PENDING REFUNDS</b>")
    for r in pending:
        await message.answer(
            f"🆔 #{r.id} • Order #{r.order_id}\n"
            f"💵 {CUR}{r.amount}\n"
            f"📝 {r.reason}",
            reply_markup=kb.refund_actions(r.id),
        )
    if isinstance(event, CallbackQuery):
        await event.answer()


@router.callback_query(F.data.startswith("owner:rf_ok:"))
async def refund_approve(call: CallbackQuery, session: AsyncSession, user: User, role: Role, bot: Bot):
    if not await _guard(call, role):
        return
    rid = int(call.data.split(":")[2])
    try:
        r = await SupportFlowService(session).approve_refund(user.id, rid)
    except ServiceError as exc:
        await call.answer(str(exc), show_alert=True)
        return
    await call.message.edit_text(f"✅ Refund #{rid} approved and credited.")
    target = await session.get(User, r.user_id)
    if target:
        try:
            await bot.send_message(target.telegram_id, f"✅ Your refund #{rid} was approved.")
        except Exception:
            pass
    await call.answer()


@router.callback_query(F.data.startswith("owner:rf_no:"))
async def refund_reject(call: CallbackQuery, session: AsyncSession, user: User, role: Role, bot: Bot):
    if not await _guard(call, role):
        return
    rid = int(call.data.split(":")[2])
    try:
        r = await SupportFlowService(session).reject_refund(user.id, rid, note="Rejected")
    except ServiceError as exc:
        await call.answer(str(exc), show_alert=True)
        return
    await call.message.edit_text(f"❌ Refund #{rid} rejected.")
    target = await session.get(User, r.user_id)
    if target:
        try:
            await bot.send_message(target.telegram_id, f"❌ Your refund #{rid} was rejected.")
        except Exception:
            pass
    await call.answer()


# ======================================================================
# BANNERS
# ======================================================================
@router.message(F.text == "🖼 Banners")
@router.callback_query(F.data == "owner:banners")
async def banners(event, session: AsyncSession, role: Role, state: FSMContext):
    if not await _guard(event, role):
        return
    message = event.message if isinstance(event, CallbackQuery) else event
    existing = await MarketingRepository(session).list_banners()
    summary = "\n".join(
        f"#{b.id} • {enum_str(b.type)} • {'ON' if b.is_active else 'OFF'}" for b in existing
    ) or "None"

    await message.answer(
        "🖼 <b>BANNERS</b>\n"
        f"Current:\n{summary}\n\n"
        "Send a <b>photo</b>, <b>video</b>, or <b>GIF/animation</b> to add a new banner."
    )
    await state.set_state(BannerStates.media)
    if isinstance(event, CallbackQuery):
        await event.answer()


@router.message(BannerStates.media, F.photo | F.video | F.animation)
async def banner_media(message: Message, state: FSMContext):
    if message.photo:
        file_id, btype = message.photo[-1].file_id, BannerType.IMAGE
    elif message.video:
        file_id, btype = message.video.file_id, BannerType.VIDEO
    else:
        file_id, btype = message.animation.file_id, BannerType.GIF
    await state.update_data(file_id=file_id, btype=btype.value, caption=message.caption or "")
    await state.set_state(BannerStates.button)
    await message.answer(
        "Add a button as <code>Text|https://url</code>, or send <code>skip</code>."
    )


@router.message(BannerStates.button)
async def banner_button(message: Message, session: AsyncSession, state: FSMContext):
    data = await state.get_data()
    await state.clear()
    btn_text = btn_url = None
    raw = (message.text or "").strip()
    if raw.lower() != "skip" and "|" in raw:
        btn_text, btn_url = (p.strip() for p in raw.split("|", 1))
    await MarketingRepository(session).create_banner(
        type=BannerType(data["btype"]),
        file_id=data["file_id"],
        caption=data.get("caption") or None,
        button_text=btn_text,
        button_url=btn_url,
        is_active=True,
    )
    await message.answer("✅ Banner added and activated.")


# ======================================================================
# BROADCAST
# ======================================================================
@router.message(F.text == "📣 Broadcast")
@router.callback_query(F.data == "owner:broadcast")
async def broadcast_start(event, role: Role, state: FSMContext):
    if not await _guard(event, role):
        return
    message = event.message if isinstance(event, CallbackQuery) else event
    await state.set_state(BroadcastStates.target)
    await message.answer("📣 <b>Broadcast</b>\nChoose target:", reply_markup=kb.broadcast_targets())
    if isinstance(event, CallbackQuery):
        await event.answer()


@router.callback_query(BroadcastStates.target, F.data.startswith("owner:bc:"))
async def broadcast_target(call: CallbackQuery, state: FSMContext):
    target = call.data.split(":")[2]
    await state.update_data(target=target)
    await state.set_state(BroadcastStates.content)
    await call.message.answer(
        f"Target: <b>{target}</b>\nNow send the message (text / photo / video / document)."
    )
    await call.answer()


@router.message(BroadcastStates.content)
async def broadcast_content(message: Message, session: AsyncSession, user: User, state: FSMContext, bot: Bot):
    data = await state.get_data()
    await state.clear()
    target = BroadcastTarget(data["target"])
    role_filter = {
        BroadcastTarget.BUYERS: Role.BUYER,
        BroadcastTarget.SELLERS: Role.SELLER,
        BroadcastTarget.ALL: None,
    }[target]

    chat_ids = await UserRepository(session).all_telegram_ids(role_filter)

    content_type, text, file_id = "text", message.text or message.caption, None
    if message.photo:
        content_type, file_id = "photo", message.photo[-1].file_id
    elif message.video:
        content_type, file_id = "video", message.video.file_id
    elif message.document:
        content_type, file_id = "document", message.document.file_id

    record = await MarketingRepository(session).create_broadcast(
        owner_id=user.id, target=target, content_type=content_type, text=text, file_id=file_id
    )
    await message.answer(f"🚀 Sending to {len(chat_ids)} recipient(s)...")

    delivered, failed, blocked = await send_broadcast(
        bot, chat_ids, content_type=content_type, text=text, file_id=file_id
    )
    await MarketingRepository(session).finalize_broadcast(record.id, delivered, failed, blocked)
    await message.answer(
        "✅ <b>Broadcast complete</b>\n"
        f"📨 Delivered: {delivered}\n"
        f"❌ Failed: {failed}\n"
        f"🚫 Blocked: {blocked}"
    )


# ======================================================================
# COUPONS
# ======================================================================
@router.message(F.text == "🎟 Coupons")
@router.callback_query(F.data == "owner:coupons")
async def coupons(event, session: AsyncSession, role: Role, state: FSMContext):
    if not await _guard(event, role):
        return
    message = event.message if isinstance(event, CallbackQuery) else event
    existing = await MarketingRepository(session).list_coupons()
    summary = "\n".join(
        f"• <code>{c.code}</code> {enum_str(c.type)} {c.value} "

        f"({'ON' if c.is_active else 'OFF'}, used {c.used_count}/{c.usage_limit or '∞'})"
        for c in existing[:20]
    ) or "None"
    await message.answer(f"🎟 <b>COUPONS</b>\n{summary}\n\nSend a new coupon <b>code</b>:")
    await state.set_state(CouponStates.code)
    if isinstance(event, CallbackQuery):
        await event.answer()


@router.message(CouponStates.code)
async def coupon_code(message: Message, state: FSMContext):
    await state.update_data(code=(message.text or "").strip().upper())
    await state.set_state(CouponStates.type)
    await message.answer("Type? Send <code>percent</code> or <code>fixed</code>:")


@router.message(CouponStates.type)
async def coupon_type(message: Message, state: FSMContext):
    t = (message.text or "").strip().lower()
    if t not in ("percent", "fixed"):
        await message.answer("❌ Send 'percent' or 'fixed'.")
        return
    await state.update_data(ctype=t)
    await state.set_state(CouponStates.value)
    await message.answer("Send the value (e.g. <code>10</code> for 10% or $10):")


@router.message(CouponStates.value)
async def coupon_value(message: Message, state: FSMContext):
    try:
        value = Decimal((message.text or "").strip())
    except InvalidOperation:
        await message.answer("❌ Invalid number.")
        return
    await state.update_data(value=str(value))
    await state.set_state(CouponStates.limit)
    await message.answer("Usage limit? (0 = unlimited):")


@router.message(CouponStates.limit)
async def coupon_limit(message: Message, session: AsyncSession, state: FSMContext):
    data = await state.get_data()
    await state.clear()
    limit = int(message.text) if (message.text or "").strip().isdigit() else 0
    await MarketingRepository(session).create_coupon(
        code=data["code"],
        type=CouponType.PERCENT if data["ctype"] == "percent" else CouponType.FIXED,
        value=Decimal(data["value"]),
        usage_limit=limit,
        is_active=True,
    )
    await message.answer(f"✅ Coupon <code>{data['code']}</code> created.")


# ======================================================================
# TICKETS
# ======================================================================
@router.message(F.text == "🎫 Tickets")
@router.callback_query(F.data == "owner:tickets")
async def tickets(event, session: AsyncSession, role: Role):
    if not await _guard(event, role):
        return
    message = event.message if isinstance(event, CallbackQuery) else event
    open_tickets = await SupportRepository(session).open_tickets()
    if not open_tickets:
        await message.answer("✅ No open tickets.")
        if isinstance(event, CallbackQuery):
            await event.answer()
        return
    await message.answer("🎫 <b>OPEN TICKETS</b>")
    for t in open_tickets:
        full = await SupportRepository(session).get_ticket(t.id)
        last = full.messages[-1].text if full and full.messages else ""
        from aiogram.utils.keyboard import InlineKeyboardBuilder

        b = InlineKeyboardBuilder()
        b.button(text="✍ Reply", callback_data=f"owner:tk_reply:{t.id}")
        b.button(text="✅ Close", callback_data=f"owner:tk_close:{t.id}")
        await message.answer(
            f"#{t.id} • {t.subject}\n💬 {last[:200]}", reply_markup=b.as_markup()
        )
    if isinstance(event, CallbackQuery):
        await event.answer()


@router.callback_query(F.data.startswith("owner:tk_reply:"))
async def ticket_reply_start(call: CallbackQuery, role: Role, state: FSMContext):
    if not await _guard(call, role):
        return
    tid = int(call.data.split(":")[2])
    await state.set_state(SupportStates.reply)
    await state.update_data(ticket_id=tid)
    await call.message.answer(f"Type your reply to ticket #{tid}:")
    await call.answer()


@router.message(SupportStates.reply)
async def ticket_reply_send(message: Message, session: AsyncSession, user: User, state: FSMContext, bot: Bot):
    data = await state.get_data()
    await state.clear()
    tid = data["ticket_id"]
    ticket = await SupportFlowService(session).reply_ticket(tid, user.id, message.text or "", is_owner=True)
    if ticket is None:
        await message.answer("❌ Ticket not found.")
        return
    target = await session.get(User, ticket.user_id)
    if target:
        try:
            await bot.send_message(
                target.telegram_id, f"🎫 <b>Support reply (#{tid})</b>\n{message.text}"
            )
        except Exception:
            pass
    await message.answer("✅ Reply sent.")


@router.callback_query(F.data.startswith("owner:tk_close:"))
async def ticket_close(call: CallbackQuery, session: AsyncSession, role: Role):
    if not await _guard(call, role):
        return
    tid = int(call.data.split(":")[2])
    await SupportFlowService(session).close_ticket(tid)
    await call.message.edit_text(f"✅ Ticket #{tid} closed.")
    await call.answer()


# ======================================================================
# SETTINGS (editable pages + commission)
# ======================================================================
@router.message(F.text == "⚙ Settings")
@router.callback_query(F.data == "owner:settings")
async def settings_menu(event, role: Role):
    if not await _guard(event, role):
        return
    message = event.message if isinstance(event, CallbackQuery) else event
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    b = InlineKeyboardBuilder()
    b.button(text="🏷 Edit Bot Title", callback_data="owner:set:title")
    b.button(text="💬 Edit Subtitle", callback_data="owner:set:subtitle")
    b.button(text="👋 Edit Welcome Message", callback_data="owner:set:welcome")
    b.button(text="📜 Edit Rules", callback_data="owner:set:rules")
    b.button(text="📞 Edit Contacts", callback_data="owner:set:contacts")
    b.button(text="↩ Edit Refund Page", callback_data="owner:set:refund")
    b.button(text="🤝 Set Seller %", callback_data="owner:set:commission")
    b.adjust(1)
    await message.answer(
        "⚙ <b>SETTINGS</b>\n"
        f"Current commission: Seller {settings.default_seller_percent}% / "
        f"Owner {settings.default_owner_percent}%",
        reply_markup=b.as_markup(),
    )
    if isinstance(event, CallbackQuery):
        await event.answer()


@router.callback_query(F.data.startswith("owner:set:"))
async def settings_edit_start(call: CallbackQuery, role: Role, state: FSMContext):
    if not await _guard(call, role):
        return
    key = call.data.split(":")[2]
    await state.set_state(SettingStates.waiting_value)
    await state.update_data(key=key)
    prompts = {
        "title": (
            "🏷 Send the new <b>Bot Title</b> (shown at the top of the home page).\n"
            "Plain text — no need for emoji or bold."
        ),
        "subtitle": "💬 Send the new <b>Subtitle</b> (the small line under the title):",
        "welcome": (
            "👋 Send the new <b>Welcome Message</b> shown on /start.\n"
            "You can use <code>{name}</code> for the user's name and "
            "<code>{title}</code> for the bot title. HTML allowed."
        ),
        "rules": "Send the new Rules text (HTML allowed):",
        "contacts": "Send the new Contacts text (HTML allowed):",
        "refund": "Send the new Refund page text (HTML allowed):",
        "commission": "Send the seller percentage (0-100). Owner gets the rest:",
    }
    await call.message.answer(prompts.get(key, "Send value:"))
    await call.answer()


@router.message(SettingStates.waiting_value)
async def settings_edit_save(message: Message, session: AsyncSession, state: FSMContext):
    data = await state.get_data()
    await state.clear()
    key = data["key"]
    value = message.text or ""

    if key == "commission":
        if not value.strip().isdigit() or not (0 <= int(value) <= 100):
            await message.answer("❌ Send a whole number between 0 and 100.")
            return
        seller_pct = int(value)
        await SystemRepository(session).set("default_seller_percent", str(seller_pct))
        settings.default_seller_percent = seller_pct
        settings.default_owner_percent = 100 - seller_pct
        await message.answer(
            f"✅ Commission updated: Seller {seller_pct}% / Owner {100 - seller_pct}%"
        )
        return

    key_map = {
        "title": ss.KEY_TITLE,
        "subtitle": ss.KEY_SUBTITLE,
        "welcome": ss.KEY_WELCOME,
        "rules": ss.KEY_RULES,
        "contacts": ss.KEY_CONTACTS,
        "refund": ss.KEY_REFUND,
    }
    if key not in key_map:
        await message.answer("❌ Unknown setting.")
        return
    await ss.set_page(session, key_map[key], value)
    feedback = {
        "title": "✅ Bot title updated. Open 🏠 Home to see it.",
        "subtitle": "✅ Subtitle updated. Open 🏠 Home to see it.",
        "welcome": "✅ Welcome message updated. Send /start to preview it.",
    }
    await message.answer(feedback.get(key, "✅ Page updated."))
