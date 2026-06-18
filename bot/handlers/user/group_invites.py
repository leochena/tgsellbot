from __future__ import annotations

import logging
import time
from html import escape

from aiogram import F, Router
from aiogram.enums import ChatMemberStatus
from aiogram.enums.chat_type import ChatType
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, ChatMemberUpdated, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.database.methods import (
    ensure_user_exists,
    get_group_invite_share_template,
    get_group_invite_reward_tiers_text,
    get_inviter_group_invite_reward,
    get_or_create_group_invite_link,
    list_inviter_group_invite_rewards,
    parse_group_invite_reward_tiers,
    perform_daily_checkin,
    record_group_invite_join,
    record_user_appeal,
    reward_group_inviter_after_checkin,
)
from bot.i18n import get_locale, localize
from bot.keyboards.inline import back
from bot.misc import EnvKeys

router = Router()
logger = logging.getLogger(__name__)
_WELCOME_DEDUP_SECONDS = 60
_REWARD_HISTORY_PAGE_SIZE = 5
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


def _invite_reward_display(default_points: int, tiers_text: str | None) -> str:
    tiers = parse_group_invite_reward_tiers(tiers_text)
    if not tiers:
        return localize("group_invite.reward.fixed", points=max(int(default_points or 0), 0))

    parts: list[str] = []
    for index, (start, points) in enumerate(tiers):
        if index + 1 < len(tiers):
            end = tiers[index + 1][0] - 1
            parts.append(localize("group_invite.reward.range", start=start, end=end, points=points))
        else:
            parts.append(localize("group_invite.reward.open", start=start, points=points))
    return "；".join(parts)


def _invite_reward_status_text(reward: dict) -> str:
    points = int(reward.get("points_awarded") or 0)
    status = str(reward.get("status") or "")
    if status == "risk_blocked":
        return localize("group_invite.risk_blocked", points=points)
    if status == "rejected":
        return localize("group_invite.rejected", points=points)
    if status == "rewarded" or not reward.get("pending_settlement"):
        return localize("group_invite.rewarded", points=points)
    return localize("group_invite.pending_settlement", points=points)


def _invite_reward_history_status_key(status: str) -> str:
    if status in {"pending", "qualified", "rewarded", "risk_blocked", "rejected"}:
        return f"group_invite.status.{status}"
    return "group_invite.status.pending"


def _render_invite_reward_history(summary: dict) -> str:
    rewards = list(summary.get("rewards") or [])
    counts = summary.get("status_counts") or {}
    lines = [
        localize("group_invite.rewards.title"),
        localize(
            "group_invite.rewards.summary",
            total=int(summary.get("total") or 0),
            pending=int(counts.get("pending") or 0),
            qualified=int(counts.get("qualified") or 0),
            rewarded=int(counts.get("rewarded") or 0),
            risk_blocked=int(counts.get("risk_blocked") or 0),
            rejected=int(counts.get("rejected") or 0),
        ),
    ]
    if not rewards:
        lines.append(localize("group_invite.rewards.empty"))
        return "\n\n".join(lines)

    lines.append("")
    for reward in rewards:
        status = str(reward.get("status") or "pending")
        parts = [
            localize(
                "group_invite.rewards.item",
                invited=reward.get("invited_id_masked") or "",
                status=localize(_invite_reward_history_status_key(status)),
                points=int(reward.get("points_awarded") or 0),
                settlement_at=_format_invite_reward_time(reward.get("settlement_at") or reward.get("pending_until") or ""),
            )
        ]
        reason = str(reward.get("reason") or "").strip()
        if reason:
            parts.append(localize("group_invite.rewards.reason", reason=reason))
        lines.append("\n".join(parts))
    if summary.get("has_more"):
        lines.append(localize("group_invite.rewards.has_more"))
    return "\n\n".join(lines)


def _invite_reward_history_page(callback_data: str | None) -> int:
    raw = str(callback_data or "")
    if ":" not in raw:
        return 0
    try:
        return max(int(raw.rsplit(":", 1)[1]), 0)
    except ValueError:
        return 0


