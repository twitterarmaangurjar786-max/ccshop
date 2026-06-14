"""Seller handlers: upload, inventory, stats, earnings, withdraw, sales."""
from __future__ import annotations

import io
from decimal import Decimal, InvalidOperation

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app import keyboards as kb
from app.config import settings
from app.constants import Role
from app.models import User
from app.repositories.finance_repo import FinanceRepository
from app.repositories.inventory_repo import InventoryRepository
from app.repositories.order_repo import OrderRepository
from app.repositories.seller_repo import SellerRepository
from app.services.exceptions import ServiceError
from app.services.upload_service import UploadService
from app.services.withdrawal_service import WithdrawalService
from app.states import EditPriceStates, UploadStates, WithdrawStates

router = Router(name="seller")
CUR = settings.currency_symbol
MAX_FILE_MB = 25


async def _require_seller(event, session: AsyncSession, user: User, role: Role):
    if role != Role.SELLER:
        msg = event.message if isinstance(event, CallbackQuery) else event
        await msg.answer("⛔ Seller access only. The Owner creates sellers.")
        if isinstance(event, CallbackQuery):
            await event.answer()
        return None
    return await SellerRepository(session).get_by_user_id(user.id)


# ======================================================================
# PANEL
# ======================================================================
@router.callback_query(F.data == "seller:panel")
async def cb_panel(call: CallbackQuery, session: AsyncSession, user: User, role: Role):
    seller = await _require_seller(call, session, user, role)
    if not seller:
        return
    await call.message.answer(
        f"🏪 <b>{seller.seller_name}</b> — Seller Panel", reply_markup=kb.seller_panel()
    )
    await call.answer()


# ======================================================================
# UPLOAD
# ======================================================================
@router.message(F.text == "📤 Upload Stock")
@router.callback_query(F.data == "seller:upload")
async def upload_start(event, session: AsyncSession, user: User, role: Role, state: FSMContext):
    seller = await _require_seller(event, session, user, role)
    if not seller:
        return
    message = event.message if isinstance(event, CallbackQuery) else event
    await state.set_state(UploadStates.waiting_file)
    await message.answer(
        "📤 <b>Upload Stock</b>\n"
        "Send a <b>.txt</b> or <b>.csv</b> file.\n\n"
        "Each line format:\n<code>12345678902772|298/3883|abc</code>\n"
        "The first 6 digits auto-generate the category."
    )
    if isinstance(event, CallbackQuery):
        await event.answer()


@router.message(UploadStates.waiting_file, F.document)
async def upload_file(message: Message, session: AsyncSession, user: User, role: Role, state: FSMContext, bot: Bot):
    seller = await SellerRepository(session).get_by_user_id(user.id)
    if seller is None:
        await state.clear()
        await message.answer("⛔ Seller access only.")
        return
    doc = message.document
    if not (doc.file_name or "").lower().endswith((".txt", ".csv")):
        await message.answer("❌ Only .txt or .csv files are supported.")
        return
    if doc.file_size and doc.file_size > MAX_FILE_MB * 1024 * 1024:
        await message.answer(f"❌ File too large (max {MAX_FILE_MB} MB).")
        return

    buffer = io.BytesIO()
    await bot.download(doc, destination=buffer)
    raw = buffer.getvalue().decode("utf-8", errors="ignore")

    result = await UploadService(session).prepare_upload(raw)
    if result.valid_count == 0:
        await message.answer(
            "⚠ No valid new lines found.\n"
            f"Total: {result.total_lines:,} • Duplicates: {result.duplicates:,} • "
            f"Invalid: {result.invalid_lines:,}"
        )
        await state.clear()
        return

    cats = "\n".join(
        f"   • <code>{c}</code> = {n:,}"
        for c, n in sorted(result.categories.items(), key=lambda x: -x[1])[:20]
    )
    await state.update_data(file_id=doc.file_id)
    await message.answer(
        "🔎 <b>SCAN COMPLETE</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"📥 Total Lines: {result.total_lines:,}\n"
        f"♻ Duplicates: {result.duplicates:,} "
        f"(file {result.file_duplicates:,} / db {result.db_duplicates:,})\n"
        f"🚫 Invalid: {result.invalid_lines:,}\n"
        f"✅ Valid Lines: {result.valid_count:,}\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"🗂 <b>Categories ({len(result.categories)}):</b>\n{cats}\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "💲 Enter <b>price per line</b> (e.g. <code>2.50</code>):"
    )
    await state.set_state(UploadStates.waiting_price)


