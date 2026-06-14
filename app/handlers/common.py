"""Common handlers: /start, Home, Profile, Rules, Contacts, navigation."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app import keyboards as kb
from app.constants import BannerType, Role
from app.handlers.render import render_home, render_profile
from app.models import User
from app.services import system_settings as ss

router = Router(name="common")


def menu_for(role: Role):
    if role == Role.OWNER:
        return kb.owner_menu()
    if role == Role.SELLER:
        return kb.seller_menu()
    return kb.buyer_menu()


async def _send_home(message: Message, session: AsyncSession, user: User, role: Role) -> None:
    text, banner = await render_home(session, user, role)
    nav = kb.home_nav(role == Role.OWNER, role == Role.SELLER)
    if banner and banner.file_id:
        try:
            if banner.type == BannerType.VIDEO:
                await message.answer_video(banner.file_id, caption=text, reply_markup=nav)
            elif banner.type == BannerType.GIF:
                await message.answer_animation(banner.file_id, caption=text, reply_markup=nav)
            else:
                await message.answer_photo(banner.file_id, caption=text, reply_markup=nav)
            await message.answer("Use the menu below 👇", reply_markup=menu_for(role))
            return
        except Exception:
            pass
    await message.answer(text, reply_markup=nav)
    await message.answer("Use the menu below 👇", reply_markup=menu_for(role))


@router.message(Command("start"))
async def cmd_start(message: Message, session: AsyncSession, user: User, role: Role, state: FSMContext):
    await state.clear()
    template = await ss.get_page(session, ss.KEY_WELCOME, ss.DEFAULT_WELCOME)
    title = await ss.get_page(session, ss.KEY_TITLE, ss.DEFAULT_TITLE)
    welcome = template.replace("{name}", message.from_user.full_name).replace("{title}", title)
    await message.answer(welcome)
    await _send_home(message, session, user, role)


@router.message(Command("home"))
@router.message(F.text == "🏠 Home")
async def show_home(message: Message, session: AsyncSession, user: User, role: Role, state: FSMContext):
    await state.clear()
    await _send_home(message, session, user, role)


@router.callback_query(F.data == "nav:home")
async def cb_home(call: CallbackQuery, session: AsyncSession, user: User, role: Role, state: FSMContext):
    await state.clear()
    await call.message.answer("🏠 Home")
    await _send_home(call.message, session, user, role)
    await call.answer()


@router.message(F.text == "👤 Profile")
@router.message(Command("profile"))
async def show_profile(message: Message, session: AsyncSession, user: User, role: Role):
    await message.answer(await render_profile(session, user, role))


@router.callback_query(F.data == "nav:profile")
async def cb_profile(call: CallbackQuery, session: AsyncSession, user: User, role: Role):
    await call.message.answer(await render_profile(session, user, role))
    await call.answer()


@router.message(F.text == "📜 Rules")
@router.message(Command("rules"))
async def show_rules(message: Message, session: AsyncSession):
    await message.answer(await ss.get_page(session, ss.KEY_RULES, ss.DEFAULT_RULES))


@router.message(F.text == "📞 Contacts")
@router.message(Command("contacts"))
async def show_contacts(message: Message, session: AsyncSession):
    await message.answer(await ss.get_page(session, ss.KEY_CONTACTS, ss.DEFAULT_CONTACTS))


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext, role: Role):
    await state.clear()
    await message.answer("❌ Cancelled.", reply_markup=menu_for(role))