def _invite_reward_history_keyboard(summary: dict):
    limit = max(int(summary.get("limit") or _REWARD_HISTORY_PAGE_SIZE), 1)
    offset = max(int(summary.get("offset") or 0), 0)
    page = offset // limit
    rewards = list(summary.get("rewards") or [])

    kb = InlineKeyboardBuilder()
    for reward in rewards:
        status = str(reward.get("status") or "")
        if status not in {"risk_blocked", "rejected"}:
            continue
        kb.button(
            text=localize(
                "group_invite.rewards.appeal",
                invited=reward.get("invited_id_masked") or "",
            ),
            callback_data=f"group_invite_reward_appeal:{int(reward.get('id') or 0)}",
        )
    if rewards:
        kb.adjust(1)

    nav_buttons: list[InlineKeyboardButton] = []
    if offset > 0:
        nav_buttons.append(InlineKeyboardButton(text="◀️", callback_data=f"group_invite_rewards:{page - 1}"))
    if offset > 0 or summary.get("has_more"):
        nav_buttons.append(InlineKeyboardButton(
            text=localize("group_invite.rewards.page", page=page + 1),
            callback_data="noop",
        ))
    if summary.get("has_more"):
        nav_buttons.append(InlineKeyboardButton(text="▶️", callback_data=f"group_invite_rewards:{page + 1}"))
    if nav_buttons:
        kb.row(*nav_buttons)
    kb.row(InlineKeyboardButton(text=localize("btn.back"), callback_data="back_to_menu"))
    return kb.as_markup()


def _format_invite_reward_time(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return "-"
    return text.replace("T", " ")[:16]


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
    reward_tiers = await get_group_invite_reward_tiers_text()
    share_text = _render_invite_share_text(template, link)
    text = localize(
        "group_invite.link",
        share_text=escape(share_text),
        reward=_invite_reward_display(EnvKeys.GROUP_INVITE_REWARD_POINTS, reward_tiers),
    )
    if _is_callback_source(message_or_call):
        await message_or_call.message.edit_text(text, reply_markup=back("back_to_menu"))
        await message_or_call.answer()
    else:
        await message_or_call.answer(text)

    if state:
        await state.clear()


async def _send_invite_reward_history(call: CallbackQuery, state: FSMContext) -> None:
    chat_id = _configured_group_chat_id()
    page = _invite_reward_history_page(call.data)
    summary = await list_inviter_group_invite_rewards(
        call.from_user.id,
        chat_id=chat_id,
        limit=_REWARD_HISTORY_PAGE_SIZE,
        offset=page * _REWARD_HISTORY_PAGE_SIZE,
    )
    await call.message.edit_text(
        _render_invite_reward_history(summary),
        reply_markup=_invite_reward_history_keyboard(summary),
    )
    await call.answer()
    await state.clear()


async def _submit_invite_reward_appeal(call: CallbackQuery) -> None:
    try:
        reward_id = int(str(call.data or "").rsplit(":", 1)[1])
    except (IndexError, ValueError):
        await call.answer(localize("group_invite.rewards.appeal_unavailable"), show_alert=True)
        return

    reward = await get_inviter_group_invite_reward(
        call.from_user.id,
        reward_id,
        chat_id=_configured_group_chat_id(),
    )
    if not reward or reward.get("status") not in {"risk_blocked", "rejected"}:
        await call.answer(localize("group_invite.rewards.appeal_unavailable"), show_alert=True)
        return

    try:
        appeal = await record_user_appeal(
            call.from_user.id,
            reason=(
                f"Invite reward review appeal for reward #{reward_id}; "
                f"status={reward.get('status')}; reason={reward.get('reason') or ''}"
            ),
            source="bot_invite_reward_history",
            evidence={
                "reward_id": reward_id,
                "chat_id": reward.get("chat_id"),
                "status": reward.get("status"),
                "points_awarded": reward.get("points_awarded"),
                "public_reason": reward.get("reason"),
                "invited_id_masked": reward.get("invited_id_masked"),
            },
            dedupe_key=f"invite_reward:{reward_id}",
        )
    except ValueError:
        await call.answer(localize("group_invite.rewards.appeal_unavailable"), show_alert=True)
        return

    if appeal.get("duplicate"):
        await call.answer(
            localize("group_invite.rewards.appeal_existing", appeal_id=appeal["id"]),
            show_alert=True,
        )
        return

    await call.answer(
        localize("group_invite.rewards.appeal_created", appeal_id=appeal["id"]),
        show_alert=True,
    )


@router.callback_query(F.data == "group_invite_link")
async def group_invite_link_callback(call: CallbackQuery, state: FSMContext):
    await _send_invite_link(call, state)


@router.callback_query(F.data.startswith("group_invite_rewards"))
async def group_invite_rewards_callback(call: CallbackQuery, state: FSMContext):
    await _send_invite_reward_history(call, state)


@router.callback_query(F.data.startswith("group_invite_reward_appeal:"))
async def group_invite_reward_appeal_callback(call: CallbackQuery):
    await _submit_invite_reward_appeal(call)


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
            text = f"{text}\n{_invite_reward_status_text(reward)}"
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
