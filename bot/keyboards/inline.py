from typing import Callable, Iterable, Tuple
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from bot.i18n import get_supported_locales, localize
from bot.database.models import Permission
from bot.misc import LazyPaginator # noqa: F401
from bot.misc.url_safety import UnsafeURL, normalize_public_https_url


def _platform_tab_url(base_url: str | None, tab: str) -> str:
    text = (base_url or "").strip()
    if not text:
        return ""
    try:
        safe_url = normalize_public_https_url(text, allow_path=True)
    except UnsafeURL:
        return ""
    parts = urlsplit(safe_url.normalized)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["tab"] = tab
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def main_menu(
        role: int,
        channel: str | None = None,
        helper: str | None = None,
        cart_count: int = 0,
        platform_enabled: bool = False,
        platform_webapp_url: str | None = None,
) -> InlineKeyboardMarkup:
    """
    Main menu.
    """
    kb = InlineKeyboardBuilder()
    if platform_enabled:
        channel_url = _platform_tab_url(platform_webapp_url, "channels")
        model_lab_url = _platform_tab_url(platform_webapp_url, "model_lab")
        contribute_url = _platform_tab_url(platform_webapp_url, "contribute")
        if channel_url and model_lab_url and contribute_url:
            kb.button(text=localize("btn.discover_channels"), web_app=WebAppInfo(url=channel_url))
            kb.button(text=localize("btn.model_lab"), web_app=WebAppInfo(url=model_lab_url))
            kb.button(text=localize("btn.contribution_tasks"), web_app=WebAppInfo(url=contribute_url))
        else:
            kb.button(text=localize("btn.discover_channels"), callback_data="platform_channels")
            kb.button(text=localize("btn.model_lab"), callback_data="platform_model_lab")
            kb.button(text=localize("btn.contribution_tasks"), callback_data="platform_contribute")
    kb.button(text=localize("btn.shop"), callback_data="shop")
    kb.button(text=localize("btn.rules"), callback_data="rules")
    kb.button(text=localize("btn.checkin"), callback_data="checkin")
    kb.button(text=localize("btn.lottery"), callback_data="lottery")
    kb.button(text=localize("btn.profile"), callback_data="profile")
    cart_text = localize("btn.cart", count=cart_count) if cart_count > 0 else localize("btn.cart_empty")
    kb.button(text=cart_text, callback_data="cart")
    kb.button(text=localize("btn.balance_promo"), callback_data="redeem_balance_promo")
    kb.button(text=localize("btn.language"), callback_data="language_settings")
    if helper:
        kb.button(text=localize("btn.support"), url=f"tg://user?id={helper}")
    if channel:
        kb.button(text=localize("btn.invite_group"), callback_data="group_invite_link")
        kb.button(text=localize("btn.invite_rewards"), callback_data="group_invite_rewards")
    if Permission.has_any_admin_perm(role):
        kb.button(text=localize("btn.admin_menu"), callback_data="console")
    kb.adjust(2)
    return kb.as_markup()


def lottery_keyboard(has_active_event: bool = False) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if has_active_event:
        kb.button(text=localize("btn.checkin"), callback_data="checkin")
    kb.button(text=localize("btn.back"), callback_data="back_to_menu")
    kb.adjust(1)
    return kb.as_markup()


def profile_keyboard(referral_percent: int, user_items: int = 0, cart_count: int = 0) -> InlineKeyboardMarkup:
    """
    Profile keyboard with cart, history, subscriptions.
    """
    kb = InlineKeyboardBuilder()
    kb.button(text=localize("btn.replenish"), callback_data="replenish_balance")
    if referral_percent != 0:
        kb.button(text=localize("btn.referral"), callback_data="referral_system")
    if user_items != 0:
        kb.button(text=localize("btn.purchased"), callback_data="bought_items")
    cart_text = localize("btn.cart", count=cart_count) if cart_count > 0 else localize("btn.cart_empty")
    kb.button(text=cart_text, callback_data="cart")
    kb.button(text=localize("btn.operation_history"), callback_data="operation_history")
    kb.button(text=localize("btn.balance_promo"), callback_data="redeem_balance_promo")
    kb.button(text=localize("btn.language"), callback_data="language_settings")
    kb.button(text=localize("btn.back"), callback_data="back_to_menu")
    kb.adjust(1)
    return kb.as_markup()


