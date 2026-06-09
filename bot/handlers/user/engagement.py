from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from bot.database.methods import (
    get_active_lottery_event,
    get_checkin_status,
    get_user_lottery_entries,
    perform_daily_checkin,
)
from bot.i18n import localize
from bot.keyboards.inline import back, lottery_keyboard
from bot.misc import EnvKeys

router = Router()


@router.callback_query(F.data == "checkin")
async def checkin_callback_handler(call: CallbackQuery, state: FSMContext):
    success, message, data = await perform_daily_checkin(
        user_id=call.from_user.id,
        reward_amount=EnvKeys.CHECKIN_POINTS_REWARD,
        tickets_per_day=EnvKeys.CHECKIN_TICKETS_PER_DAY,
    )

    if success:
        await call.message.edit_text(
            localize(
                "checkin.success",
                points=data["points_awarded"],
                tickets=data["tickets_awarded"],
                streak=data["streak"],
            ),
            reply_markup=back("back_to_menu"),
        )
    elif message == "already_checked_in":
        await call.message.edit_text(
            localize(
                "checkin.already",
                streak=data.get("streak", 0),
                tickets=data.get("tickets_awarded", 0),
            ),
            reply_markup=back("back_to_menu"),
        )
    else:
        await call.answer(localize("errors.something_wrong"), show_alert=True)

    await state.clear()


@router.callback_query(F.data == "lottery")
async def lottery_callback_handler(call: CallbackQuery, state: FSMContext):
    event = await get_active_lottery_event()
    checkin_status = await get_checkin_status(call.from_user.id)

    if not event:
        await call.message.edit_text(
            localize(
                "lottery.no_active",
                checked=localize("common.yes") if checkin_status["checked_today"] else localize("common.no"),
                streak=checkin_status["streak"],
            ),
            reply_markup=lottery_keyboard(False),
        )
        await state.clear()
        return

    user_entries = await get_user_lottery_entries(call.from_user.id, event["id"])
    await call.message.edit_text(
        localize(
            "lottery.active",
            title=event["title"],
            prize=event["prize"],
            entries=event["total_entries"],
            users=event["unique_users"],
            my_entries=user_entries,
            checked=localize("common.yes") if checkin_status["checked_today"] else localize("common.no"),
            streak=checkin_status["streak"],
        ),
        reply_markup=lottery_keyboard(True),
    )
    await state.clear()
