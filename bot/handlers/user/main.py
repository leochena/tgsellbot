from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.enums.chat_type import ChatType
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

import datetime

from bot.database.methods import (
    select_max_role_id, create_user, check_role, check_user,
    select_user_operations, select_user_items, check_user_cached, set_user_locale
)
from bot.database.methods.read import get_cart_count
from bot.database.methods.group_invites import get_bot_setting
from bot.database.methods.lazy_queries import query_user_operations_history
from bot.handlers.other import check_sub_channel, _parse_channel_username
from bot.keyboards import main_menu, back, profile_keyboard, check_sub
from bot.keyboards.inline import simple_buttons, lazy_paginated_keyboard, language_keyboard
from bot.misc import EnvKeys
from bot.misc.metrics import get_metrics
from bot.i18n import get_locale, is_supported_locale, localize, set_current_locale
from bot.logger_mesh import logger

router = Router()


async def _get_custom_rules_text() -> str:
    locale = get_locale()
    custom_rules = (await get_bot_setting(f"rules_text_{locale}", "")).strip()
    if not custom_rules:
        custom_rules = (await get_bot_setting("rules_text", "")).strip()
    if not custom_rules:
        custom_rules = (EnvKeys.RULES or "").strip()
    return custom_rules


async def _build_rules_text() -> str:
    custom_rules = await _get_custom_rules_text()
    balance_currency = getattr(EnvKeys, "BALANCE_CURRENCY", EnvKeys.PAY_CURRENCY)
    stars_per_value = getattr(EnvKeys, "STARS_PER_VALUE", 0)
    stars_rate_text = localize("rules.stars_rate_unconfigured")
    try:
        stars_rate = float(stars_per_value)
        if stars_rate > 0:
            stars_rate_text = localize(
                "rules.stars_rate_configured",
                balance_currency=balance_currency,
                stars_per_value=stars_rate,
            )
    except (TypeError, ValueError):
        pass
    rules_notice = localize(
        "rules.balance_notice",
        balance_currency=balance_currency,
        pay_currency=EnvKeys.PAY_CURRENCY,
        stars_rate=stars_rate_text,
    )
    return f"{custom_rules}\n\n{rules_notice}" if custom_rules else rules_notice


def _invite_group_config() -> str:
    return EnvKeys.ANNOUNCEMENT_CHAT_ID or EnvKeys.CHANNEL_ID or EnvKeys.CHANNEL_URL


@router.message(F.text.startswith('/start'))
async def start(message: Message, state: FSMContext):
    """
    Handle /start:
    - Ensure user exists (register if new)
    - (Optional) Check channel subscription
    - Show the main menu
    """
    if message.chat.type != ChatType.PRIVATE:
        return

    user_id = message.from_user.id
    await state.clear()

    owner_max_role = await select_max_role_id()
    referral_id = message.text[7:] if message.text[7:] != str(user_id) else None
    user_role = owner_max_role if user_id == EnvKeys.OWNER_ID else 1

    is_new_user = (await check_user(user_id)) is None

    # registration_date is DateTime
    await create_user(
        telegram_id=int(user_id),
        registration_date=datetime.datetime.now(datetime.timezone.utc),
        referral_id=int(referral_id) if referral_id else None,
        role=user_role
    )

    if is_new_user:
        metrics = get_metrics()
        if metrics:
            metrics.track_event("registration", user_id)

    channel_username = _parse_channel_username()
    role_data = await check_role(user_id)

    # Optional subscription check
    try:
        if channel_username:
            chat_id = int(EnvKeys.CHANNEL_ID) if EnvKeys.CHANNEL_ID else f"@{channel_username}"
            chat_member = await message.bot.get_chat_member(chat_id=chat_id, user_id=user_id)
            if not await check_sub_channel(chat_member):
                markup = check_sub(channel_username)
                await message.answer(localize("subscribe.prompt"), reply_markup=markup)
                await message.delete()
                return
    except (TelegramBadRequest, TelegramForbiddenError) as e:
        # Ignore channel errors (private channel, wrong link, etc.)
        logger.warning(f"Channel subscription check failed for user {user_id}: {e}")

    cart_count = await get_cart_count(user_id)
    markup = main_menu(
        role=role_data,
        channel=_invite_group_config() or channel_username,
        helper=EnvKeys.HELPER_ID,
        cart_count=cart_count,
    )
    await message.answer(localize("menu.title"), reply_markup=markup)
    await message.delete()
    await state.clear()


