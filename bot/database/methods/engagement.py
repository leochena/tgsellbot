from __future__ import annotations

import random
from collections import Counter
from datetime import datetime, time, timedelta, timezone

from sqlalchemy import func, select, update

from bot.database import Database
from bot.database.methods.audit import log_audit
from bot.database.methods.read import invalidate_user_cache
from bot.database.models import User
from bot.database.models.main import CheckIns, Goods, LotteryEntries, LotteryEvents, LotteryWinners


def _date_start(day=None) -> datetime:
    if day is None:
        day = datetime.now(timezone.utc).date()
    return datetime.combine(day, time.min, tzinfo=timezone.utc)


async def perform_daily_checkin(
        user_id: int,
        reward_amount,
        tickets_per_day: int,
) -> tuple[bool, str, dict]:
    """
    Record today's check-in, credit points reward, and issue lottery tickets.
    Returns (success, message, data).
    """
    today = _date_start()
    yesterday = _date_start(today.date() - timedelta(days=1))
    base_points_reward = max(int(reward_amount or 0), 0)
    tickets = max(int(tickets_per_day), 0)

    async with Database().session() as s:
        user = (await s.execute(
            select(User).where(User.telegram_id == user_id).with_for_update()
        )).scalars().one_or_none()
        if not user:
            return False, "user_not_found", {}

        existing = (await s.execute(
            select(CheckIns).where(
                CheckIns.user_id == user_id,
                CheckIns.checkin_date == today,
            )
        )).scalars().first()
        if existing:
            return False, "already_checked_in", {
                "streak": existing.streak,
                "points_awarded": existing.points_awarded,
                "reward_amount": existing.points_awarded,
                "tickets_awarded": existing.tickets_awarded,
            }

        previous = (await s.execute(
            select(CheckIns).where(
                CheckIns.user_id == user_id,
                CheckIns.checkin_date == yesterday,
            )
        )).scalars().first()
        streak = (previous.streak + 1) if previous else 1

        active_event = (await s.execute(
            select(LotteryEvents)
            .where(LotteryEvents.status == "active")
            .order_by(LotteryEvents.created_at.desc(), LotteryEvents.id.desc())
            .limit(1)
        )).scalars().first()

        points_reward = base_points_reward * streak
        if points_reward > 0:
            user.points_balance += points_reward

        tickets_awarded = 0
        if active_event and tickets > 0:
            for _ in range(tickets):
                s.add(LotteryEntries(event_id=active_event.id, user_id=user_id, source="checkin"))
            tickets_awarded = tickets

        s.add(CheckIns(
            user_id=user_id,
            checkin_date=today,
            reward_amount=0,
            points_awarded=points_reward,
            tickets_awarded=tickets_awarded,
            streak=streak,
        ))

    await invalidate_user_cache(user_id)
    await log_audit(
        "daily_checkin",
        user_id=user_id,
        resource_type="CheckIn",
        details=f"points={points_reward}, tickets={tickets_awarded}, streak={streak}",
    )
    return True, "success", {
        "streak": streak,
        "points_awarded": points_reward,
        "reward_amount": points_reward,
        "tickets_awarded": tickets_awarded,
        "event_id": active_event.id if active_event else None,
        "event_title": active_event.title if active_event else None,
    }


async def get_checkin_status(user_id: int) -> dict:
    today = _date_start()
    async with Database().session() as s:
        today_checkin = (await s.execute(
            select(CheckIns).where(CheckIns.user_id == user_id, CheckIns.checkin_date == today)
        )).scalars().first()
        latest = (await s.execute(
            select(CheckIns)
            .where(CheckIns.user_id == user_id)
            .order_by(CheckIns.checkin_date.desc())
            .limit(1)
        )).scalars().first()
        return {
            "checked_today": today_checkin is not None,
            "streak": latest.streak if latest else 0,
            "last_checkin_date": latest.checkin_date if latest else None,
        }


