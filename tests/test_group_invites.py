from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from aiogram.enums import ChatMemberStatus

from bot.database.methods import (
    get_group_invite_share_template,
    get_bot_setting,
    get_or_create_group_invite_link,
    parse_group_invite_reward_tiers,
    perform_daily_checkin,
    record_group_invite_join,
    reward_group_inviter_after_checkin,
    resolve_group_invite_reward_points,
)
from bot.database.methods.read import check_user


class TestGroupInviteMethods:

    def test_parse_and_resolve_reward_tiers(self):
        assert parse_group_invite_reward_tiers("1=1,10=2; 30:3") == [(1, 1), (10, 2), (30, 3)]
        assert parse_group_invite_reward_tiers("bad,0=9,3=0,5=2") == [(5, 2)]
        assert resolve_group_invite_reward_points(1, 1, "1=1,3=2,5=4") == 1
        assert resolve_group_invite_reward_points(3, 1, "1=1,3=2,5=4") == 2
        assert resolve_group_invite_reward_points(5, 1, "1=1,3=2,5=4") == 4
        assert resolve_group_invite_reward_points(5, 7, "") == 7

    async def test_get_or_create_group_invite_link_reuses_existing(self, user_factory):
        await user_factory(telegram_id=150001)
        create_link = AsyncMock(return_value="https://t.me/+abc")

        first = await get_or_create_group_invite_link(150001, -1001, create_link)
        second = await get_or_create_group_invite_link(150001, -1001, create_link)

        assert first == "https://t.me/+abc"
        assert second == "https://t.me/+abc"
        create_link.assert_awaited_once()

    async def test_record_join_then_reward_after_checkin_once(self, user_factory):
        await user_factory(telegram_id=150010, points_balance=5)
        await get_or_create_group_invite_link(150010, -1003919149099, AsyncMock(return_value="https://t.me/+join1"))

        recorded = await record_group_invite_join(150011, -1003919149099, "https://t.me/+join1")
        assert recorded["inviter_id"] == 150010

        duplicate = await record_group_invite_join(150011, -1003919149099, "https://t.me/+join1")
        assert duplicate["already_recorded"] is True

        success, _, _ = await perform_daily_checkin(150011, reward_amount=1, tickets_per_day=0)
        assert success is True

        reward = await reward_group_inviter_after_checkin(150011, -1003919149099, points=2)
        assert reward["points_awarded"] == 2
        assert reward["inviter_id"] == 150010

        second_reward = await reward_group_inviter_after_checkin(150011, -1003919149099, points=2)
        assert second_reward is None

        inviter = await check_user(150010)
        invited = await check_user(150011)
        assert inviter["points_balance"] == 7
        assert invited["points_balance"] == 1

    async def test_reward_tiers_increase_points_by_successful_invite_count(self, user_factory):
        await user_factory(telegram_id=150030, points_balance=0)
        invite_link = await get_or_create_group_invite_link(
            150030,
            -1003919149099,
            AsyncMock(return_value="https://t.me/+tiers"),
        )

        awarded = []
        for offset in range(1, 6):
            invited_id = 150030 + offset
            await record_group_invite_join(invited_id, -1003919149099, invite_link)
            success, _, _ = await perform_daily_checkin(invited_id, reward_amount=1, tickets_per_day=0)
            assert success is True
            reward = await reward_group_inviter_after_checkin(
                invited_id,
                -1003919149099,
                points=1,
                reward_tiers="1=1,3=2,5=4",
            )
            awarded.append((reward["successful_invite_count"], reward["points_awarded"]))

        assert awarded == [(1, 1), (2, 1), (3, 2), (4, 2), (5, 4)]
        inviter = await check_user(150030)
        assert inviter["points_balance"] == 10

    async def test_self_invite_is_ignored(self, user_factory):
        await user_factory(telegram_id=150020)
        await get_or_create_group_invite_link(150020, -1002, AsyncMock(return_value="https://t.me/+self"))

        recorded = await record_group_invite_join(150020, -1002, "https://t.me/+self")

        assert recorded is None

    async def test_default_share_template_is_inserted(self):
        from bot.database.models.main import BotSettings

        await BotSettings.insert_defaults()

        template = await get_group_invite_share_template()
        assert "{link}" in template
        assert "AI 公益分享频道" in template

        en_template = await get_group_invite_share_template("en")
        assert "{link}" in en_template
        assert "AI public-benefit" in en_template

        reward_tiers = await get_bot_setting("group_invite_reward_tiers")
        assert reward_tiers == "1=1,10=2,30=3"


