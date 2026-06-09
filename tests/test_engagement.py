from datetime import timedelta

from bot.database.main import Database
from bot.database.methods.engagement import (
    check_auto_draw_lotteries,
    create_lottery_event,
    draw_lottery_winner,
    get_active_lottery_event,
    get_user_lottery_entries,
    _date_start,
    perform_daily_checkin,
)
from bot.database.methods.read import check_user
from bot.database.models.main import CheckIns, LotteryWinners
from sqlalchemy import select


class TestCheckInLottery:

    async def test_checkin_rewards_points_without_lottery(self, user_factory):
        await user_factory(telegram_id=120001, balance=0)

        success, msg, data = await perform_daily_checkin(120001, 2, 1)

        assert success is True
        assert msg == "success"
        assert data["points_awarded"] == 2
        assert data["tickets_awarded"] == 0
        user = await check_user(120001)
        assert user["balance"] == 0
        assert user["points_balance"] == 2

    async def test_checkin_only_once_per_day(self, user_factory):
        await user_factory(telegram_id=120002)

        first = await perform_daily_checkin(120002, 1, 0)
        second = await perform_daily_checkin(120002, 1, 0)

        assert first[0] is True
        assert second[0] is False
        assert second[1] == "already_checked_in"

    async def test_checkin_streak_rewards_current_streak_points(self, user_factory):
        await user_factory(telegram_id=120006)
        yesterday = _date_start(_date_start().date() - timedelta(days=1))

        async with Database().session() as s:
            s.add(CheckIns(
                user_id=120006,
                checkin_date=yesterday,
                reward_amount=0,
                points_awarded=1,
                tickets_awarded=0,
                streak=1,
            ))

        success, msg, data = await perform_daily_checkin(120006, 1, 0)

        assert success is True
        assert msg == "success"
        assert data["streak"] == 2
        assert data["points_awarded"] == 2
        user = await check_user(120006)
        assert user["points_balance"] == 2

    async def test_checkin_awards_active_lottery_ticket(self, user_factory):
        await user_factory(telegram_id=120003)
        event_id = await create_lottery_event("June Draw", "Gift card", 120003)

        success, msg, data = await perform_daily_checkin(120003, 1, 2)

        assert success is True
        assert data["event_id"] == event_id
        assert data["tickets_awarded"] == 2
        assert await get_user_lottery_entries(120003, event_id) == 2

    async def test_draw_lottery_winner(self, user_factory, item_factory):
        await user_factory(telegram_id=120004)
        await item_factory(
            name="PrizeItem",
            lottery_enabled=True,
            lottery_level="一等奖",
            lottery_winners_count=1,
        )
        event_id = await create_lottery_event("Draw", "Prize", 120004)
        await perform_daily_checkin(120004, 0, 1)

        success, msg, data = await draw_lottery_winner(event_id, 120004)

        assert success is True
        assert msg == "success"
        assert data["winner_user_id"] == 120004
        assert data["winners_count"] == 1
        async with Database().session() as s:
            winner = (await s.execute(select(LotteryWinners).where(
                LotteryWinners.event_id == event_id
            ))).scalars().one()
            assert winner.user_id == 120004
            assert winner.goods_name == "PrizeItem"
        assert await get_active_lottery_event() is None

    async def test_lottery_prize_pool_draws_multiple_levels(self, user_factory, item_factory):
        await user_factory(telegram_id=120007)
        await user_factory(telegram_id=120008)
        await item_factory(
            name="FirstPrize",
            lottery_enabled=True,
            lottery_level="一等奖",
            lottery_winners_count=1,
        )
        await item_factory(
            name="SecondPrize",
            lottery_enabled=True,
            lottery_level="二等奖",
            lottery_winners_count=1,
        )
        event_id = await create_lottery_event("Pool", "Prize pool", 120007)
        await perform_daily_checkin(120007, 0, 1)
        await perform_daily_checkin(120008, 0, 1)

        success, msg, data = await draw_lottery_winner(event_id, 120007)

        assert success is True
        assert msg == "success"
        assert data["winners_count"] == 2
        async with Database().session() as s:
            winners = (await s.execute(select(LotteryWinners).where(
                LotteryWinners.event_id == event_id
            ))).scalars().all()
            assert len(winners) == 2
            assert {winner.goods_name for winner in winners} == {"FirstPrize", "SecondPrize"}
            assert len({winner.user_id for winner in winners}) == 2

    async def test_auto_draw_when_entry_condition_is_met(self, user_factory, item_factory):
        await user_factory(telegram_id=120009)
        await item_factory(
            name="AutoPrize",
            lottery_enabled=True,
            lottery_level="自动奖",
            lottery_winners_count=1,
        )
        event_id = await create_lottery_event(
            "Auto",
            "Prize pool",
            120009,
            auto_draw_enabled=True,
            min_entries=1,
        )
        await perform_daily_checkin(120009, 0, 1)

        results = await check_auto_draw_lotteries(admin_id=120009)

        assert results[0]["event_id"] == event_id
        assert results[0]["success"] is True
        assert await get_active_lottery_event() is None

    async def test_create_lottery_replaces_active_event(self, user_factory):
        await user_factory(telegram_id=120005)
        first_id = await create_lottery_event("First", "Old prize", 120005)
        second_id = await create_lottery_event("Second", "New prize", 120005)

        assert second_id != first_id
        active = await get_active_lottery_event()
        assert active["id"] == second_id
        assert active["title"] == "Second"
