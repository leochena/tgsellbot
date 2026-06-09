from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from datetime import datetime, timezone

from bot.database.methods import (
    close_lottery_event,
    create_lottery_event,
    draw_lottery_winner,
    get_active_lottery_event,
)
from bot.database.models import Permission
from bot.filters import HasPermissionFilter
from bot.i18n import localize
from bot.keyboards import back
from bot.keyboards.inline import lottery_admin_keyboard
from bot.states import LotteryAdminStates

router = Router()


@router.callback_query(F.data == "lottery_admin", HasPermissionFilter(Permission.PROMO_MANAGE))
async def lottery_admin_handler(call: CallbackQuery, state: FSMContext):
    event = await get_active_lottery_event()
    if event:
        text = localize(
            "admin.lottery.active",
            id=event["id"],
            title=event["title"],
            prize=event["prize"],
            entries=event["total_entries"],
            users=event["unique_users"],
        )
        markup = lottery_admin_keyboard(event["id"])
    else:
        text = localize("admin.lottery.no_active")
        markup = lottery_admin_keyboard(None)

    await call.message.edit_text(text, reply_markup=markup)
    await state.clear()


@router.callback_query(F.data == "lottery_admin_create", HasPermissionFilter(Permission.PROMO_MANAGE))
async def lottery_create_start(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text(localize("admin.lottery.prompt_title"), reply_markup=back("lottery_admin"))
    await state.set_state(LotteryAdminStates.waiting_title)


@router.message(LotteryAdminStates.waiting_title, F.text, HasPermissionFilter(Permission.PROMO_MANAGE))
async def lottery_create_title(message: Message, state: FSMContext):
    title = message.text.strip()
    if not title:
        await message.answer(localize("admin.lottery.title_invalid"), reply_markup=back("lottery_admin"))
        return
    await state.update_data(title=title)
    await message.answer(localize("admin.lottery.prompt_auto_draw"), reply_markup=back("lottery_admin"))
    await state.set_state(LotteryAdminStates.waiting_auto_draw)


def _parse_auto_draw_config(text: str):
    config = {
        "auto_draw_enabled": False,
        "draw_at": None,
        "min_entries": 0,
        "min_users": 0,
    }
    text = (text or "").strip()
    if not text or text in {"0", "否", "none", "no"}:
        return config
    config["auto_draw_enabled"] = True
    for part in text.replace("；", ";").replace("，", ";").split(";"):
        if "=" not in part:
            continue
        key, value = [item.strip() for item in part.split("=", 1)]
        if key in {"time", "draw_at", "时间"} and value:
            config["draw_at"] = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if config["draw_at"].tzinfo is None:
                config["draw_at"] = config["draw_at"].replace(tzinfo=timezone.utc)
        elif key in {"entries", "min_entries", "票数"}:
            config["min_entries"] = max(int(value), 0)
        elif key in {"users", "min_users", "人数"}:
            config["min_users"] = max(int(value), 0)
    return config


@router.message(LotteryAdminStates.waiting_auto_draw, F.text, HasPermissionFilter(Permission.PROMO_MANAGE))
async def lottery_create_auto_draw(message: Message, state: FSMContext):
    try:
        auto_config = _parse_auto_draw_config(message.text)
    except Exception:
        await message.answer(localize("admin.lottery.auto_draw_invalid"), reply_markup=back("lottery_admin"))
        return

    data = await state.get_data()
    event_id = await create_lottery_event(
        data["title"],
        localize("admin.lottery.prize_pool"),
        message.from_user.id,
        **auto_config,
    )
    await message.answer(localize("admin.lottery.created", id=event_id, title=data["title"]), reply_markup=back("lottery_admin"))
    await state.clear()


@router.callback_query(F.data.startswith("lottery_admin_draw:"), HasPermissionFilter(Permission.PROMO_MANAGE))
async def lottery_draw_handler(call: CallbackQuery):
    event_id = int(call.data.split(":", 1)[1])
    success, message, data = await draw_lottery_winner(event_id, call.from_user.id)
    if success:
        await call.message.edit_text(
            localize(
                "admin.lottery.drawn",
                title=data["title"],
                prize=data["prize"],
                winner=data["winner_user_id"],
                winners_count=data.get("winners_count", 1),
                winner_tickets=data["winner_ticket_count"],
                entries=data["total_entries"],
                users=data["unique_users"],
            ),
            reply_markup=back("lottery_admin"),
        )
        return

    await call.answer(localize(f"admin.lottery.error.{message}"), show_alert=True)


@router.callback_query(F.data.startswith("lottery_admin_close:"), HasPermissionFilter(Permission.PROMO_MANAGE))
async def lottery_close_handler(call: CallbackQuery):
    event_id = int(call.data.split(":", 1)[1])
    success, message = await close_lottery_event(event_id, call.from_user.id)
    if success:
        await call.message.edit_text(localize("admin.lottery.closed"), reply_markup=back("lottery_admin"))
        return
    await call.answer(localize(f"admin.lottery.error.{message}"), show_alert=True)