@router.message(F.text.startswith('/chatid'))
async def chatid(message: Message):
    """Return the current Telegram chat id to the bot owner."""
    if message.from_user.id != EnvKeys.OWNER_ID:
        return

    await message.answer(
        localize(
            "chatid.response",
            chat_id=message.chat.id,
            chat_type=message.chat.type,
        )
    )


@router.callback_query(F.data == "back_to_menu")
async def back_to_menu_callback_handler(call: CallbackQuery, state: FSMContext):
    """
    Return user to the main menu.
    """
    user_id = call.from_user.id
    user = await check_user_cached(user_id)
    if not user:
        await create_user(
            telegram_id=user_id,
            registration_date=datetime.datetime.now(datetime.timezone.utc),
            referral_id=None,
            role=1
        )
        user = await check_user_cached(user_id)

    role_id = user.get('role_id')

    channel_username = _parse_channel_username()

    cart_count = await get_cart_count(user_id)
    markup = main_menu(
        role=role_id,
        channel=_invite_group_config() or channel_username,
        helper=EnvKeys.HELPER_ID,
        cart_count=cart_count,
    )
    await call.message.edit_text(localize("menu.title"), reply_markup=markup)
    await state.clear()


@router.callback_query(F.data == "rules")
async def rules_callback_handler(call: CallbackQuery, state: FSMContext):
    """
    Show rules text and the configured balance/payment notice.
    """
    await call.message.edit_text(await _build_rules_text(), reply_markup=back("back_to_menu"))
    await state.clear()


@router.callback_query(F.data == "profile")
async def profile_callback_handler(call: CallbackQuery, state: FSMContext):
    """
    Send profile info (balance, purchases count, id, etc.).
    """
    user_id = call.from_user.id
    tg_user = call.from_user
    user_info = await check_user_cached(user_id)

    balance = user_info.get('balance')
    points_balance = user_info.get('points_balance', 0)
    operations = await select_user_operations(user_id)
    overall_balance = sum(operations) if operations else 0
    items = await select_user_items(user_id)
    referral = EnvKeys.REFERRAL_PERCENT
    cart_count = await get_cart_count(user_id)

    markup = profile_keyboard(referral, items, cart_count=cart_count)
    text = (
        f"{localize('profile.caption', name=tg_user.first_name, id=user_id)}\n"
        f"{localize('profile.id', id=user_id)}\n"
        f"{localize('profile.balance', amount=balance, currency=EnvKeys.BALANCE_CURRENCY)}\n"
        f"{localize('profile.points', amount=points_balance)}\n"
        f"{localize('profile.total_topup', amount=overall_balance, currency=EnvKeys.BALANCE_CURRENCY)}\n"
        f"{localize('profile.purchased_count', count=items)}"
    )
    try:
        await call.message.edit_text(text, reply_markup=markup, parse_mode='HTML')
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            raise
    await state.clear()


@router.callback_query(F.data == "language_settings")
async def language_settings_callback_handler(call: CallbackQuery, state: FSMContext):
    """
    Show per-user language choices.
    """
    await call.message.edit_text(
        localize("language.select"),
        reply_markup=language_keyboard(get_locale(), back_cb="back_to_menu")
    )
    await state.clear()