class TestGroupInviteHandlers:

    async def test_invite_callback_creates_and_shows_link(self, make_callback_query, fsm_context, user_factory):
        from bot.handlers.user.group_invites import group_invite_link_callback

        await user_factory(telegram_id=150100)
        call = make_callback_query(data="group_invite_link", user_id=150100)
        call.bot.create_chat_invite_link = AsyncMock(
            return_value=SimpleNamespace(invite_link="https://t.me/+handler")
        )

        with patch("bot.handlers.user.group_invites.EnvKeys") as env:
            env.ANNOUNCEMENT_CHAT_ID = "-1003919149099"
            env.CHANNEL_ID = ""
            env.GROUP_INVITE_REWARD_POINTS = 3
            await group_invite_link_callback(call, fsm_context)

        call.bot.create_chat_invite_link.assert_awaited_once()
        call.message.edit_text.assert_awaited_once()
        assert "https://t.me/+handler" in call.message.edit_text.await_args.args[0]
        assert "AI 公益分享频道" in call.message.edit_text.await_args.args[0]

    async def test_group_checkin_rewards_inviter(self, make_message, fsm_context, user_factory):
        from bot.handlers.user.group_invites import group_command_handler

        await user_factory(telegram_id=150200, points_balance=0)
        await get_or_create_group_invite_link(150200, -1003919149099, AsyncMock(return_value="https://t.me/+group"))
        await record_group_invite_join(150201, -1003919149099, "https://t.me/+group")

        msg = make_message(text="/签到", user_id=150201)
        msg.chat.id = -1003919149099
        msg.chat.type = "supergroup"

        with patch("bot.handlers.user.group_invites.EnvKeys") as env:
            env.ANNOUNCEMENT_CHAT_ID = "-1003919149099"
            env.CHANNEL_ID = ""
            env.CHECKIN_POINTS_REWARD = 1
            env.CHECKIN_TICKETS_PER_DAY = 0
            env.GROUP_INVITE_REWARD_POINTS = 4
            await group_command_handler(msg, fsm_context)

        inviter = await check_user(150200)
        invited = await check_user(150201)
        assert inviter["points_balance"] == 4
        assert invited["points_balance"] == 1
        msg.answer.assert_awaited_once()
        answer = msg.answer.await_args.args[0]
        assert "checkin.tomorrow_points" in answer
        assert "'points': 2" in answer
        assert "group_invite.rewarded" in answer

    async def test_group_checkin_already_checked_in_shows_tomorrow_points(self, make_message, fsm_context, user_factory):
        from bot.handlers.user.group_invites import group_command_handler

        await user_factory(telegram_id=150202)
        await perform_daily_checkin(150202, reward_amount=1, tickets_per_day=0)

        msg = make_message(text="/签到", user_id=150202)
        msg.chat.id = -1003919149099
        msg.chat.type = "supergroup"

        with patch("bot.handlers.user.group_invites.EnvKeys") as env:
            env.ANNOUNCEMENT_CHAT_ID = "-1003919149099"
            env.CHANNEL_ID = ""
            env.CHECKIN_POINTS_REWARD = 1
            env.CHECKIN_TICKETS_PER_DAY = 0
            env.GROUP_INVITE_REWARD_POINTS = 4
            await group_command_handler(msg, fsm_context)

        msg.answer.assert_awaited_once()
        answer = msg.answer.await_args.args[0]
        assert "checkin.tomorrow_points" in answer
        assert "'points': 2" in answer

    async def test_member_join_sends_group_usage_once(self):
        from bot.handlers.user import group_invites
        from bot.handlers.user.group_invites import (
            group_member_update_handler,
            group_new_members_message_handler,
        )

        group_invites._recent_welcome_keys.clear()
        bot = AsyncMock()
        user = SimpleNamespace(id=150300, first_name="新用户", is_bot=False)
        event = SimpleNamespace(
            chat=SimpleNamespace(id=-1003919149099),
            old_chat_member=SimpleNamespace(status=ChatMemberStatus.LEFT),
            new_chat_member=SimpleNamespace(status=ChatMemberStatus.MEMBER, user=user),
            invite_link=None,
            bot=bot,
        )

        with patch("bot.handlers.user.group_invites.EnvKeys") as env:
            env.ANNOUNCEMENT_CHAT_ID = "-1003919149099"
            env.CHANNEL_ID = ""
            await group_member_update_handler(event)

            message = SimpleNamespace(
                chat=SimpleNamespace(id=-1003919149099, type="supergroup"),
                new_chat_members=[user],
                bot=bot,
            )
            await group_new_members_message_handler(message)

        bot.send_message.assert_awaited_once()
        kwargs = bot.send_message.await_args.kwargs
        assert kwargs["chat_id"] == -1003919149099
        assert "group_invite.welcome_usage" in kwargs["text"]
        assert "新用户" in kwargs["text"]