@router.message(UploadStates.waiting_price)
async def upload_price(message: Message, state: FSMContext):
    try:
        price = Decimal((message.text or "").strip()).quantize(Decimal("0.01"))
        if price <= 0:
            raise InvalidOperation
    except (InvalidOperation, ValueError):
        await message.answer("❌ Invalid price. Send a positive number like <code>2.50</code>.")
        return
    await state.update_data(price=str(price))
    await state.set_state(UploadStates.confirm)
    await message.answer(
        f"💲 Price per line: <b>{CUR}{price}</b>\n\nConfirm upload?",
        reply_markup=kb.upload_confirm(),
    )


@router.callback_query(UploadStates.confirm, F.data == "seller:upload_confirm")
async def upload_confirm(call: CallbackQuery, session: AsyncSession, user: User, state: FSMContext, bot: Bot):
    data = await state.get_data()
    await state.clear()
    seller = await SellerRepository(session).get_by_user_id(user.id)
    if seller is None or not data.get("file_id"):
        await call.answer("Session expired.", show_alert=True)
        return

    buffer = io.BytesIO()
    await bot.download(data["file_id"], destination=buffer)
    raw = buffer.getvalue().decode("utf-8", errors="ignore")

    upload = UploadService(session)
    result = await upload.prepare_upload(raw)
    price = Decimal(data["price"])
    inserted = await upload.commit_upload(seller.id, result, price)
    total = sum(inserted.values())

    # Notify matching pre-orders
    notified = 0
    for category in inserted:
        preorders = await upload.pending_preorders(category)
        for po in preorders:
            try:
                target = await session.get(User, po.user_id)
                if target:
                    await bot.send_message(
                        target.telegram_id,
                        f"📦 New stock for category <b>{category}</b> is now available!",
                    )
                    notified += 1
            except Exception:
                pass

    summary = "\n".join(f"   • <code>{c}</code> = {n:,}" for c, n in inserted.items())
    await call.message.edit_text(
        "✅ <b>UPLOAD SAVED</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"📦 Lines added: {total:,}\n"
        f"💲 Price: {CUR}{price}\n"
        f"🗂 Categories:\n{summary}\n"
        f"🔔 Pre-order notifications: {notified}"
    )
    await call.answer("Uploaded!")