@router.callback_query(F.data.startswith("set_locale:"))
async def set_locale_callback_handler(call: CallbackQuery, state: FSMContext):
    """
    Persist per-user language and refresh current i18n context immediately.
    """
    locale = call.data.split(":", 1)[1]
    if not is_supported_locale(locale):
        await call.answer(localize("language.unsupported"), show_alert=True)
        return

    success = await set_user_locale(call.from_user.id, locale)
    if not success:
        await call.answer(localize("errors.something_wrong"), show_alert=True)
        return

    locale_token = set_current_locale(locale)
    try:
        await call.answer(localize("language.updated"))
        await call.message.edit_text(
            localize("language.select"),
            reply_markup=language_keyboard(get_locale(), back_cb="back_to_menu")
        )
    finally:
        from bot.i18n import reset_current_locale
        reset_current_locale(locale_token)
    await state.clear()


@router.callback_query(F.data == "sub_channel_done")
async def check_sub_to_channel(call: CallbackQuery, state: FSMContext):
    """
    Re-check channel subscription after user clicks "Check".
    """
    user_id = call.from_user.id
    channel_username = _parse_channel_username()
    helper = EnvKeys.HELPER_ID

    if channel_username:
        chat_id = int(EnvKeys.CHANNEL_ID) if EnvKeys.CHANNEL_ID else f"@{channel_username}"
        chat_member = await call.bot.get_chat_member(chat_id=chat_id, user_id=user_id)
        if await check_sub_channel(chat_member):
            user = await check_user_cached(user_id)
            role_id = user.get('role_id')
            cart_count = await get_cart_count(user_id)
            markup = main_menu(role_id, _invite_group_config() or channel_username, helper, cart_count=cart_count)
            await call.message.edit_text(localize("menu.title"), reply_markup=markup)
            await state.clear()
            return

    await call.answer(localize("errors.not_subscribed"))


# --- Operation History ---

@router.callback_query(F.data == "operation_history")
async def operation_history_handler(call: CallbackQuery, state: FSMContext):
    user_id = call.from_user.id
    await _show_operations_page(call, state, user_id, 0)


@router.callback_query(F.data.startswith("ops-page_"))
async def navigate_operations(call: CallbackQuery, state: FSMContext):
    page = int(call.data.split("_")[1])
    await _show_operations_page(call, state, call.from_user.id, page)


async def _show_operations_page(call: CallbackQuery, state: FSMContext, user_id: int, page: int):
    from functools import partial
    from bot.misc import LazyPaginator

    paginator = LazyPaginator(partial(query_user_operations_history, user_id), per_page=10)
    items = await paginator.get_page(page)
    total_pages = await paginator.get_total_pages()

    if not items:
        await call.message.edit_text(
            localize("history.title") + "\n\n" + localize("history.empty"),
            reply_markup=back("profile"),
        )
        return

    lines = [localize("history.title"), ""]
    for op in items:
        op_type = op['type']
        amount = op['amount']
        date = op['date']
        date_str = str(date)[:19] if date else ""

        if op_type == 'topup':
            lines.append(localize("history.topup", amount=amount, currency=EnvKeys.BALANCE_CURRENCY))
        elif op_type == 'purchase':
            lines.append(localize("history.purchase", amount=amount, currency=EnvKeys.BALANCE_CURRENCY))
        elif op_type == 'referral':
            lines.append(localize("history.referral", amount=amount, currency=EnvKeys.BALANCE_CURRENCY))
        lines.append(localize("history.date", date=date_str))
        lines.append("")

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    kb = InlineKeyboardBuilder()
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="◀️", callback_data=f"ops-page_{page - 1}"))
    if total_pages > 1:
        nav_buttons.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton(text="▶️", callback_data=f"ops-page_{page + 1}"))
    if nav_buttons:
        kb.row(*nav_buttons)
    kb.row(InlineKeyboardButton(text=localize("btn.back"), callback_data="profile"))

    await call.message.edit_text("\n".join(lines), reply_markup=kb.as_markup())