def lottery_admin_keyboard(active_event_id: int | None = None) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=localize("admin.lottery.create"), callback_data="lottery_admin_create")
    if active_event_id is not None:
        kb.button(text=localize("admin.lottery.draw"), callback_data=f"lottery_admin_draw:{active_event_id}")
        kb.button(text=localize("admin.lottery.close"), callback_data=f"lottery_admin_close:{active_event_id}")
    kb.button(text=localize("btn.back"), callback_data="console")
    kb.adjust(1)
    return kb.as_markup()


def language_keyboard(current_locale: str, back_cb: str = "back_to_menu") -> InlineKeyboardMarkup:
    """
    User language selection.
    """
    kb = InlineKeyboardBuilder()
    for locale in get_supported_locales():
        label = localize(f"language.name.{locale}")
        prefix = "✅ " if locale == current_locale else ""
        kb.button(text=f"{prefix}{label}", callback_data=f"set_locale:{locale}")
    kb.button(text=localize("btn.back"), callback_data=back_cb)
    kb.adjust(1)
    return kb.as_markup()


def admin_console_keyboard(maintenance_mode: bool = False, role: int = 127) -> InlineKeyboardMarkup:
    """
    Admin panel — shows only buttons the user has permissions for.
    """
    kb = InlineKeyboardBuilder()
    if role & Permission.CATALOG_MANAGE:
        kb.button(text=localize("admin.menu.shop"), callback_data="shop_management")
        kb.button(text=localize("admin.menu.goods"), callback_data="goods_management")
        kb.button(text=localize("admin.menu.categories"), callback_data="categories_management")
    if role & Permission.PROMO_MANAGE:
        kb.button(text=localize("admin.menu.promo"), callback_data="promo_mgmt")
        kb.button(text=localize("admin.menu.lottery"), callback_data="lottery_admin")
    if role & Permission.USERS_MANAGE:
        kb.button(text=localize("admin.menu.users"), callback_data="user_management")
    if role & Permission.ADMINS_MANAGE:
        kb.button(text=localize("admin.menu.roles"), callback_data="role_mgmt")
    if role & Permission.BROADCAST:
        kb.button(text=localize("admin.menu.broadcast"), callback_data="send_message")
    if role & Permission.SETTINGS_MANAGE:
        maintenance_key = "admin.menu.maintenance_on" if maintenance_mode else "admin.menu.maintenance_off"
        kb.button(text=localize(maintenance_key), callback_data="toggle_maintenance")
    kb.button(text=localize("btn.back"), callback_data="back_to_menu")
    kb.adjust(1)
    return kb.as_markup()


def simple_buttons(buttons: Iterable[Tuple[str, str]], per_row: int = 1) -> InlineKeyboardMarkup:
    """
    Universal button assembly from (text, callback_data)
    """
    kb = InlineKeyboardBuilder()
    for text, cb in buttons:
        kb.button(text=text, callback_data=cb)
    kb.adjust(per_row)
    return kb.as_markup()


def back(cb: str = "menu", text: str | None = None) -> InlineKeyboardMarkup:
    """
    One 'Back' button.
    """
    return simple_buttons([(text or localize("btn.back"), cb)])


def close() -> InlineKeyboardMarkup:
    """
    One button 'Close'.
    """
    return simple_buttons([(localize("btn.close"), "close")])


async def lazy_paginated_keyboard(
        paginator: 'LazyPaginator',
        item_text: Callable[[object], str],
        item_callback: Callable[[object], str],
        page: int = 0,
        back_cb: str | None = None,
        nav_cb_prefix: str = "",
        back_text: str | None = None,
) -> InlineKeyboardMarkup:
    """
    Lazy pagination keyboard with data loading on demand
    """
    kb = InlineKeyboardBuilder()

    # Get items for current page
    items = await paginator.get_page(page)

    for item in items:
        kb.button(text=item_text(item), callback_data=item_callback(item))
    kb.adjust(1)

    # Navigation
    total_pages = await paginator.get_total_pages()
    if total_pages > 1:
        nav_buttons = []
        if page > 0:
            nav_buttons.append(InlineKeyboardButton(text="◀️", callback_data=f"{nav_cb_prefix}{page - 1}"))
        nav_buttons.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="noop"))
        if page < total_pages - 1:
            nav_buttons.append(InlineKeyboardButton(text="▶️", callback_data=f"{nav_cb_prefix}{page + 1}"))
        kb.row(*nav_buttons)

    if back_cb:
        kb.row(InlineKeyboardButton(text=back_text or localize("btn.back"), callback_data=back_cb))

    return kb.as_markup()


