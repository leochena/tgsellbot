from typing import Optional

from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from bot.i18n import localize
from bot.database.models import Permission
from bot.keyboards import back, close
from bot.database.methods.audit import log_audit
from bot.filters import HasPermissionFilter
from bot.handlers.other import _parse_channel_username
from bot.misc import BroadcastMessage, EnvKeys, sanitize_html
from bot.misc.services.broadcast_system import BroadcastManager
from bot.states import BroadcastFSM

router = Router()

# Global mailing list manager
broadcast_manager: Optional[BroadcastManager] = None


def _announcement_target() -> int | str | None:
    chat_id = (getattr(EnvKeys, "ANNOUNCEMENT_CHAT_ID", "") or EnvKeys.CHANNEL_ID or "").strip()
    if chat_id:
        try:
            return int(chat_id)
        except ValueError:
            return chat_id

    channel_username = _parse_channel_username()
    if channel_username:
        return f"@{channel_username}"

    return None


@router.callback_query(F.data == "send_message", HasPermissionFilter(permission=Permission.BROADCAST))
async def send_message_callback_handler(call: CallbackQuery, state: FSMContext):
    """Begin composing a group/channel announcement."""
    await call.message.edit_text(
        localize("broadcast.prompt"),
        reply_markup=back("console"),
    )
    await state.set_state(BroadcastFSM.waiting_message)


@router.message(BroadcastFSM.waiting_message, F.text)
async def broadcast_messages(message: Message, state: FSMContext):
    """Send an announcement to the configured group/channel only."""

    try:
        target = _announcement_target()
        if target is None:
            await message.answer(
                localize("broadcast.target_missing"),
                reply_markup=back("send_message"),
            )
            await state.clear()
            return

        # Validate broadcast message
        broadcast_msg = BroadcastMessage(
            text=message.text,
            parse_mode="HTML"
        )

        # Sanitize HTML if needed
        safe_text = sanitize_html(broadcast_msg.text) if broadcast_msg.parse_mode == "HTML" else broadcast_msg.text

        await message.delete()

        await message.bot.send_message(
            chat_id=target,
            text=safe_text,
            reply_markup=close(),
            parse_mode=str(broadcast_msg.parse_mode),
            disable_notification=False,
        )

        await message.answer(
            localize("broadcast.done", target=target),
            reply_markup=back("send_message")
        )

        # Logging
        user_info = await message.bot.get_chat(message.from_user.id)
        await log_audit("announcement_sent", user_id=user_info.id, details=f"admin={user_info.first_name}, target={target}")

    except (TelegramBadRequest, TelegramForbiddenError) as e:
        await message.answer(
            localize("broadcast.send_failed"),
            reply_markup=back("send_message")
        )
        await log_audit("announcement_error", level="ERROR", user_id=message.from_user.id, details=str(e))
    except Exception as e:
        await message.answer(
            localize("errors.invalid_data"),
            reply_markup=back("send_message")
        )
        await log_audit("announcement_error", level="ERROR", user_id=message.from_user.id, details=str(e))

    await state.clear()


@router.callback_query(F.data == "cancel_broadcast", HasPermissionFilter(permission=Permission.BROADCAST))
async def cancel_broadcast_handler(call: CallbackQuery):
    """Cancel current mailing"""
    global broadcast_manager

    if broadcast_manager:
        broadcast_manager.cancel()
        await call.answer(localize("broadcast.cancel"), show_alert=True)
    else:
        await call.answer(localize("broadcast.warning"), show_alert=True)
