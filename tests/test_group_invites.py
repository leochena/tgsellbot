import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from aiogram.enums import ChatMemberStatus

from bot.database.methods import (
    get_inviter_group_invite_reward,
    get_group_invite_share_template,
    get_bot_setting,
    get_or_create_group_invite_link,
    list_inviter_group_invite_rewards,
    parse_group_invite_reward_tiers,
    perform_daily_checkin,
    record_group_invite_join,
    record_invite_retention_activity,
    review_group_invite_reward,
    reward_group_inviter_after_checkin,
    list_group_invite_rewards,
    resolve_group_invite_reward_points,
    settle_mature_group_invite_rewards,
)
from bot.database.methods.read import check_user
from bot.database.main import Database
from bot.database.models.main import FraudEvents, GroupInviteRewards, InviteRetentionSnapshots, LedgerEntries
from sqlalchemy import select


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
        async with Database().session() as s:
            reward_row = (await s.execute(select(GroupInviteRewards).where(
                GroupInviteRewards.id == recorded["id"]
            ))).scalars().one()
            assert reward_row.status == "pending"
            assert reward_row.pending_until is not None

        duplicate = await record_group_invite_join(150011, -1003919149099, "https://t.me/+join1")
        assert duplicate["already_recorded"] is True

        success, _, _ = await perform_daily_checkin(150011, reward_amount=1, tickets_per_day=0)
        assert success is True

        reward = await reward_group_inviter_after_checkin(150011, -1003919149099, points=2)
        assert reward["points_awarded"] == 2
        assert reward["inviter_id"] == 150010
        assert reward["pending_settlement"] is True

        second_reward = await reward_group_inviter_after_checkin(150011, -1003919149099, points=2)
        assert second_reward["pending_settlement"] is True

        inviter = await check_user(150010)
        invited = await check_user(150011)
        assert inviter["points_balance"] == 5
        assert invited["points_balance"] == 1
        async with Database().session() as s:
            reward_row = (await s.execute(select(GroupInviteRewards).where(
                GroupInviteRewards.id == reward["id"]
            ))).scalars().one()
            ledger = (await s.execute(select(LedgerEntries).where(
                LedgerEntries.user_id == 150010,
                LedgerEntries.entry_type == "group_invite_reward",
            ))).scalars().one_or_none()
            snapshots = (await s.execute(select(InviteRetentionSnapshots).where(
                InviteRetentionSnapshots.reward_id == reward["id"],
                InviteRetentionSnapshots.activity_type == "checkin",
            ))).scalars().all()
            assert reward_row.status == "qualified"
            assert reward_row.qualified_at is not None
            assert reward_row.rewarded_at is None
            assert ledger is None
            assert len(snapshots) == 1
            assert snapshots[0].retained_7d is False

        settlement = await settle_mature_group_invite_rewards(
            default_points=2,
            now=reward["settlement_at"],
            limit=10,
        )
        assert settlement["settled"] == 1
        inviter = await check_user(150010)
        assert inviter["points_balance"] == 7
        async with Database().session() as s:
            ledger = (await s.execute(select(LedgerEntries).where(
                LedgerEntries.user_id == 150010,
                LedgerEntries.entry_type == "group_invite_reward",
            ))).scalars().one()
            assert float(ledger.amount) == 2.0

    async def test_invite_retention_activity_is_idempotent_for_same_snapshot(self, user_factory):
        await user_factory(telegram_id=150012, points_balance=0)
        invite_link = await get_or_create_group_invite_link(
            150012,
            -1003919149099,
            AsyncMock(return_value="https://t.me/+retention"),
        )

        recorded = await record_group_invite_join(150013, -1003919149099, invite_link)
        first = await perform_daily_checkin(150013, reward_amount=1, tickets_per_day=0)
        async with Database().session() as s:
            reward = (await s.execute(
                select(GroupInviteRewards).where(GroupInviteRewards.id == recorded["id"])
            )).scalars().one()
            activity_at = reward.joined_at + datetime.timedelta(minutes=1)
        snapshots = await record_invite_retention_activity(
            150013,
            activity_at=activity_at,
            chat_id=-1003919149099,
        )
        duplicate = await record_invite_retention_activity(
            150013,
            activity_at=activity_at,
            chat_id=-1003919149099,
        )
        assert first[0] is True
        assert len(snapshots) == 1
        assert len(duplicate) == 0

        async with Database().session() as s:
            snapshots = (await s.execute(select(InviteRetentionSnapshots).where(
                InviteRetentionSnapshots.reward_id == recorded["id"],
                InviteRetentionSnapshots.activity_type == "checkin",
            ))).scalars().all()

        assert len(snapshots) == 1

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
        assert inviter["points_balance"] == 0

        settlement = await settle_mature_group_invite_rewards(
            default_points=1,
            reward_tiers="1=1,3=2,5=4",
            now=reward["settlement_at"],
            limit=10,
        )
        assert settlement["settled"] == 5
        inviter = await check_user(150030)
        assert inviter["points_balance"] == 10

    async def test_mature_invite_settlement_blocks_risky_rewards(self, user_factory):
        await user_factory(telegram_id=150040, points_balance=0)
        invite_link = await get_or_create_group_invite_link(
            150040,
            -1003919149099,
            AsyncMock(return_value="https://t.me/+risk"),
        )
        recorded = await record_group_invite_join(150041, -1003919149099, invite_link)
        await perform_daily_checkin(150041, reward_amount=1, tickets_per_day=0)
        reward = await reward_group_inviter_after_checkin(150041, -1003919149099, points=3)
        async with Database().session() as s:
            reward_row = (await s.execute(select(GroupInviteRewards).where(
                GroupInviteRewards.id == recorded["id"]
            ))).scalars().one()
            reward_row.risk_score = 10
            reward_row.risk_reason = "linked accounts"

        settlement = await settle_mature_group_invite_rewards(
            default_points=3,
            now=reward["settlement_at"],
            max_risk_score=0,
        )

        assert settlement["settled"] == 0
        assert settlement["blocked"] == 1
        inviter = await check_user(150040)
        assert inviter["points_balance"] == 0

    async def test_invite_reward_review_marks_risk_and_can_release(self, user_factory):
        await user_factory(telegram_id=150050, points_balance=0)
        invite_link = await get_or_create_group_invite_link(
            150050,
            -1003919149099,
            AsyncMock(return_value="https://t.me/+review"),
        )
        recorded = await record_group_invite_join(150051, -1003919149099, invite_link)
        await perform_daily_checkin(150051, reward_amount=1, tickets_per_day=0)
        reward = await reward_group_inviter_after_checkin(150051, -1003919149099, points=3)

        blocked = await review_group_invite_reward(
            reward["id"],
            reviewer_id=150050,
            status="risk_blocked",
            risk_score=20,
            risk_reason="duplicate device",
        )
        still_blocked = await reward_group_inviter_after_checkin(150051, -1003919149099, points=3)
        blocked_queue = await list_group_invite_rewards(status="risk_blocked")
        released = await review_group_invite_reward(
            reward["id"],
            reviewer_id=150050,
            status="qualified",
            risk_score=0,
            risk_reason="",
        )
        qualified_queue = await list_group_invite_rewards(status="qualified")

        assert recorded["id"] == reward["id"]
        assert blocked is True
        assert still_blocked["status"] == "risk_blocked"
        assert still_blocked["pending_settlement"] is False
        assert blocked_queue["rewards"][0]["risk_score"] == 20
        assert blocked_queue["rewards"][0]["risk_reason"] == "duplicate device"
        assert released is True
        assert qualified_queue["rewards"][0]["risk_score"] == 0
        settlement = await settle_mature_group_invite_rewards(
            default_points=3,
            now=reward["settlement_at"],
            max_risk_score=0,
        )
        assert settlement["settled"] == 1

    async def test_invite_reward_review_reverses_settled_reward_idempotently(self, user_factory):
        await user_factory(telegram_id=150055, points_balance=0)
        invite_link = await get_or_create_group_invite_link(
            150055,
            -1003919149099,
            AsyncMock(return_value="https://t.me/+reversal"),
        )
        recorded = await record_group_invite_join(150056, -1003919149099, invite_link)
        await perform_daily_checkin(150056, reward_amount=1, tickets_per_day=0)
        reward = await reward_group_inviter_after_checkin(150056, -1003919149099, points=3)

        settlement = await settle_mature_group_invite_rewards(
            default_points=3,
            now=reward["settlement_at"],
            limit=10,
        )
        assert settlement["settled"] == 1

        inviter = await check_user(150055)
        assert inviter["points_balance"] == reward["points_awarded"]

        blocked = await review_group_invite_reward(
            reward["id"],
            reviewer_id=150055,
            status="rejected",
            risk_score=33,
            risk_reason="fraud pattern",
        )
        inviter = await check_user(150055)
        assert inviter["points_balance"] == 0

        async with Database().session() as s:
            ledger_rows = (await s.execute(select(LedgerEntries).where(
                LedgerEntries.user_id == 150055,
                LedgerEntries.entry_type.in_(["group_invite_reward", "group_invite_reward_reversal"]),
            ).order_by(LedgerEntries.id.asc()))).scalars().all()

        assert recorded["id"] == reward["id"]
        assert blocked is True
        assert len(ledger_rows) == 2
        original, reversal = ledger_rows
        assert original.entry_type == "group_invite_reward"
        assert float(original.amount) == float(reward["points_awarded"])
        assert reversal.entry_type == "group_invite_reward_reversal"
        assert float(reversal.amount) == float(-reward["points_awarded"])
        assert reversal.reversed_id == original.id
        assert reversal.idempotency_key.endswith(":reversal")

        repeat = await review_group_invite_reward(
            reward["id"],
            reviewer_id=150055,
            status="rejected",
            risk_score=33,
            risk_reason="fraud pattern",
        )
        inviter = await check_user(150055)
        assert repeat is True
        assert inviter["points_balance"] == 0

        async with Database().session() as s:
            repeat_rows = (await s.execute(select(LedgerEntries).where(
                LedgerEntries.user_id == 150055,
                LedgerEntries.entry_type.in_(["group_invite_reward", "group_invite_reward_reversal"]),
            ))).scalars().all()

        assert len(repeat_rows) == 2

    async def test_invite_reward_review_can_restore_after_reversal(self, user_factory):
        await user_factory(telegram_id=150065, points_balance=0)
        invite_link = await get_or_create_group_invite_link(
            150065,
            -1003919149099,
            AsyncMock(return_value="https://t.me/+restore"),
        )
        await record_group_invite_join(150066, -1003919149099, invite_link)
        await perform_daily_checkin(150066, reward_amount=1, tickets_per_day=0)
        reward = await reward_group_inviter_after_checkin(150066, -1003919149099, points=2)
        await settle_mature_group_invite_rewards(
            default_points=2,
            now=reward["settlement_at"],
            limit=10,
        )

        rejected = await review_group_invite_reward(
            reward["id"],
            reviewer_id=150065,
            status="rejected",
            risk_score=40,
            risk_reason="tmp risk",
        )
        restored = await review_group_invite_reward(
            reward["id"],
            reviewer_id=150065,
            status="qualified",
            risk_score=0,
            risk_reason="",
        )

        inviter = await check_user(150065)
        async with Database().session() as s:
            ledger_rows = (await s.execute(select(LedgerEntries).where(
                LedgerEntries.user_id == 150065,
                LedgerEntries.entry_type.like("group_invite_reward%"),
            ).order_by(LedgerEntries.id.asc()))).scalars().all()

        assert rejected is True
        assert restored is True
        assert inviter["points_balance"] == reward["points_awarded"]
        assert len(ledger_rows) == 3
        assert ledger_rows[1].entry_type == "group_invite_reward_reversal"
        assert ledger_rows[2].entry_type == "group_invite_reward_reinstatement"
        assert float(ledger_rows[2].amount) == float(reward["points_awarded"])

    async def test_inviter_reward_listing_masks_invited_user_and_shows_reason(self, user_factory):
        await user_factory(telegram_id=150060, points_balance=0)
        invite_link = await get_or_create_group_invite_link(
            150060,
            -1003919149099,
            AsyncMock(return_value="https://t.me/+history"),
        )
        await record_group_invite_join(150061, -1003919149099, invite_link)
        await perform_daily_checkin(150061, reward_amount=1, tickets_per_day=0)
        reward = await reward_group_inviter_after_checkin(150061, -1003919149099, points=3)
        await review_group_invite_reward(
            reward["id"],
            reviewer_id=150060,
            status="risk_blocked",
            risk_score=20,
            risk_reason="duplicate device family with very long note",
        )

        listing = await list_inviter_group_invite_rewards(150060, chat_id=-1003919149099)

        assert listing["total"] == 1
        assert listing["status_counts"]["risk_blocked"] == 1
        row = listing["rewards"][0]
        assert row["status"] == "risk_blocked"
        assert row["invited_id_masked"] == "...0061"
        assert "invited_id" not in row
        assert row["reason"] == "duplicate device family with very long note"

    async def test_inviter_reward_detail_is_scoped_to_owner(self, user_factory):
        await user_factory(telegram_id=150070, points_balance=0)
        await user_factory(telegram_id=150071, points_balance=0)
        invite_link = await get_or_create_group_invite_link(
            150070,
            -1003919149099,
            AsyncMock(return_value="https://t.me/+detail"),
        )
        recorded = await record_group_invite_join(150072, -1003919149099, invite_link)

        own_reward = await get_inviter_group_invite_reward(
            150070,
            recorded["id"],
            chat_id=-1003919149099,
        )
        other_reward = await get_inviter_group_invite_reward(
            150071,
            recorded["id"],
            chat_id=-1003919149099,
        )

        assert own_reward["id"] == recorded["id"]
        assert own_reward["invited_id_masked"] == "...0072"
        assert "invited_id" not in own_reward
        assert other_reward is None

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

    async def test_invite_rewards_callback_shows_status_history(self, make_callback_query, fsm_context, user_factory):
        from bot.handlers.user.group_invites import group_invite_rewards_callback

        await user_factory(telegram_id=150110)
        invite_link = await get_or_create_group_invite_link(
            150110,
            -1003919149099,
            AsyncMock(return_value="https://t.me/+handler-history"),
        )
        await record_group_invite_join(150111, -1003919149099, invite_link)
        await perform_daily_checkin(150111, reward_amount=1, tickets_per_day=0)
        reward = await reward_group_inviter_after_checkin(150111, -1003919149099, points=2)
        await review_group_invite_reward(
            reward["id"],
            reviewer_id=150110,
            status="rejected",
            risk_score=10,
            risk_reason="duplicate device",
        )

        call = make_callback_query(data="group_invite_rewards", user_id=150110)
        with patch("bot.handlers.user.group_invites.EnvKeys") as env:
            env.ANNOUNCEMENT_CHAT_ID = "-1003919149099"
            env.CHANNEL_ID = ""
            await group_invite_rewards_callback(call, fsm_context)

        call.message.edit_text.assert_awaited_once()
        text = call.message.edit_text.await_args.args[0]
        assert "group_invite.rewards.title" in text
        assert "group_invite.status.rejected" in text
        assert "duplicate device" in text
        assert "150111" not in text
        assert "...0111" in text
        buttons = [
            button.callback_data
            for row in call.message.edit_text.await_args.kwargs["reply_markup"].inline_keyboard
            for button in row
        ]
        assert f"group_invite_reward_appeal:{reward['id']}" in buttons

    async def test_invite_rewards_callback_paginates_history(self, make_callback_query, fsm_context, user_factory):
        from bot.handlers.user.group_invites import group_invite_rewards_callback

        await user_factory(telegram_id=150120)
        invite_link = await get_or_create_group_invite_link(
            150120,
            -1003919149099,
            AsyncMock(return_value="https://t.me/+handler-pages"),
        )
        for invited_id in range(150121, 150127):
            await record_group_invite_join(invited_id, -1003919149099, invite_link)

        first_page = make_callback_query(data="group_invite_rewards", user_id=150120)
        second_page = make_callback_query(data="group_invite_rewards:1", user_id=150120)
        with patch("bot.handlers.user.group_invites.EnvKeys") as env:
            env.ANNOUNCEMENT_CHAT_ID = "-1003919149099"
            env.CHANNEL_ID = ""
            await group_invite_rewards_callback(first_page, fsm_context)
            await group_invite_rewards_callback(second_page, fsm_context)

        first_text = first_page.message.edit_text.await_args.args[0]
        first_buttons = [
            button.callback_data
            for row in first_page.message.edit_text.await_args.kwargs["reply_markup"].inline_keyboard
            for button in row
        ]
        second_text = second_page.message.edit_text.await_args.args[0]
        second_buttons = [
            button.callback_data
            for row in second_page.message.edit_text.await_args.kwargs["reply_markup"].inline_keyboard
            for button in row
        ]

        assert "...0126" in first_text
        assert "...0121" not in first_text
        assert "group_invite_rewards:1" in first_buttons
        assert "...0121" in second_text
        assert "group_invite_rewards:0" in second_buttons
        assert "group_invite_rewards:2" not in second_buttons

    async def test_invite_reward_appeal_callback_records_fraud_event(self, make_callback_query, user_factory):
        from bot.handlers.user.group_invites import group_invite_reward_appeal_callback

        await user_factory(telegram_id=150130, points_balance=0)
        invite_link = await get_or_create_group_invite_link(
            150130,
            -1003919149099,
            AsyncMock(return_value="https://t.me/+handler-appeal"),
        )
        await record_group_invite_join(150131, -1003919149099, invite_link)
        await perform_daily_checkin(150131, reward_amount=1, tickets_per_day=0)
        reward = await reward_group_inviter_after_checkin(150131, -1003919149099, points=2)
        await review_group_invite_reward(
            reward["id"],
            reviewer_id=150130,
            status="risk_blocked",
            risk_score=10,
            risk_reason="duplicate device",
        )

        call = make_callback_query(data=f"group_invite_reward_appeal:{reward['id']}", user_id=150130)
        with patch("bot.handlers.user.group_invites.EnvKeys") as env:
            env.ANNOUNCEMENT_CHAT_ID = "-1003919149099"
            env.CHANNEL_ID = ""
            await group_invite_reward_appeal_callback(call)

        call.answer.assert_awaited_once()
        assert call.answer.await_args.kwargs["show_alert"] is True
        assert "group_invite.rewards.appeal_created" in call.answer.await_args.args[0]
        async with Database().session() as s:
            appeal = (await s.execute(select(FraudEvents).where(
                FraudEvents.subject_id == "150130",
                FraudEvents.event_type == "appeal",
            ))).scalars().one()

        assert appeal.status == "open"
        assert appeal.evidence["source"] == "bot_invite_reward_history"
        assert appeal.evidence["evidence"]["reward_id"] == reward["id"]
        assert appeal.evidence["evidence"]["status"] == "risk_blocked"

    async def test_invite_reward_appeal_callback_reuses_open_appeal(self, make_callback_query, user_factory):
        from bot.handlers.user.group_invites import group_invite_reward_appeal_callback

        await user_factory(telegram_id=150132, points_balance=0)
        invite_link = await get_or_create_group_invite_link(
            150132,
            -1003919149099,
            AsyncMock(return_value="https://t.me/+handler-appeal-dedupe"),
        )
        await record_group_invite_join(150133, -1003919149099, invite_link)
        await perform_daily_checkin(150133, reward_amount=1, tickets_per_day=0)
        reward = await reward_group_inviter_after_checkin(150133, -1003919149099, points=2)
        await review_group_invite_reward(
            reward["id"],
            reviewer_id=150132,
            status="rejected",
            risk_score=10,
            risk_reason="duplicate device",
        )

        first_call = make_callback_query(data=f"group_invite_reward_appeal:{reward['id']}", user_id=150132)
        second_call = make_callback_query(data=f"group_invite_reward_appeal:{reward['id']}", user_id=150132)
        with patch("bot.handlers.user.group_invites.EnvKeys") as env:
            env.ANNOUNCEMENT_CHAT_ID = "-1003919149099"
            env.CHANNEL_ID = ""
            await group_invite_reward_appeal_callback(first_call)
            await group_invite_reward_appeal_callback(second_call)

        assert "group_invite.rewards.appeal_created" in first_call.answer.await_args.args[0]
        assert "group_invite.rewards.appeal_existing" in second_call.answer.await_args.args[0]
        async with Database().session() as s:
            appeals = (await s.execute(select(FraudEvents).where(
                FraudEvents.subject_id == "150132",
                FraudEvents.event_type == "appeal",
            ))).scalars().all()

        assert len(appeals) == 1
        assert appeals[0].evidence["dedupe_key"] == f"invite_reward:{reward['id']}"

    async def test_invite_reward_appeal_rejects_non_owner(self, make_callback_query, user_factory):
        from bot.handlers.user.group_invites import group_invite_reward_appeal_callback

        await user_factory(telegram_id=150140, points_balance=0)
        await user_factory(telegram_id=150142, points_balance=0)
        invite_link = await get_or_create_group_invite_link(
            150140,
            -1003919149099,
            AsyncMock(return_value="https://t.me/+handler-appeal-scope"),
        )
        await record_group_invite_join(150141, -1003919149099, invite_link)
        await perform_daily_checkin(150141, reward_amount=1, tickets_per_day=0)
        reward = await reward_group_inviter_after_checkin(150141, -1003919149099, points=2)
        await review_group_invite_reward(
            reward["id"],
            reviewer_id=150140,
            status="rejected",
            risk_score=10,
            risk_reason="duplicate device",
        )

        call = make_callback_query(data=f"group_invite_reward_appeal:{reward['id']}", user_id=150142)
        with patch("bot.handlers.user.group_invites.EnvKeys") as env:
            env.ANNOUNCEMENT_CHAT_ID = "-1003919149099"
            env.CHANNEL_ID = ""
            await group_invite_reward_appeal_callback(call)

        call.answer.assert_awaited_once()
        assert call.answer.await_args.kwargs["show_alert"] is True
        assert "group_invite.rewards.appeal_unavailable" in call.answer.await_args.args[0]
        async with Database().session() as s:
            appeals = (await s.execute(select(FraudEvents).where(
                FraudEvents.event_type == "appeal",
            ))).scalars().all()

        assert appeals == []

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
        assert inviter["points_balance"] == 0
        assert invited["points_balance"] == 1
        msg.answer.assert_awaited_once()
        answer = msg.answer.await_args.args[0]
        assert "checkin.tomorrow_points" in answer
        assert "'points': 2" in answer
        assert "group_invite.pending_settlement" in answer

    async def test_invite_reward_status_text_handles_reviewed_states(self):
        from bot.handlers.user.group_invites import _invite_reward_status_text

        assert "group_invite.pending_settlement" in _invite_reward_status_text({
            "points_awarded": 2,
            "pending_settlement": True,
            "status": "qualified",
        })
        assert "group_invite.risk_blocked" in _invite_reward_status_text({
            "points_awarded": 2,
            "pending_settlement": False,
            "status": "risk_blocked",
        })
        assert "group_invite.rejected" in _invite_reward_status_text({
            "points_awarded": 2,
            "pending_settlement": False,
            "status": "rejected",
        })

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
