from __future__ import annotations

import logging
import time
from html import escape

from aiogram import F, Router
from aiogram.enums import ChatMemberStatus
from aiogram.enums.chat_type import ChatType
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, ChatMemberUpdated, Message

from bot.database.methods import (
    ensure_user_exists,
    get_group_invite_share_template,
    get_or_create_group_invite_link,
    perform_daily_checkin,
    record_group_invite_join,
    reward_group_inviter_after_checkin,
)
from bot.i18n import get_locale, localize
from bot.keyboards.inline import back
from bot.misc import EnvKeys

router = Router()
logger = logging.getLogger(__name__)
_WELCOME_DEDUP_SECONDS = 60
_recent_welcome_keys: dict[tuple[int, int], float] = {}

JOINED_STATUSES = {
    ChatMemberStatus.MEMBER,
    ChatMemberStatus.ADMINISTRATOR,
    ChatMemberStatus.CREATOR,
    ChatMemberStatus.RESTRICTED,
}
LEFT_STATUSES = {
    ChatMemberStatus.LEFT,
    ChatMemberStatus.KICKED,
}
CHECKIN_COMMANDS = {"/签到", "/簽到", "/checkin"}
INVITE_COMMANDS = {"/邀请", "/邀請", "/invite"}
GROUP_COMMANDS = CHECKIN_COMMANDS | INVITE_COMMANDS


def _configured_group_chat_id() -> int | None:
    value = (EnvKeys.ANNOUNCEMENT_CHAT_ID or EnvKeys.CHANNEL_ID or "").strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _command_base(text: str | None) -> str:
    if not text:
        return ""
    first = text.strip().split(maxsplit=1)[0].lower()
    return first.split("@", 1)[0]


def _is_configured_group(chat_id: int | str) -> bool:
    configured = _configured_group_chat_id()
    return configured is not None and str(chat_id) == str(configured)


def _is_callback_source(source: Message | CallbackQuery) -> bool:
    return isinstance(source, CallbackQuery) or "message" in getattr(source, "__dict__", {})


def _tomorrow_checkin_points(streak: int) -> int:
    base_points = max(int(EnvKeys.CHECKIN_POINTS_REWARD or 0), 0)
    return base_points * (int(streak or 0) + 1)


def _append_tomorrow_points(text: str, streak: int) -> str:
    return f"{text}\n{localize('checkin.tomorrow_points', points=_tomorrow_checkin_points(streak))}"


def _should_send_welcome(chat_id: int, user_id: int) -> bool:
    now = time.monotonic()
    expired_before = now - _WELCOME_DEDUP_SECONDS
    for key, timestamp in list(_recent_welcome_keys.items()):
        if timestamp < expired_before:
            _recent_welcome_keys.pop(key, None)

    key = (int(chat_id), int(user_id))
    if key in _recent_welcome_keys:
        return False
    _recent_welcome_keys[key] = now
    return True


def _welcome_usage_text(user) -> str:
    name = escape(user.first_name or "用户")
    return localize("group_invite.welcome_usage", name=name)


async def _send_group_welcome(bot, chat_id: int, user) -> None:
    if not _should_send_welcome(chat_id, user.id):
        return
    try:
        await bot.send_message(chat_id=chat_id, text=_welcome_usage_text(user))
    except (TelegramBadRequest, TelegramForbiddenError) as exc:
        logger.warning("Failed to send group welcome in %s for %s: %s", chat_id, user.id, exc)


def _render_invite_share_text(template: str, link: str) -> str:
    if "{link}" not in template:
        template = f"{template.rstrip()} {{link}}"
    return template.replace("{link}", link)


async def _create_invite_link(bot, user_id: int, chat_id: int) -> str:
    invite = await bot.create_chat_invite_link(
        chat_id=chat_id,
        name=f"invite:{user_id}",
    )
    return invite.invite_link