@router.callback_query(F.data == "seller:upload_cancel")
async def upload_cancel(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("❌ Upload cancelled.")
    await call.answer()


# ======================================================================
# INVENTORY
# ======================================================================
@router.message(F.text == "📦 Inventory")
@router.callback_query(F.data == "seller:inventory")
async def show_inventory(event, session: AsyncSession, user: User, role: Role):
    seller = await _require_seller(event, session, user, role)
    if not seller:
        return
    message = event.message if isinstance(event, CallbackQuery) else event
    offers = await InventoryRepository(session).seller_offers(seller.id)
    if not offers:
        await message.answer("📭 No inventory yet. Use 📤 Upload Stock.")
        if isinstance(event, CallbackQuery):
            await event.answer()
        return
    await message.answer("📦 <b>YOUR INVENTORY</b>")
    for o in offers:
        await message.answer(
            f"🗂 <b>Category {o.category}</b>\n"
            f"   📦 Stock: {o.total_lines:,}\n"
            f"   ✅ Remaining: {o.remaining:,}\n"
            f"   🛒 Sold: {o.sold_count:,}\n"
            f"   💲 Price: {CUR}{o.price}\n"
            f"   🔒 Price editable: {'Yes' if o.can_edit_price else 'No (sales started)'}",
            reply_markup=kb.offer_edit(o.id, o.can_edit_price),
        )
    if isinstance(event, CallbackQuery):
        await event.answer()


@router.callback_query(F.data.startswith("seller:price:"))
async def edit_price_start(call: CallbackQuery, session: AsyncSession, user: User, state: FSMContext):
    offer_id = int(call.data.split(":")[2])
    offer = await InventoryRepository(session).get_offer(offer_id)
    seller = await SellerRepository(session).get_by_user_id(user.id)
    if offer is None or seller is None or offer.seller_id != seller.id:
        await call.answer("Not allowed.", show_alert=True)
        return
    if not offer.can_edit_price:
        await call.answer("Price locked after first sale.", show_alert=True)
        return
    await state.set_state(EditPriceStates.waiting_price)
    await state.update_data(offer_id=offer_id)
    await call.message.answer(f"✏ Send new price for category {offer.category}:")
    await call.answer()


@router.message(EditPriceStates.waiting_price)
async def edit_price_apply(message: Message, session: AsyncSession, user: User, state: FSMContext):
    data = await state.get_data()
    await state.clear()
    try:
        price = Decimal((message.text or "").strip()).quantize(Decimal("0.01"))
        if price <= 0:
            raise InvalidOperation
    except (InvalidOperation, ValueError):
        await message.answer("❌ Invalid price.")
        return
    repo = InventoryRepository(session)
    offer = await repo.get_offer(data["offer_id"])
    seller = await SellerRepository(session).get_by_user_id(user.id)
    if offer is None or seller is None or offer.seller_id != seller.id or not offer.can_edit_price:
        await message.answer("⛔ Cannot edit this price.")
        return
    await repo.set_price(offer.id, price)
    await message.answer(f"✅ Price updated to {CUR}{price}.")


@router.callback_query(F.data.startswith("seller:del:"))
async def delete_offer(call: CallbackQuery, session: AsyncSession, user: User):
    offer_id = int(call.data.split(":")[2])
    repo = InventoryRepository(session)
    offer = await repo.get_offer(offer_id)
    seller = await SellerRepository(session).get_by_user_id(user.id)
    if offer is None or seller is None or offer.seller_id != seller.id:
        await call.answer("Not allowed.", show_alert=True)
        return
    if offer.sold_count > 0:
        await call.answer("Cannot delete: this category has sales.", show_alert=True)
        return
    await repo.delete_offer(offer_id)
    await call.message.edit_text(f"🗑 Deleted inventory for category {offer.category}.")
    await call.answer("Deleted.")


# ======================================================================
# STATISTICS / EARNINGS
# ======================================================================
@router.message(F.text == "📊 Statistics")
@router.callback_query(F.data == "seller:stats")
async def show_stats(event, session: AsyncSession, user: User, role: Role):
    seller = await _require_seller(event, session, user, role)
    if not seller:
        return
    message = event.message if isinstance(event, CallbackQuery) else event
    inv = InventoryRepository(session)
    offers = await inv.seller_offers(seller.id)
    stock = sum(o.remaining for o in offers)
    sold = sum(o.sold_count for o in offers)
    await message.answer(
        "📊 <b>STATISTICS</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"🏪 {seller.seller_name}\n"
        f"🗂 Categories: {len(offers)}\n"
        f"📦 Available stock: {stock:,}\n"
        f"🛒 Lines sold: {sold:,}\n"
        f"💵 Total sales: {seller.total_sales}\n"
        f"💰 Total revenue (your share): {CUR}{seller.total_revenue}\n"
        f"📅 Joined: {seller.join_date:%Y-%m-%d}"
    )
    if isinstance(event, CallbackQuery):
        await event.answer()


@router.message(F.text == "💰 Earnings")
@router.callback_query(F.data == "seller:earnings")
async def show_earnings(event, session: AsyncSession, user: User, role: Role):
    seller = await _require_seller(event, session, user, role)
    if not seller:
        return
    message = event.message if isinstance(event, CallbackQuery) else event
    from app.repositories.user_repo import UserRepository

    wallet = await UserRepository(session).get_wallet(user.id)
    pct = seller.seller_percent or settings.default_seller_percent
    await message.answer(
        "💰 <b>EARNINGS</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"💵 Available balance: {CUR}{wallet.balance}\n"
        f"📈 Total earned: {CUR}{wallet.total_earned}\n"
        f"🏦 Total withdrawn: {CUR}{wallet.total_withdrawn}\n"
        f"🤝 Commission split: you keep {pct}%\n\n"
        "Use 🏦 Withdraw to cash out."
    )
    if isinstance(event, CallbackQuery):
        await event.answer()


# ======================================================================
# WITHDRAW
# ======================================================================
@router.message(F.text == "🏦 Withdraw")
@router.callback_query(F.data == "seller:withdraw")
async def withdraw_start(event, session: AsyncSession, user: User, role: Role, state: FSMContext):
    seller = await _require_seller(event, session, user, role)
    if not seller:
        return
    message = event.message if isinstance(event, CallbackQuery) else event
    await state.set_state(WithdrawStates.amount)
    await message.answer("🏦 <b>Withdraw</b>\nEnter the amount to withdraw (USD):")
    if isinstance(event, CallbackQuery):
        await event.answer()


@router.message(WithdrawStates.amount)
async def withdraw_amount(message: Message, state: FSMContext):
    try:
        amount = Decimal((message.text or "").strip()).quantize(Decimal("0.01"))
        if amount <= 0:
            raise InvalidOperation
    except (InvalidOperation, ValueError):
        await message.answer("❌ Invalid amount.")
        return
    await state.update_data(amount=str(amount))
    await state.set_state(WithdrawStates.address)
    await message.answer("Send your <b>USDT TRC20 / TRX</b> wallet address:")


@router.message(WithdrawStates.address)
async def withdraw_address(message: Message, session: AsyncSession, user: User, state: FSMContext, bot: Bot):
    data = await state.get_data()
    await state.clear()
    address = (message.text or "").strip()
    try:
        wd = await WithdrawalService(session).request(
            user.id, Decimal(data["amount"]), address
        )
    except ServiceError as exc:
        await message.answer(f"⚠ {exc}")
        return
    await message.answer(
        "✅ <b>Withdrawal requested</b>\n"
        f"💵 Amount: {CUR}{wd.amount}\n"
        f"🏦 To: <code>{wd.wallet_address}</code>\n"
        f"🆔 Request: #{wd.id}\n"
        "⏳ Pending Owner approval."
    )
    # Notify owners
    for owner_tg in settings.owner_ids:
        try:
            await bot.send_message(
                owner_tg,
                f"🔔 New withdrawal #{wd.id}: {CUR}{wd.amount} from {user.telegram_id}",
            )
        except Exception:
            pass


# ======================================================================
# SALES HISTORY
# ======================================================================
@router.message(F.text == "📜 Sales History")
@router.callback_query(F.data == "seller:sales")
async def sales_history(event, session: AsyncSession, user: User, role: Role):
    seller = await _require_seller(event, session, user, role)
    if not seller:
        return
    message = event.message if isinstance(event, CallbackQuery) else event
    sales = await OrderRepository(session).seller_sales(seller.id, limit=20)
    if not sales:
        await message.answer("📭 No sales yet.")
        if isinstance(event, CallbackQuery):
            await event.answer()
        return
    lines = ["📜 <b>SALES HISTORY</b> (latest 20)", "━━━━━━━━━━━━━━━━━━━━"]
    for o in sales:
        lines.append(
            f"#{o.id} • 🗂{o.category} • {o.quantity}x • "
            f"{CUR}{o.total} • {o.created_at:%Y-%m-%d}"
        )
    await message.answer("\n".join(lines))
    if isinstance(event, CallbackQuery):
        await event.answer()