def _weighted_unique_winners(entries: list[int], count: int) -> list[int]:
    pool = list(entries)
    winners: list[int] = []
    for _ in range(max(count, 0)):
        if not pool:
            break
        winner = random.choice(pool)
        winners.append(winner)
        pool = [entry for entry in pool if entry != winner]
    return winners


async def create_lottery_event(
        title: str,
        prize: str,
        created_by: int,
        *,
        draw_at: datetime | None = None,
        min_entries: int = 0,
        min_users: int = 0,
        auto_draw_enabled: bool = False,
) -> int:
    now = datetime.now(timezone.utc)
    async with Database().session() as s:
        await s.execute(
            update(LotteryEvents)
            .where(LotteryEvents.status == "active")
            .values(status="closed", ended_at=now)
        )
        event = LotteryEvents(
            title=title.strip(),
            prize=prize.strip(),
            status="active",
            created_by=created_by,
            draw_at=draw_at,
            min_entries=max(int(min_entries or 0), 0),
            min_users=max(int(min_users or 0), 0),
            auto_draw_enabled=bool(auto_draw_enabled),
        )
        s.add(event)
        await s.flush()
        event_id = event.id

    await log_audit(
        "lottery_create",
        user_id=created_by,
        resource_type="Lottery",
        resource_id=str(event_id),
        details="previous_active_closed=true",
    )
    return event_id


async def get_active_lottery_event() -> dict | None:
    async with Database().session() as s:
        event = (await s.execute(
            select(LotteryEvents)
            .where(LotteryEvents.status == "active")
            .order_by(LotteryEvents.created_at.desc(), LotteryEvents.id.desc())
            .limit(1)
        )).scalars().first()
        if not event:
            return None
        total_entries = (await s.execute(
            select(func.count(LotteryEntries.id)).where(LotteryEntries.event_id == event.id)
        )).scalar() or 0
        unique_users = (await s.execute(
            select(func.count(func.distinct(LotteryEntries.user_id))).where(LotteryEntries.event_id == event.id)
        )).scalar() or 0
        return {
            "id": event.id,
            "title": event.title,
            "prize": event.prize,
            "status": event.status,
            "total_entries": total_entries,
            "unique_users": unique_users,
            "created_at": event.created_at,
            "draw_at": event.draw_at,
            "min_entries": event.min_entries,
            "min_users": event.min_users,
            "auto_draw_enabled": event.auto_draw_enabled,
        }


async def get_user_lottery_entries(user_id: int, event_id: int | None = None) -> int:
    async with Database().session() as s:
        if event_id is None:
            event = (await s.execute(
                select(LotteryEvents)
                .where(LotteryEvents.status == "active")
                .order_by(LotteryEvents.created_at.desc(), LotteryEvents.id.desc())
                .limit(1)
            )).scalars().first()
            if not event:
                return 0
            event_id = event.id
        return (await s.execute(
            select(func.count(LotteryEntries.id)).where(
                LotteryEntries.event_id == event_id,
                LotteryEntries.user_id == user_id,
            )
        )).scalar() or 0


