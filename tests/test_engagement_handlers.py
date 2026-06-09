from unittest.mock import patch

from bot.database.methods.engagement import create_lottery_event, perform_daily_checkin
from bot.database.methods.read import check_user


class TestUserEngagementHandlers:

    async def test_checkin_handler_rewards_user(self, make_callback_query, fsm_context, user_factory):
        from bot.handlers.user.engagement import checkin_callback_handler

        await user_factory(telegram_id=130001, balance=0)
        call = make_callback_query(data="checkin", user_id=130001)

        with patch("bot.handlers.user.engagement.EnvKeys") as env:
            env.CHECKIN_POINTS_REWARD = 3
            env.CHECKIN_TICKETS_PER_DAY = 0
            await checkin_callback_handler(call, fsm_context)

        user = await check_user(130001)
        assert user["balance"] == 0
        assert user["points_balance"] == 3
        call.message.edit_text.assert_called_once()

    async def test_lottery_handler_shows_active_event(self, make_callback_query, fsm_context, user_factory):
        from bot.handlers.user.engagement import lottery_callback_handler

        await user_factory(telegram_id=130002)
        await create_lottery_event("Event", "Prize", 130002)
        await perform_daily_checkin(130002, 0, 1)
        call = make_callback_query(data="lottery", user_id=130002)

        await lottery_callback_handler(call, fsm_context)

        call.message.edit_text.assert_called_once()


class TestAdminLotteryHandlers:

    async def test_create_lottery_flow(self, make_callback_query, make_message, fsm_context):
        from bot.database.methods.engagement import get_active_lottery_event
        from bot.handlers.admin.lottery_management import (
            lottery_create_auto_draw,
            lottery_create_start,
            lottery_create_title,
        )

        call = make_callback_query(data="lottery_admin_create", user_id=130010)
        await lottery_create_start(call, fsm_context)
        assert await fsm_context.get_state() is not None

        title_msg = make_message(text="Launch Draw", user_id=130010)
        await lottery_create_title(title_msg, fsm_context)

        auto_draw_msg = make_message(text="0", user_id=130010)
        await lottery_create_auto_draw(auto_draw_msg, fsm_context)

        event = await get_active_lottery_event()
        assert event is not None
        assert event["title"] == "Launch Draw"
        auto_draw_msg.answer.assert_called_once()

    async def test_draw_lottery_handler(self, make_callback_query, user_factory, item_factory):
        from bot.handlers.admin.lottery_management import lottery_draw_handler

        await user_factory(telegram_id=130011)
        await item_factory(
            name="HandlerPrize",
            lottery_enabled=True,
            lottery_level="一等奖",
            lottery_winners_count=1,
        )
        event_id = await create_lottery_event("Draw", "Prize", 130011)
        await perform_daily_checkin(130011, 0, 1)
        call = make_callback_query(data=f"lottery_admin_draw:{event_id}", user_id=130011)

        await lottery_draw_handler(call)

        call.message.edit_text.assert_called_once()