def item_info(
        item_name: str, back_data: str, avg_rating: float = None,
        review_count: int = 0, has_purchased: bool = False,
        applied_promo: str = None, reviews_enabled: bool = True,
        points_price: int = 0,
        points_max_per_redeem: int = 1,
        in_stock: bool = True,
        cart_count: int = 0,
) -> InlineKeyboardMarkup:
    """
    Product card with buy, cart, promo, review buttons.
    """
    kb = InlineKeyboardBuilder()
    if in_stock:
        kb.button(text=localize("btn.buy"), callback_data="buy")
        if int(points_price or 0) > 0:
            callback = "redeem_points_choose" if int(points_max_per_redeem or 1) > 1 else "redeem_points"
            kb.button(text=localize("btn.redeem_points"), callback_data=callback)
        kb.button(text=localize("btn.add_to_cart"), callback_data="add_to_cart")
        cart_text = localize("btn.cart", count=cart_count) if cart_count > 0 else localize("btn.cart_empty")
        kb.button(text=cart_text, callback_data="cart")
        if applied_promo:
            kb.button(text=localize("btn.remove_product_promo"), callback_data="remove_promo")
        else:
            kb.button(text=localize("btn.product_promo"), callback_data="apply_promo")
    else:
        kb.button(text=localize("shop.out_of_stock"), callback_data="noop")
        cart_text = localize("btn.cart", count=cart_count) if cart_count > 0 else localize("btn.cart_empty")
        kb.button(text=cart_text, callback_data="cart")
    if reviews_enabled:
        if review_count > 0:
            kb.button(text=localize("btn.view_reviews", count=review_count), callback_data=f"reviews:{item_name}:0")
        if has_purchased:
            kb.button(text=localize("btn.leave_review"), callback_data=f"review:{item_name}")
    kb.button(text=localize("btn.back"), callback_data=back_data)
    kb.adjust(2)
    return kb.as_markup()


def payment_menu(pay_url: str) -> InlineKeyboardMarkup:
    """
    Buttons under the invoice (CryptoPay, etc.).
    """
    kb = InlineKeyboardBuilder()
    kb.button(text=localize("btn.pay"), url=pay_url)
    kb.button(text=localize("btn.check_payment"), callback_data="check")
    kb.button(text=localize("btn.back"), callback_data="profile")
    kb.adjust(1)
    return kb.as_markup()


def get_payment_choice() -> InlineKeyboardMarkup:
    """
    Select a payment method.
    """
    return simple_buttons(
        [
            (localize("btn.pay.crypto"), "pay_cryptopay"),
            (localize("btn.pay.stars"), "pay_stars"),
            (localize("btn.pay.tg"), "pay_fiat"),
            (localize("btn.back"), "replenish_balance"),
        ],
        per_row=1,
    )


def question_buttons(question: str, back_data: str) -> InlineKeyboardMarkup:
    """
    Universal yes/no + Back.
    """
    kb = InlineKeyboardBuilder()
    kb.button(text=localize("btn.yes"), callback_data=f"{question}_yes")
    kb.button(text=localize("btn.no"), callback_data=f"{question}_no")
    kb.button(text=localize("btn.back"), callback_data=back_data)
    kb.adjust(2)
    return kb.as_markup()


def check_sub(channel_username: str) -> InlineKeyboardMarkup:
    """
    checks the channel subscription.
    """
    kb = InlineKeyboardBuilder()
    kb.button(text=localize("btn.channel"), url=f"https://t.me/{channel_username}")
    kb.button(text=localize("btn.check_subscription"), callback_data="sub_channel_done")
    kb.adjust(1)
    return kb.as_markup()


def rating_keyboard(item_name: str) -> InlineKeyboardMarkup:
    """Rating selection keyboard (1-5 stars)."""
    kb = InlineKeyboardBuilder()
    for i in range(1, 6):
        kb.button(text="⭐" * i, callback_data=f"rating:{i}")
    kb.button(text=localize("btn.back"), callback_data="back_to_menu")
    kb.adjust(5)
    return kb.as_markup()


def referral_system_keyboard(has_referrals: bool = False, has_earnings: bool = False) -> InlineKeyboardMarkup:
    """
    Referral system keyboard with additional buttons.
    """
    kb = InlineKeyboardBuilder()

    if has_referrals:
        kb.button(text=localize("btn.view_referrals"), callback_data="view_referrals")

    if has_earnings:
        kb.button(text=localize("btn.view_earnings"), callback_data="view_all_earnings")

    kb.button(text=localize("btn.back"), callback_data="profile")
    kb.adjust(1)
    return kb.as_markup()
