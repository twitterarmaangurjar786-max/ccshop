  """Buyer handlers: search, browse, purchase, top-up, filters, export, etc."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app import keyboards as kb
from app.config import settings
from app.constants import CryptoAsset, DepositStatus, SellerStatus, enum_str

from app.models import User
from app.repositories.finance_repo import FinanceRepository
from app.repositories.inventory_repo import InventoryRepository
from app.repositories.order_repo import OrderRepository
from app.repositories.seller_repo import SellerRepository
from app.repositories.user_repo import UserRepository
from app.services import system_settings as ss
from app.services.crypto_service import CryptoService
from app.services.exceptions import ServiceError
from app.services.purchase_service import PurchaseService
from app.services.support_flows import SupportFlowService
from app.states import (
    BuyStates,
    ManualDepositStates,
    PreOrderStates,
    RefundStates,
    SearchStates,
    SupportStates,
    TopUpStates,
)

from app.utils.inventory_parser import extract_category

router = Router(name="buyer")
CUR = settings.currency_symbol


def _txt_file(lines: list[str], name: str) -> BufferedInputFile:
    data = "\n".join(lines).encode("utf-8")
    return BufferedInputFile(data, filename=name)


# ======================================================================
# SEARCH
# ======================================================================
@router.message(F.text == "🔎 Search")
@router.message(Command("search"))
async def ask_search(message: Message, state: FSMContext):
    await state.set_state(SearchStates.waiting_query)
    await message.answer(
        "🔎 <b>Search</b>\nSend a category code (first 6 digits), e.g. <code>123456</code>."
    )


@router.callback_query(F.data == "buyer:search")
async def cb_ask_search(call: CallbackQuery, state: FSMContext):
    await state.set_state(SearchStates.waiting_query)
    await call.message.answer("🔎 Send a 6-digit category code, e.g. <code>123456</code>.")
    await call.answer()


@router.message(SearchStates.waiting_query)
async def do_search(message: Message, session: AsyncSession, user: User, state: FSMContext):
    await state.clear()
    query = (message.text or "").strip()
    category = query if (query.isdigit() and len(query) >= 6) else extract_category(query)
    if not category:
        await message.answer("❌ Invalid code. Send at least 6 digits.")
        return
    await _show_category(message, session, user, category)


async def _show_category(message: Message, session: AsyncSession, user: User, category: str):
    flt = await ss.get_filter(user.id)
    repo = InventoryRepository(session)
    offers = await repo.offers_for_category(
        category,
        min_price=Decimal(str(flt["min_price"])) if flt.get("min_price") is not None else None,
        max_price=Decimal(str(flt["max_price"])) if flt.get("max_price") is not None else None,
        only_available=True,
    )
    if not offers:
        await message.answer(
            f"📭 No stock for category <b>{category}</b> right now.\n"
            "Tip: create a 📦 Pre-Order to get notified when it arrives."
        )
        return
    text = [f"🗂 <b>Category: {category}</b>", "━━━━━━━━━━━━━━━━━━━━"]
    for offer, seller in offers:
        text.append(
            f"🏪 <b>{seller.seller_name}</b>\n"
            f"   💲 Price: {CUR}{offer.price}\n"
            f"   📦 Stock: {offer.remaining:,}"
        )
    text.append("━━━━━━━━━━━━━━━━━━━━\nSelect a seller to buy:")
    await message.answer("\n".join(text), reply_markup=kb.offer_list(offers))


# ======================================================================
# SELLERS PAGE
# ======================================================================
@router.message(F.text == "👥 Sellers")
@router.callback_query(F.data == "buyer:sellers")
async def show_sellers(event, session: AsyncSession):
    message = event.message if isinstance(event, CallbackQuery) else event
    sellers = await SellerRepository(session).list_active()
    inv = InventoryRepository(session)
    if not sellers:
        await message.answer("📭 No sellers yet.")
        if isinstance(event, CallbackQuery):
            await event.answer()
        return
    lines = ["👥 <b>SELLERS</b>", "━━━━━━━━━━━━━━━━━━━━"]
    for s in sellers:
        offers = await inv.seller_offers(s.id)
        stock = sum(o.remaining for o in offers)
        lines.append(
            f"🏪 <b>{s.seller_name}</b>\n"
            f"   📦 Available: {stock:,}\n"
            f"   🛒 Sales: {s.total_sales}\n"
            f"   ✅ {enum_str(s.status).title()}"

        )
    await message.answer("\n".join(lines))
    if isinstance(event, CallbackQuery):
        await event.answer()


# ======================================================================
# CATEGORY / OFFER selection
# ======================================================================
@router.callback_query(F.data.startswith("buyer:cat:"))
async def cb_category(call: CallbackQuery, session: AsyncSession, user: User):
    category = call.data.split(":", 2)[2]
    await _show_category(call.message, session, user, category)
    await call.answer()


@router.callback_query(F.data.startswith("buyer:offer:"))
async def cb_offer(call: CallbackQuery, session: AsyncSession, state: FSMContext):
    offer_id = int(call.data.split(":")[2])
    offer = await InventoryRepository(session).get_offer(offer_id)
    if offer is None or offer.remaining <= 0:
        await call.answer("Out of stock.", show_alert=True)
        return
    seller = await SellerRepository(session).get_by_id(offer.seller_id)
    await state.set_state(BuyStates.waiting_quantity)
    await state.update_data(offer_id=offer_id)
    await call.message.answer(
        f"🏪 <b>{seller.seller_name}</b>\n"
        f"🗂 Category: <b>{offer.category}</b>\n"
        f"💲 Price: {CUR}{offer.price} / line\n"
        f"📦 Available: {offer.remaining:,}\n\n"
        "How many lines do you want?\n"
        "<i>Optionally add a coupon: e.g. <code>100 SAVE10</code></i>"
    )
    await call.answer()


@router.message(BuyStates.waiting_quantity)
async def do_reserve(message: Message, session: AsyncSession, user: User, state: FSMContext):
    data = await state.get_data()
    offer_id = data.get("offer_id")
    parts = (message.text or "").split()
    if not parts or not parts[0].isdigit():
        await message.answer("❌ Send a number, e.g. <code>100</code>.")
        return
    quantity = int(parts[0])
    coupon = parts[1] if len(parts) > 1 else None
    await state.clear()
    try:
        service = PurchaseService(session)
        order = await service.reserve(user.id, offer_id, quantity, coupon)
    except ServiceError as exc:
        await message.answer(f"⚠ {exc}")
        return
    discount_line = f"🎟 Discount: -{CUR}{order.discount}\n" if order.discount > 0 else ""
    await message.answer(
        "🧾 <b>ORDER RESERVED</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"🗂 Category: {order.category}\n"
        f"🔢 Quantity: {order.quantity:,}\n"
        f"💲 Unit: {CUR}{order.unit_price}\n"
        f"🧮 Subtotal: {CUR}{order.subtotal}\n"
        f"{discount_line}"
        f"💰 <b>Total: {CUR}{order.total}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"⏳ Reserved for {settings.reservation_minutes} min. Pay to receive your codes.",
        reply_markup=kb.order_pay(order.id),
    )


@router.callback_query(F.data.startswith("buyer:confirm:"))
async def cb_confirm(call: CallbackQuery, session: AsyncSession, user: User):
    order_id = int(call.data.split(":")[2])
    try:
        service = PurchaseService(session)
        order, lines = await service.confirm(order_id, user.id)
    except ServiceError as exc:
        await call.answer()
        await call.message.answer(f"⚠ {exc}")
        return

    await call.message.answer(
        "✅ <b>PAYMENT SUCCESSFUL</b>\n"
        f"📦 Delivered {len(lines):,} line(s) for category {order.category}.\n"
        f"💰 Charged: {CUR}{order.total}"
    )
    # Telegram message delivery (chunked) + TXT file
    preview = "\n".join(lines[:50])
    await call.message.answer(
        f"<b>Your codes</b> (showing up to 50):\n<code>{preview}</code>",
        reply_markup=kb.delivery_actions(order.id),
    )
    await call.message.answer_document(
        _txt_file(lines, f"order_{order.id}.txt"), caption="📥 Full delivery (TXT)"
    )
    await call.answer("Delivered!")


@router.callback_query(F.data.startswith("buyer:abort:"))
async def cb_abort(call: CallbackQuery, session: AsyncSession, user: User):
    order_id = int(call.data.split(":")[2])
    await PurchaseService(session).cancel(order_id, user.id)
    await call.message.edit_text("❌ Reservation cancelled. Stock released.")
    await call.answer()


@router.callback_query(F.data == "buyer:cancel")
async def cb_cancel(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.answer("❌ Cancelled.")
    await call.answer()


@router.callback_query(F.data.startswith("buyer:dl:"))
async def cb_download(call: CallbackQuery, session: AsyncSession, user: User):
    order_id = int(call.data.split(":")[2])
    order = await OrderRepository(session).get(order_id)
    if order is None or order.buyer_id != user.id:
        await call.answer("Not found.", show_alert=True)
        return
    lines = await PurchaseService(session).delivered_lines(order_id)
    await call.message.answer_document(
        _txt_file(lines, f"order_{order_id}.txt"), caption="📥 Your delivery"
    )
    await call.answer()


# ======================================================================
# TOP UP (crypto deposit)
# ======================================================================
@router.message(F.text == "💰 Top Up")
@router.callback_query(F.data == "buyer:topup")
async def topup_menu(event, **_):
    message = event.message if isinstance(event, CallbackQuery) else event
    await message.answer("💰 <b>Top Up</b>\nChoose a deposit asset:", reply_markup=kb.topup_assets())
    if isinstance(event, CallbackQuery):
        await event.answer()


@router.callback_query(F.data.startswith("buyer:topup:"))
async def topup_asset(call: CallbackQuery, session: AsyncSession, user: User, state: FSMContext):
    asset = call.data.split(":")[2]

    # --- xRocket Pay rail (Telegram instant crypto payment) ---
    if asset == "XROCKET":
        if not CryptoService.xrocket_enabled():
            await call.answer("xRocket is not configured.", show_alert=True)
            return
        await state.set_state(TopUpStates.amount)
        await call.message.answer(
            "⚡ <b>xRocket Top Up</b>\n"
            f"Enter the amount in {settings.xrocket_currency} you want to "
            "deposit (e.g. <code>10</code>):"
        )
        await call.answer()
        return

    # --- Manual payment rail (owner approves) ---
    if asset == "MANUAL":
        if not settings.manual_bep20_address:
            await call.answer("Manual payment is not configured.", show_alert=True)
            return
        await state.set_state(ManualDepositStates.amount)
        await call.message.answer(
            "🏦 <b>Manual Top Up</b>\n"
            f"Network: <b>{settings.manual_payment_label}</b>\n\n"
            f"Enter the amount in USD you want to deposit (e.g. <code>10</code>):"
        )
        await call.answer()
        return

    # --- On-chain TRON rail ---
    try:
        crypto_asset = CryptoAsset(asset)
    except ValueError:
        await call.answer("Unsupported.", show_alert=True)
        return
    deposit = await CryptoService(session).create_deposit(user.id, crypto_asset)
    await call.message.answer(
        "🏦 <b>DEPOSIT</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"Asset: <b>{crypto_asset.value}</b>\n"
        f"Send funds to:\n<code>{deposit.address}</code>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Your balance is credited automatically after on-chain confirmation.\n"
        f"Reference: <code>DEP-{deposit.id}</code>"
    )
    await call.answer()


@router.message(TopUpStates.amount)
async def topup_xrocket_amount(
    message: Message, session: AsyncSession, user: User, state: FSMContext
):
    raw = (message.text or "").strip().lstrip(settings.currency_symbol)
    try:
        amount = Decimal(raw)
    except (InvalidOperation, ValueError):
        await message.answer("❌ Send a valid number, e.g. <code>10</code>")
        return
    if amount <= 0:
        await message.answer("❌ Amount must be greater than 0.")
        return
    await state.clear()
    try:
        deposit, link = await CryptoService(session).create_xrocket_deposit(user.id, amount)
    except Exception as exc:  # noqa: BLE001
        await message.answer(f"❌ Could not create the invoice: {exc}")
        return
    await message.answer(
        "⚡ <b>xROCKET INVOICE</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"Amount: <b>{CUR}{amount}</b>\n"
        f"Reference: <code>DEP-{deposit.id}</code>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "1️⃣ Tap <b>Pay with xRocket</b>\n"
        "2️⃣ Complete the payment inside xRocket\n"
        "3️⃣ Tap <b>I've Paid — Check now</b>\n\n"
        "Your balance is credited automatically.",
        reply_markup=kb.xrocket_pay(link, deposit.id),
    )


@router.callback_query(F.data.startswith("buyer:xrcheck:"))
async def topup_xrocket_check(call: CallbackQuery, session: AsyncSession, user: User):
    deposit_id = int(call.data.split(":")[2])
    credited = await CryptoService(session).check_one_xrocket(deposit_id)
    if credited:
        await call.message.answer(
            f"✅ <b>Payment received!</b>\n{CUR}{credited} has been credited to your balance."
        )
        await call.answer("Credited!")
    else:
        await call.answer(
            "Not paid yet. Complete the payment, then tap Check again.", show_alert=True
        )


# ======================================================================
# MANUAL TOP UP (owner-approved BEP20)
# ======================================================================
@router.message(ManualDepositStates.amount)
async def manual_amount(message: Message, state: FSMContext):
    raw = (message.text or "").strip().lstrip(settings.currency_symbol)
    try:
        amount = Decimal(raw)
    except (InvalidOperation, ValueError):
        await message.answer("❌ Send a valid number, e.g. <code>10</code>")
        return
    if amount <= 0:
        await message.answer("❌ Amount must be greater than 0.")
        return
    await state.update_data(amount=str(amount))
    await state.set_state(ManualDepositStates.proof)
    await message.answer(
        "🏦 <b>MANUAL PAYMENT</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"💲 Amount: <b>{CUR}{amount}</b>\n"
        f"🌐 Network: <b>{settings.manual_payment_label}</b>\n\n"
        f"Send <b>{CUR}{amount}</b> (USDT) to this address:\n"
        f"<code>{settings.manual_bep20_address}</code>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "After paying, reply here with the <b>transaction hash (TXID)</b> "
        "or a payment <b>screenshot</b>.\n"
        "The Owner will verify it and credit your balance."
    )


@router.message(ManualDepositStates.proof)
async def manual_proof(message: Message, session: AsyncSession, user: User, state: FSMContext):
    data = await state.get_data()
    amount = Decimal(data.get("amount", "0"))
    proof = (message.text or message.caption or "(screenshot attached)").strip()[:128]
    await state.clear()

    deposit = await FinanceRepository(session).create_deposit(
        user_id=user.id,
        asset="MANUAL_BEP20",
        amount=amount,
        address=settings.manual_bep20_address,
        status=DepositStatus.PENDING,
        txid=proof,
    )
    await session.flush()
    dep_id = deposit.id
    await session.commit()

    await message.answer(
        "✅ <b>Request submitted!</b>\n"
        f"🧾 Reference: <code>DEP-{dep_id}</code>\n"
        f"💲 Amount: <b>{CUR}{amount}</b>\n\n"
        "The Owner will verify your payment and credit your balance. "
        "You'll be notified once it's approved."
    )

    uname = f"@{user.username}" if getattr(user, "username", None) else "—"
    owner_text = (
        "🏦 <b>NEW MANUAL DEPOSIT</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"🧾 Ref: <code>DEP-{dep_id}</code>\n"
        f"👤 User: <code>{user.telegram_id}</code> ({uname})\n"
        f"💲 Amount: <b>{CUR}{amount}</b>\n"
        f"🌐 Network: {settings.manual_payment_label}\n"
        f"🔗 Proof/TXID: <code>{proof}</code>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Verify the payment, then Approve or Reject."
    )
    for oid in settings.owner_ids:
        try:
            await message.bot.send_message(
                oid, owner_text, reply_markup=kb.manual_deposit_actions(dep_id)
            )
            if message.photo or message.document:
                await message.bot.copy_message(oid, message.chat.id, message.message_id)
        except Exception:  # noqa: BLE001
            pass


# ======================================================================
# DISCOUNT
# ======================================================================
@router.message(F.text == "🎟 Discount")
async def discount_info(message: Message):
    await message.answer(
        "🎟 <b>Discounts</b>\n"
        "Have a coupon? Apply it while buying by sending:\n"
        "<code>QUANTITY COUPONCODE</code>\n"
        "Example: <code>100 SAVE10</code>"
    )


# ======================================================================
# FILTERS
# ======================================================================
@router.message(F.text == "🔍 Filters")
async def filters_menu(message: Message, session: AsyncSession, user: User):
    current = await ss.get_active_filter_text(session, user.id)
    await message.answer(
        "🔍 <b>FILTERS</b>\n"
        f"Active: <b>{current}</b>\n\n"
        "Set a filter by sending:\n"
        "<code>cat=123456 min=1 max=3</code>\n"
        "Send <code>clear</code> to reset."
    )
    await message.answer("Send your filter now or /cancel.")


@router.message(F.text.func(lambda t: bool(t) and (t.startswith("cat=") or t.strip().lower() == "clear")))
async def apply_filter(message: Message, user: User):

    raw = (message.text or "").strip()
    if raw.lower() == "clear":
        await ss.clear_filter(user.id)
        await message.answer("✅ Filter cleared.")
        return
    data: dict = {}
    for tok in raw.split():
        if tok.startswith("cat=") and tok[4:].isdigit():
            data["category"] = tok[4:][:6]
        elif tok.startswith("min="):
            try:
                data["min_price"] = float(tok[4:])
            except ValueError:
                pass
        elif tok.startswith("max="):
            try:
                data["max_price"] = float(tok[4:])
            except ValueError:
                pass
    data["only_available"] = True
    await ss.save_filter(user.id, data)
    await message.answer("✅ Filter saved. Open Search or a category to see results.")


# ======================================================================
# EXPORT (buyer's purchased lines)
# ======================================================================
@router.message(F.text == "📄 Export")
async def export_history(message: Message, session: AsyncSession, user: User):
    orders = await OrderRepository(session).buyer_orders(user.id, limit=100)
    if not orders:
        await message.answer("📭 You have no purchases to export.")
        return
    all_lines: list[str] = []
    service = PurchaseService(session)
    for o in orders:
        all_lines += await service.delivered_lines(o.id)
    await message.answer_document(
        _txt_file(all_lines, "my_purchases.txt"),
        caption=f"📄 Exported {len(all_lines):,} purchased line(s).",
    )


# ======================================================================
# PRE-ORDER
# ======================================================================
@router.message(F.text == "📦 Pre-Order")
async def preorder_start(message: Message, state: FSMContext):
    await state.set_state(PreOrderStates.category)
    await message.answer("📦 <b>Pre-Order</b>\nSend the 6-digit category you want:")


@router.message(PreOrderStates.category)
async def preorder_category(message: Message, state: FSMContext):
    cat = (message.text or "").strip()
    if not (cat.isdigit() and len(cat) >= 6):
        await message.answer("❌ Send at least 6 digits.")
        return
    await state.update_data(category=cat[:6])
    await state.set_state(PreOrderStates.quantity)
    await message.answer("How many lines do you want to pre-order?")


@router.message(PreOrderStates.quantity)
async def preorder_quantity(message: Message, session: AsyncSession, user: User, state: FSMContext):
    if not (message.text or "").strip().isdigit():
        await message.answer("❌ Send a number.")
        return
    data = await state.get_data()
    await state.clear()
    from app.repositories.marketing_repo import MarketingRepository

    await MarketingRepository(session).create_preorder(
        user_id=user.id, category=data["category"], quantity=int(message.text)
    )
    await message.answer(
        f"✅ Pre-order created for category <b>{data['category']}</b>.\n"
        "You'll be notified when matching stock is uploaded."
    )


# ======================================================================
# REFUND
# ======================================================================
@router.message(F.text == "↩ Refund")
async def refund_start(message: Message, session: AsyncSession, state: FSMContext):
    await message.answer(await ss.get_page(session, ss.KEY_REFUND, ss.DEFAULT_REFUND))
    await state.set_state(RefundStates.order_id)
    await message.answer("Send the <b>Order ID</b> you want refunded:")


@router.message(RefundStates.order_id)
async def refund_order(message: Message, session: AsyncSession, user: User, state: FSMContext):
    if not (message.text or "").strip().isdigit():
        await message.answer("❌ Send a numeric order ID.")
        return
    order = await OrderRepository(session).get(int(message.text))
    if order is None or order.buyer_id != user.id:
        await message.answer("❌ Order not found.")
        await state.clear()
        return
    await state.update_data(order_id=order.id, amount=str(order.total))
    await state.set_state(RefundStates.reason)
    await message.answer("Describe the reason for the refund:")


@router.message(RefundStates.reason)
async def refund_reason(message: Message, session: AsyncSession, user: User, state: FSMContext):
    data = await state.get_data()
    await state.clear()
    await SupportFlowService(session).create_refund(
        user_id=user.id,
        order_id=data["order_id"],
        amount=Decimal(data["amount"]),
        reason=message.text or "No reason",
    )
    await message.answer("✅ Refund request submitted. The Owner will review it.")


# ======================================================================
# SUPPORT
# ======================================================================
@router.message(F.text == "🎫 Support")
async def support_start(message: Message, state: FSMContext):
    await state.set_state(SupportStates.subject)
    await message.answer("🎫 <b>Support</b>\nEnter a short subject for your ticket:")


@router.message(SupportStates.subject)
async def support_subject(message: Message, state: FSMContext):
    await state.update_data(subject=(message.text or "")[:200])
    await state.set_state(SupportStates.message)
    await message.answer("Now describe your issue:")


@router.message(SupportStates.message)
async def support_message(message: Message, session: AsyncSession, user: User, state: FSMContext):
    data = await state.get_data()
    await state.clear()
    ticket = await SupportFlowService(session).open_ticket(
        user.id, data.get("subject", "Support"), message.text or ""
    )
    await message.answer(
        f"✅ Ticket <b>#{ticket.id}</b> created. The Owner will reply soon."
    )