async def _send_invite_link(message_or_call: Message | CallbackQuery, state: FSMContext | None = None) -> None:
    user_id = message_or_call.from_user.id
    chat_id = _configured_group_chat_id()
    if chat_id is None:
        text = localize("group_invite.not_configured")
        if _is_callback_source(message_or_call):
            await message_or_call.answer(text, show_alert=True)
        else:
            await message_or_call.answer(text)
        return

    bot = message_or_call.bot
    try:
        link = await get_or_create_group_invite_link(
            inviter_id=user_id,
            chat_id=chat_id,
            create_link_cb=lambda: _create_invite_link(bot, user_id, chat_id),
        )
    except (TelegramBadRequest, TelegramForbiddenError) as exc:
        logger.warning("Failed to create group invite link for %s in %s: %s", user_id, chat_id, exc)
        text = localize("group_invite.create_failed")
        if _is_callback_source(message_or_call):
            await message_or_call.answer(text, show_alert=True)
        else:
            await message_or_call.answer(text)
        return

    template = await get_group_invite_share_template(get_locale())
    share_text = _render_invite_share_text(template, link)
    text = localize(
        "group_invite.link",
        share_text=escape(share_text),
        points=EnvKeys.GROUP_INVITE_REWARD_POINTS,
    )
    if _is_callback_source(message_or_call):
        await message_or_call.message.edit_text(text, reply_markup=back("back_to_menu"))
        await message_or_call.answer()
    else:
        await message_or_call.answer(text)

    if state:
        await state.clear()


@router.callback_query(F.data == "group_invite_link")
async def group_invite_link_callback(call: CallbackQuery, state: FSMContext):
    await _send_invite_link(call, state)


@router.message(F.text.func(lambda text: _command_base(text) in GROUP_COMMANDS))
async def group_command_handler(message: Message, state: FSMContext):
    command = _command_base(message.text)
    if command not in CHECKIN_COMMANDS and command not in INVITE_COMMANDS:
        return

    if message.chat.type not in {ChatType.GROUP, ChatType.SUPERGROUP}:
        return

    if not _is_configured_group(message.chat.id):
        return

    if command in INVITE_COMMANDS:
        await _send_invite_link(message, state)
        return

    await ensure_user_exists(message.from_user.id)
    success, result, data = await perform_daily_checkin(
        user_id=message.from_user.id,
        reward_amount=EnvKeys.CHECKIN_POINTS_REWARD,
        tickets_per_day=EnvKeys.CHECKIN_TICKETS_PER_DAY,
    )

    if success:
        reward = await reward_group_inviter_after_checkin(
            invited_id=message.from_user.id,
            chat_id=message.chat.id,
            points=EnvKeys.GROUP_INVITE_REWARD_POINTS,
        )
        text = localize(
            "checkin.success",
            points=data["points_awarded"],
            tickets=data["tickets_awarded"],
            streak=data["streak"],
        )
        text = _append_tomorrow_points(text, data["streak"])
        if reward:
            text = f"{text}\n{localize('group_invite.rewarded', points=reward['points_awarded'])}"
        await message.answer(text)
    elif result == "already_checked_in":
        streak = data.get("streak", 0)
        text = localize(
            "checkin.already",
            streak=streak,
            tickets=data.get("tickets_awarded", 0),
        )
        text = _append_tomorrow_points(text, streak)
        await message.answer(
            text
        )
    else:
        await message.answer(localize("errors.something_wrong"))

    await state.clear()


@router.chat_member()
async def group_member_update_handler(event: ChatMemberUpdated):
    if not _is_configured_group(event.chat.id):
        return

    old_status = event.old_chat_member.status
    new_status = event.new_chat_member.status
    if old_status not in LEFT_STATUSES or new_status not in JOINED_STATUSES:
        return

    user = event.new_chat_member.user
    if user.is_bot:
        return

    invite_link = event.invite_link.invite_link if event.invite_link else None
    await record_group_invite_join(
        invited_id=user.id,
        chat_id=event.chat.id,
        invite_link=invite_link,
    )
    await _send_group_welcome(event.bot, event.chat.id, user)


@router.message(F.new_chat_members)
async def group_new_members_message_handler(message: Message):
    if message.chat.type not in {ChatType.GROUP, ChatType.SUPERGROUP}:
        return
    if not _is_configured_group(message.chat.id):
        return

    for user in message.new_chat_members or []:
        if user.is_bot:
            continue
        await _send_group_welcome(message.bot, message.chat.id, user)