async def draw_lottery_winner(event_id: int, admin_id: int) -> tuple[bool, str, dict]:
    async with Database().session() as s:
        event = (await s.execute(
            select(LotteryEvents).where(LotteryEvents.id == event_id).with_for_update()
        )).scalars().one_or_none()
        if not event:
            return False, "not_found", {}
        if event.status != "active":
            return False, "not_active", {}

        entries = (await s.execute(
            select(LotteryEntries.user_id).where(LotteryEntries.event_id == event_id)
        )).scalars().all()
        if not entries:
            return False, "no_entries", {"title": event.title}

        counts = Counter(entries)
        prize_rows = (await s.execute(
            select(Goods)
            .where(Goods.lottery_enabled.is_(True))
            .order_by(Goods.lottery_level.asc(), Goods.id.asc())
        )).scalars().all()
        if not prize_rows:
            return False, "no_prizes", {"title": event.title}

        winners = []
        used_users: set[int] = set()
        for goods in prize_rows:
            candidate_entries = [entry for entry in entries if entry not in used_users]
            selected_users = _weighted_unique_winners(candidate_entries, int(goods.lottery_winners_count or 1))
            for winner_id in selected_users:
                used_users.add(winner_id)
                winner = LotteryWinners(
                    event_id=event_id,
                    user_id=winner_id,
                    goods_id=goods.id,
                    goods_name=goods.name,
                    prize_level=goods.lottery_level or "奖品",
                    ticket_count=counts[winner_id],
                )
                s.add(winner)
                winners.append({
                    "user_id": winner_id,
                    "goods_id": goods.id,
                    "goods_name": goods.name,
                    "prize_level": goods.lottery_level or "奖品",
                    "ticket_count": counts[winner_id],
                })

        if not winners:
            return False, "not_enough_unique_users", {"title": event.title}

        winner_id = winners[0]["user_id"]
        event.winner_user_id = winner_id
        event.status = "drawn"
        event.ended_at = datetime.now(timezone.utc)

        winner_ticket_count = counts[winner_id]
        total_entries = len(entries)
        unique_users = len(counts)
        title = event.title
        prize = event.prize

    await log_audit(
        "lottery_draw",
        user_id=admin_id,
        resource_type="Lottery",
        resource_id=str(event_id),
        details=f"winner={winner_id}, entries={total_entries}",
    )
    return True, "success", {
        "event_id": event_id,
        "title": title,
        "prize": prize,
        "winner_user_id": winner_id,
        "winner_ticket_count": winner_ticket_count,
        "total_entries": total_entries,
        "unique_users": unique_users,
        "winners": winners,
        "winners_count": len(winners),
    }


async def check_auto_draw_lotteries(admin_id: int = 0) -> list[dict]:
    now = datetime.now(timezone.utc)
    drawn: list[dict] = []
    async with Database().session() as s:
        rows = (await s.execute(
            select(
                LotteryEvents.id,
                LotteryEvents.draw_at,
                LotteryEvents.min_entries,
                LotteryEvents.min_users,
                func.count(LotteryEntries.id).label("total_entries"),
                func.count(func.distinct(LotteryEntries.user_id)).label("unique_users"),
            )
            .outerjoin(LotteryEntries, LotteryEntries.event_id == LotteryEvents.id)
            .where(
                LotteryEvents.status == "active",
                LotteryEvents.auto_draw_enabled.is_(True),
            )
            .group_by(
                LotteryEvents.id,
                LotteryEvents.draw_at,
                LotteryEvents.min_entries,
                LotteryEvents.min_users,
            )
            .order_by(LotteryEvents.created_at.asc(), LotteryEvents.id.asc())
        )).all()

    for event in rows:
        time_ready = event.draw_at is not None and event.draw_at <= now
        entries_ready = event.min_entries > 0 and event.total_entries >= event.min_entries
        users_ready = event.min_users > 0 and event.unique_users >= event.min_users
        has_any_condition = event.draw_at is not None or event.min_entries > 0 or event.min_users > 0
        if has_any_condition and (time_ready or entries_ready or users_ready):
            success, message, data = await draw_lottery_winner(event.id, admin_id)
            drawn.append({"event_id": event.id, "success": success, "message": message, "data": data})
    return drawn


async def close_lottery_event(event_id: int, admin_id: int) -> tuple[bool, str]:
    async with Database().session() as s:
        event = (await s.execute(
            select(LotteryEvents).where(LotteryEvents.id == event_id).with_for_update()
        )).scalars().one_or_none()
        if not event:
            return False, "not_found"
        if event.status != "active":
            return False, "not_active"
        event.status = "closed"
        event.ended_at = datetime.now(timezone.utc)

    await log_audit("lottery_close", user_id=admin_id, resource_type="Lottery", resource_id=str(event_id))
    return True, "success"
