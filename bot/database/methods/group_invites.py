from __future__ import annotations

import datetime
from collections.abc import Awaitable, Callable
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from bot.database import Database
from bot.database.methods.audit import log_audit
from bot.database.methods.create import create_user
from bot.database.methods.read import invalidate_user_cache
from bot.database.models import User
from bot.database.models.main import (
    BotSettings,
    GroupInviteLinks,
    GroupInviteRewards,
    InviteRetentionSnapshots,
    LedgerEntries,
)

GROUP_INVITE_SHARE_TEMPLATE_KEY = "group_invite_share_template"
GROUP_INVITE_REWARD_TIERS_KEY = "group_invite_reward_tiers"
DEFAULT_GROUP_INVITE_SHARE_TEMPLATE = (
    "点击加入 AI 公益分享频道：{link}\n"
    "每日签到免费领取积分，积分可抽奖、兑换商品。分享 GPT Plus、接码、邮箱等资源。"
)
DEFAULT_GROUP_INVITE_REWARD_TIERS = "1=1,10=2,30=3"
GROUP_INVITE_FREEZE_HOURS = 72
GROUP_INVITE_SETTLEMENT_DAYS = 7
GROUP_INVITE_REWARD_STATUSES = {"pending", "qualified", "rewarded", "risk_blocked", "rejected"}


def parse_group_invite_reward_tiers(value: str | None) -> list[tuple[int, int]]:
    """
    Parse invite reward tiers.

    Format: "1=1,10=2,30=3" or "1:1; 10:2; 30:3".
    The first number is the effective invite count threshold, the second is
    points awarded for each invite at or above that threshold.
    """
    if not value:
        return []

    tiers: dict[int, int] = {}
    for raw_part in value.replace(";", ",").split(","):
        part = raw_part.strip()
        if not part:
            continue
        separator = "=" if "=" in part else ":"
        if separator not in part:
            continue
        threshold_raw, points_raw = part.split(separator, 1)
        try:
            threshold = int(threshold_raw.strip())
            points = int(points_raw.strip())
        except ValueError:
            continue
        if threshold <= 0 or points <= 0:
            continue
        tiers[threshold] = points

    return sorted(tiers.items())


def resolve_group_invite_reward_points(
        successful_invite_count: int,
        default_points: int,
        tiers_text: str | None,
) -> int:
    default_points = max(int(default_points or 0), 0)
    tiers = parse_group_invite_reward_tiers(tiers_text)
    if not tiers:
        return default_points

    points = default_points
    count = max(int(successful_invite_count or 0), 0)
    for threshold, tier_points in tiers:
        if count >= threshold:
            points = tier_points
        else:
            break
    return max(int(points or 0), 0)


async def ensure_user_exists(user_id: int) -> None:
    await create_user(
        telegram_id=int(user_id),
        registration_date=datetime.datetime.now(datetime.timezone.utc),
        referral_id=None,
        role=1,
    )


async def get_or_create_group_invite_link(
        inviter_id: int,
        chat_id: int | str,
        create_link_cb: Callable[[], Awaitable[str]],
) -> str:
    """
    Return an existing per-user group invite link, or create and persist one.
    """
    chat_id_str = str(chat_id)
    inviter_id = int(inviter_id)
    await ensure_user_exists(inviter_id)

    async with Database().session() as s:
        existing = (await s.execute(
            select(GroupInviteLinks.invite_link).where(
                GroupInviteLinks.inviter_id == inviter_id,
                GroupInviteLinks.chat_id == chat_id_str,
            )
        )).scalar_one_or_none()
        if existing:
            return existing

    invite_link = await create_link_cb()

    async with Database().session() as s:
        existing = (await s.execute(
            select(GroupInviteLinks.invite_link).where(
                GroupInviteLinks.inviter_id == inviter_id,
                GroupInviteLinks.chat_id == chat_id_str,
            )
        )).scalar_one_or_none()
        if existing:
            return existing

        s.add(GroupInviteLinks(
            inviter_id=inviter_id,
            chat_id=chat_id_str,
            invite_link=invite_link,
        ))
        try:
            await s.flush()
        except IntegrityError:
            await s.rollback()
            row = (await s.execute(
                select(GroupInviteLinks.invite_link).where(
                    GroupInviteLinks.inviter_id == inviter_id,
                    GroupInviteLinks.chat_id == chat_id_str,
                )
            )).scalar_one_or_none()
            if row:
                return row
            raise

    await log_audit(
        "group_invite_link_create",
        user_id=inviter_id,
        resource_type="GroupInviteLink",
        resource_id=chat_id_str,
    )
    return invite_link


async def record_group_invite_join(
        invited_id: int,
        chat_id: int | str,
        invite_link: str | None,
) -> dict | None:
    """
    Store invite attribution when Telegram reports which invite link was used.
    Points are not awarded here; the invited user must check in first.
    """
    if not invite_link:
        return None

    invited_id = int(invited_id)
    chat_id_str = str(chat_id)

    async with Database().session() as s:
        link_row = (await s.execute(
            select(GroupInviteLinks).where(
                GroupInviteLinks.chat_id == chat_id_str,
                GroupInviteLinks.invite_link == invite_link,
            )
        )).scalars().one_or_none()
        if not link_row or int(link_row.inviter_id) == invited_id:
            return None

        existing = (await s.execute(
            select(GroupInviteRewards).where(
                GroupInviteRewards.invited_id == invited_id,
                GroupInviteRewards.chat_id == chat_id_str,
            )
        )).scalars().one_or_none()
        if existing:
            return {
                "id": existing.id,
                "inviter_id": existing.inviter_id,
                "invited_id": existing.invited_id,
                "chat_id": existing.chat_id,
                "already_recorded": True,
            }

        invited_user = (await s.execute(
            select(User.telegram_id).where(User.telegram_id == invited_id)
        )).scalar_one_or_none()
        if not invited_user:
            s.add(User(
                telegram_id=invited_id,
                registration_date=datetime.datetime.now(datetime.timezone.utc),
                role_id=1,
            ))

        reward = GroupInviteRewards(
            inviter_id=link_row.inviter_id,
            invited_id=invited_id,
            chat_id=chat_id_str,
            invite_link=invite_link,
            status="pending",
            pending_until=datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=GROUP_INVITE_FREEZE_HOURS),
        )
        s.add(reward)
        try:
            await s.flush()
        except IntegrityError:
            await s.rollback()
            return None

        reward_id = reward.id
        inviter_id = reward.inviter_id

    await log_audit(
        "group_invite_join",
        user_id=invited_id,
        resource_type="GroupInviteReward",
        resource_id=str(reward_id),
        details=f"inviter={inviter_id}, chat_id={chat_id_str}",
    )
    return {
        "id": reward_id,
        "inviter_id": inviter_id,
        "invited_id": invited_id,
        "chat_id": chat_id_str,
        "already_recorded": False,
    }


async def record_invite_retention_activity(
        invited_id: int,
        *,
        activity_at: datetime.datetime | None = None,
        activity_type: str = "checkin",
        chat_id: int | str | None = None,
) -> list[dict]:
    """
    Store invite-retention activity metadata for dashboard reporting.

    This is intentionally separate from reward settlement: it does not credit
    points and does not change invite attribution.
    """
    invited_id = int(invited_id)
    activity_at = activity_at or datetime.datetime.now(datetime.timezone.utc)
    if activity_at.tzinfo is None:
        activity_at = activity_at.replace(tzinfo=datetime.timezone.utc)
    else:
        activity_at = activity_at.astimezone(datetime.timezone.utc)
    safe_activity_type = str(activity_type or "checkin").strip().lower()[:32] or "checkin"
    chat_id_str = str(chat_id) if chat_id is not None else None
    snapshots: list[dict] = []

    async with Database().session() as s:
        stmt = select(GroupInviteRewards).where(GroupInviteRewards.invited_id == invited_id)
        if chat_id_str is not None:
            stmt = stmt.where(GroupInviteRewards.chat_id == chat_id_str)
        rewards = (await s.execute(stmt.order_by(GroupInviteRewards.joined_at.asc()))).scalars().all()

        for reward in rewards:
            joined_at = _as_utc(reward.joined_at)
            window_end = joined_at + datetime.timedelta(days=GROUP_INVITE_SETTLEMENT_DAYS)
            if activity_at < joined_at:
                continue
            existing_id = (await s.execute(
                select(InviteRetentionSnapshots.id).where(
                    InviteRetentionSnapshots.reward_id == reward.id,
                    InviteRetentionSnapshots.activity_type == safe_activity_type,
                    InviteRetentionSnapshots.activity_at == activity_at,
                )
            )).scalar_one_or_none()
            if existing_id:
                continue
            snapshot = InviteRetentionSnapshots(
                reward_id=reward.id,
                inviter_id=reward.inviter_id,
                invited_id=reward.invited_id,
                chat_id=reward.chat_id,
                window_start=joined_at,
                window_end=window_end,
                activity_at=activity_at,
                activity_type=safe_activity_type,
                retained_7d=activity_at >= window_end,
            )
            s.add(snapshot)
            await s.flush()
            snapshots.append(_invite_retention_snapshot_to_dict(snapshot))

    return snapshots


async def record_invite_retention_summary(invited_id: int, *, chat_id: int | str | None = None) -> list[dict]:
    """
    Backfill retention snapshots for a user from stored invite rewards.

    Each matched reward receives at most one summary snapshot.
    """
    invited_id = int(invited_id)
    chat_id_str = str(chat_id) if chat_id is not None else None
    now = datetime.datetime.now(datetime.timezone.utc)
    summaries: list[dict] = []

    async with Database().session() as s:
        stmt = select(GroupInviteRewards).where(
            GroupInviteRewards.invited_id == invited_id,
            GroupInviteRewards.rewarded_at.is_not(None),
        )
        if chat_id_str is not None:
            stmt = stmt.where(GroupInviteRewards.chat_id == chat_id_str)
        rewards = (await s.execute(stmt.order_by(GroupInviteRewards.joined_at.asc()))).scalars().all()
        for reward in rewards:
            existing_id = (await s.execute(
                select(InviteRetentionSnapshots.id).where(
                    InviteRetentionSnapshots.reward_id == reward.id,
                    InviteRetentionSnapshots.activity_type == "summary",
                )
            )).scalar_one_or_none()
            if existing_id:
                continue
            window_end = _reward_settlement_at(reward)
            snapshot = InviteRetentionSnapshots(
                reward_id=reward.id,
                inviter_id=reward.inviter_id,
                invited_id=reward.invited_id,
                chat_id=reward.chat_id,
                window_start=_as_utc(reward.joined_at),
                window_end=window_end,
                activity_at=now,
                activity_type="summary",
                retained_7d=bool(reward.qualified_at and reward.rewarded_at and reward.rewarded_at >= window_end),
            )
            s.add(snapshot)
            await s.flush()
            summaries.append(_invite_retention_snapshot_to_dict(snapshot))

    return summaries


async def reward_group_inviter_after_checkin(
        invited_id: int,
        chat_id: int | str,
        points: int,
        reward_tiers: str | None = None,
) -> dict | None:
    """
    Mark an invite reward as behavior-qualified after the invited user checks in.

    Actual points are credited later by settle_mature_group_invite_rewards after
    the freeze and settlement windows have both elapsed.
    """
    points = max(int(points or 0), 0)

    invited_id = int(invited_id)
    chat_id_str = str(chat_id)

    async with Database().session() as s:
        reward = (await s.execute(
            select(GroupInviteRewards)
            .where(
                GroupInviteRewards.invited_id == invited_id,
                GroupInviteRewards.chat_id == chat_id_str,
                GroupInviteRewards.rewarded_at.is_(None),
            )
            .order_by(GroupInviteRewards.joined_at.asc(), GroupInviteRewards.id.asc())
            .limit(1)
            .with_for_update()
        )).scalars().one_or_none()
        if not reward:
            return None

        if reward.status in {"risk_blocked", "rejected"}:
            return _invite_reward_to_dict(reward, pending_settlement=False)

        if reward.qualified_at is not None:
            return _invite_reward_to_dict(
                reward,
                pending_settlement=reward.status == "qualified" and reward.rewarded_at is None,
            )

        inviter = (await s.execute(
            select(User).where(User.telegram_id == reward.inviter_id).with_for_update()
        )).scalars().one_or_none()
        if not inviter:
            return None

        if reward_tiers is None:
            reward_tiers = (await s.execute(
                select(BotSettings.value).where(BotSettings.key == GROUP_INVITE_REWARD_TIERS_KEY)
            )).scalar_one_or_none()

        previous_successful_invites = (await s.execute(
            select(func.count(GroupInviteRewards.id)).where(
                GroupInviteRewards.inviter_id == reward.inviter_id,
                GroupInviteRewards.chat_id == chat_id_str,
                GroupInviteRewards.qualified_at.is_not(None),
            )
        )).scalar_one()
        successful_invite_count = int(previous_successful_invites or 0) + 1
        points = resolve_group_invite_reward_points(
            successful_invite_count=successful_invite_count,
            default_points=points,
            tiers_text=reward_tiers,
        )
        if points <= 0:
            return None

        now = datetime.datetime.now(datetime.timezone.utc)
        reward.status = "qualified"
        reward.qualified_at = now
        reward.points_awarded = points
        inviter_id = int(inviter.telegram_id)
        reward_id = reward.id
        settlement_at = _reward_settlement_at(reward)

    await log_audit(
        "group_invite_qualified",
        user_id=inviter_id,
        resource_type="GroupInviteReward",
        resource_id=str(reward_id),
        details=f"invited={invited_id}, chat_id={chat_id_str}, points={points}, settlement_at={settlement_at}",
    )
    await record_invite_retention_activity(
        invited_id,
        chat_id=chat_id_str,
        activity_type="checkin",
    )
    return {
        "id": reward_id,
        "inviter_id": inviter_id,
        "invited_id": invited_id,
        "chat_id": chat_id_str,
        "points_awarded": points,
        "successful_invite_count": successful_invite_count,
        "pending_settlement": True,
        "settlement_at": settlement_at,
        "status": "qualified",
    }


async def settle_mature_group_invite_rewards(
        *,
        default_points: int,
        reward_tiers: str | None = None,
        now: datetime.datetime | None = None,
        limit: int = 100,
        max_risk_score: int = 0,
        chat_id: int | str | None = None,
) -> dict:
    """
    Credit qualified invite rewards whose freeze and 7-day settlement windows passed.
    Safe to run repeatedly; each reward has one ledger idempotency key.
    """
    now = now or datetime.datetime.now(datetime.timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=datetime.timezone.utc)
    default_points = max(int(default_points or 0), 0)
    limit = min(max(int(limit or 100), 1), 1000)
    max_risk_score = max(int(max_risk_score or 0), 0)
    chat_id_str = str(chat_id) if chat_id is not None else None

    settled: list[dict] = []
    blocked: list[dict] = []
    async with Database().session() as s:
        stmt = (
            select(GroupInviteRewards)
            .where(
                GroupInviteRewards.rewarded_at.is_(None),
                GroupInviteRewards.qualified_at.is_not(None),
                GroupInviteRewards.points_awarded > 0,
            )
            .order_by(GroupInviteRewards.joined_at.asc(), GroupInviteRewards.id.asc())
            .limit(limit)
            .with_for_update()
        )
        if chat_id_str is not None:
            stmt = stmt.where(GroupInviteRewards.chat_id == chat_id_str)
        rewards = (await s.execute(stmt)).scalars().all()

        for reward in rewards:
            settlement_at = _reward_settlement_at(reward)
            if settlement_at > now:
                continue
            if int(reward.risk_score or 0) > max_risk_score:
                reward.status = "risk_blocked"
                blocked.append(_invite_reward_to_dict(reward, pending_settlement=False))
                continue

            inviter = (await s.execute(
                select(User).where(User.telegram_id == reward.inviter_id).with_for_update()
            )).scalars().one_or_none()
            if not inviter:
                continue

            if reward_tiers is not None:
                successful_invite_count = (await s.execute(
                    select(func.count(GroupInviteRewards.id)).where(
                        GroupInviteRewards.inviter_id == reward.inviter_id,
                        GroupInviteRewards.chat_id == reward.chat_id,
                        GroupInviteRewards.qualified_at.is_not(None),
                        GroupInviteRewards.id <= reward.id,
                    )
                )).scalar_one()
                reward.points_awarded = resolve_group_invite_reward_points(
                    successful_invite_count=int(successful_invite_count or 0),
                    default_points=default_points,
                    tiers_text=reward_tiers,
                )

            inviter.points_balance += int(reward.points_awarded or 0)
            reward.status = "rewarded"
            reward.rewarded_at = now
            ledger_key = f"group-invite-reward:{reward.id}:points"
            existing_ledger = (await s.execute(
                select(LedgerEntries.id).where(LedgerEntries.idempotency_key == ledger_key)
            )).scalar_one_or_none()
            if not existing_ledger:
                s.add(LedgerEntries(
                    user_id=int(reward.inviter_id),
                    account_type="points",
                    entry_type="group_invite_reward",
                    amount=int(reward.points_awarded or 0),
                    status="available",
                    reference_type="group_invite_reward",
                    reference_id=str(reward.id),
                    idempotency_key=ledger_key,
                ))
            settled.append(_invite_reward_to_dict(reward, pending_settlement=False))

    for reward in settled:
        await invalidate_user_cache(int(reward["inviter_id"]))
        await log_audit(
            "group_invite_reward",
            user_id=int(reward["inviter_id"]),
            resource_type="GroupInviteReward",
            resource_id=str(reward["id"]),
            details=f"invited={reward['invited_id']}, chat_id={reward['chat_id']}, points={reward['points_awarded']}",
        )
    for reward in blocked:
        await log_audit(
            "group_invite_risk_blocked",
            user_id=int(reward["inviter_id"]),
            resource_type="GroupInviteReward",
            resource_id=str(reward["id"]),
            details=f"risk_score={reward['risk_score']}, reason={reward['risk_reason']}",
        )

    return {
        "settled": len(settled),
        "blocked": len(blocked),
        "rewards": settled,
        "blocked_rewards": blocked,
    }


async def list_group_invite_rewards(
        status: str = "",
        *,
        chat_id: int | str | None = None,
        limit: int = 50,
        offset: int = 0,
) -> dict:
    limit = min(max(int(limit or 50), 1), 100)
    offset = max(int(offset or 0), 0)
    status = str(status or "").strip()
    chat_id_str = str(chat_id) if chat_id not in (None, "") else None
    async with Database().session() as s:
        stmt = select(GroupInviteRewards)
        if status:
            stmt = stmt.where(GroupInviteRewards.status == status)
        if chat_id_str is not None:
            stmt = stmt.where(GroupInviteRewards.chat_id == chat_id_str)
        rows = (await s.execute(
            stmt.order_by(GroupInviteRewards.joined_at.asc(), GroupInviteRewards.id.asc())
            .offset(offset)
            .limit(limit)
        )).scalars().all()
    return {
        "rewards": [_invite_reward_admin_to_dict(row) for row in rows],
        "limit": limit,
        "offset": offset,
    }


async def list_inviter_group_invite_rewards(
        inviter_id: int,
        *,
        chat_id: int | str | None = None,
        limit: int = 10,
        offset: int = 0,
) -> dict:
    inviter_id = int(inviter_id)
    limit = min(max(int(limit or 10), 1), 20)
    offset = max(int(offset or 0), 0)
    chat_id_str = str(chat_id) if chat_id not in (None, "") else None
    filters = [GroupInviteRewards.inviter_id == inviter_id]
    if chat_id_str is not None:
        filters.append(GroupInviteRewards.chat_id == chat_id_str)

    async with Database().session() as s:
        rows = (await s.execute(
            select(GroupInviteRewards)
            .where(*filters)
            .order_by(GroupInviteRewards.joined_at.desc(), GroupInviteRewards.id.desc())
            .offset(offset)
            .limit(limit)
        )).scalars().all()
        total = int((await s.execute(
            select(func.count(GroupInviteRewards.id)).where(*filters)
        )).scalar_one() or 0)
        status_rows = (await s.execute(
            select(GroupInviteRewards.status, func.count(GroupInviteRewards.id))
            .where(*filters)
            .group_by(GroupInviteRewards.status)
        )).all()

    status_counts = {status: 0 for status in sorted(GROUP_INVITE_REWARD_STATUSES)}
    for status, count in status_rows:
        status_counts[str(status or "pending")] = int(count or 0)

    return {
        "rewards": [_invite_reward_user_to_dict(row) for row in rows],
        "total": total,
        "status_counts": status_counts,
        "limit": limit,
        "offset": offset,
        "has_more": offset + len(rows) < total,
    }


async def get_inviter_group_invite_reward(
        inviter_id: int,
        reward_id: int,
        *,
        chat_id: int | str | None = None,
) -> dict | None:
    inviter_id = int(inviter_id)
    reward_id = int(reward_id)
    chat_id_str = str(chat_id) if chat_id not in (None, "") else None
    filters = [
        GroupInviteRewards.id == reward_id,
        GroupInviteRewards.inviter_id == inviter_id,
    ]
    if chat_id_str is not None:
        filters.append(GroupInviteRewards.chat_id == chat_id_str)

    async with Database().session() as s:
        reward = (await s.execute(
            select(GroupInviteRewards).where(*filters)
        )).scalars().one_or_none()

    if not reward:
        return None
    return _invite_reward_user_to_dict(reward)


async def _group_invite_reward_credit_state(
        s,
        reward: GroupInviteRewards,
) -> tuple[Decimal, int | None, int | None]:
    rows = (await s.execute(
        select(LedgerEntries)
        .where(
            LedgerEntries.reference_type == "group_invite_reward",
            LedgerEntries.reference_id == str(reward.id),
            LedgerEntries.account_type == "points",
            LedgerEntries.status == "available",
        )
        .order_by(LedgerEntries.id.asc())
    )).scalars().all()

    credit_total = Decimal("0.00")
    settlement_ledger_id = None
    latest_ledger_id = None
    for row in rows:
        credit_total += Decimal(str(row.amount or 0))
        if settlement_ledger_id is None and row.entry_type == "group_invite_reward":
            settlement_ledger_id = int(row.id)
        latest_ledger_id = int(row.id)

    return credit_total.quantize(Decimal("0.01")), settlement_ledger_id, latest_ledger_id


async def _sync_group_invite_reward_credit(
        s,
        reward: GroupInviteRewards,
        *,
        target_credit: Decimal,
        current_credit: Decimal | None = None,
        settlement_ledger_id: int | None = None,
        latest_ledger_id: int | None = None,
) -> tuple[int, int | None]:
    if current_credit is None or settlement_ledger_id is None or latest_ledger_id is None:
        current_credit, settlement_ledger_id, latest_ledger_id = await _group_invite_reward_credit_state(s, reward)

    target_credit = Decimal(str(target_credit or 0)).quantize(Decimal("0.01"))
    current_credit = Decimal(str(current_credit or 0)).quantize(Decimal("0.01"))
    delta = (target_credit - current_credit).quantize(Decimal("0.01"))
    if delta == Decimal("0.00"):
        return 0, settlement_ledger_id

    inviter = (await s.execute(
        select(User).where(User.telegram_id == reward.inviter_id).with_for_update()
    )).scalars().one_or_none()
    if not inviter:
        return 0, settlement_ledger_id

    delta_points = int(delta)
    inviter.points_balance += delta_points
    entry_type = "group_invite_reward_reinstatement" if delta_points > 0 else "group_invite_reward_reversal"
    key_suffix = "reinstatement" if delta_points > 0 else "reversal"
    idempotency_key = (
        f"group-invite-reward:{reward.id}:sync:{current_credit}->{target_credit}:{latest_ledger_id}:{key_suffix}"
    )
    ledger = LedgerEntries(
        user_id=int(reward.inviter_id),
        account_type="points",
        entry_type=entry_type,
        amount=delta,
        status="available",
        reference_type="group_invite_reward",
        reference_id=str(reward.id),
        idempotency_key=idempotency_key,
        reversed_id=latest_ledger_id,
    )
    s.add(ledger)
    return delta_points, settlement_ledger_id


async def review_group_invite_reward(
        reward_id: int,
        reviewer_id: int,
        *,
        status: str,
        risk_score: int | None = None,
        risk_reason: str = "",
        notes: str = "",
) -> bool:
    status = str(status or "").strip()
    if status not in GROUP_INVITE_REWARD_STATUSES:
        raise ValueError("invalid invite reward status")
    async with Database().session() as s:
        reward = (await s.execute(
            select(GroupInviteRewards).where(GroupInviteRewards.id == int(reward_id)).with_for_update()
        )).scalars().one_or_none()
        if not reward:
            return False
        current_credit, settlement_ledger_id, latest_ledger_id = await _group_invite_reward_credit_state(s, reward)
        target_credit = current_credit
        if status in {"risk_blocked", "rejected"}:
            target_credit = Decimal("0.00")
            if risk_score is None:
                reward.risk_score = max(int(reward.risk_score or 0), 1)
            else:
                reward.risk_score = max(int(risk_score or 0), 0)
            if risk_reason or notes:
                reward.risk_reason = str(risk_reason or notes)[:1000]
        elif status in {"qualified", "rewarded"} and settlement_ledger_id is not None:
            target_credit = Decimal(str(max(int(reward.points_awarded or 0), 0))).quantize(Decimal("0.01"))
            if risk_score is None and not risk_reason and not notes:
                reward.risk_score = 0
                reward.risk_reason = ""
            else:
                reward.risk_score = max(int(risk_score or 0), 0)
                reward.risk_reason = str(risk_reason or notes)[:1000]
        elif status in {"qualified", "rewarded"}:
            reward.risk_score = 0 if risk_score is None else max(int(risk_score or 0), 0)
            reward.risk_reason = "" if not (risk_reason or notes) else str(risk_reason or notes)[:1000]
        elif risk_score is not None or risk_reason:
            reward.risk_score = max(int(risk_score or 0), 0)
            reward.risk_reason = str(risk_reason or "")[:1000]
        points_changed, _ = await _sync_group_invite_reward_credit(
            s,
            reward,
            target_credit=target_credit,
            current_credit=current_credit,
            settlement_ledger_id=settlement_ledger_id,
            latest_ledger_id=latest_ledger_id,
        )
        if target_credit > 0 and settlement_ledger_id is not None:
            reward.status = "rewarded"
            if points_changed != 0 or reward.rewarded_at is None:
                reward.rewarded_at = datetime.datetime.now(datetime.timezone.utc)
        else:
            reward.status = status
        reviewed = _invite_reward_admin_to_dict(reward)

    await log_audit(
        "group_invite_review",
        user_id=int(reviewer_id),
        resource_type="GroupInviteReward",
        resource_id=str(reward_id),
        details=(
            f"status={status}, inviter={reviewed['inviter_id']}, invited={reviewed['invited_id']}, "
            f"risk_score={reviewed['risk_score']}, notes={str(notes or '')[:200]}"
            + (f", points_changed={points_changed}" if points_changed else "")
        ),
    )
    if points_changed:
        await invalidate_user_cache(int(reviewed["inviter_id"]))
    return True


def _reward_settlement_at(reward: GroupInviteRewards) -> datetime.datetime:
    joined_at = _as_utc(reward.joined_at)
    pending_until = _as_utc(reward.pending_until) if reward.pending_until else joined_at + datetime.timedelta(hours=GROUP_INVITE_FREEZE_HOURS)
    seven_day_settlement = joined_at + datetime.timedelta(days=GROUP_INVITE_SETTLEMENT_DAYS)
    return max(pending_until, seven_day_settlement)


def _as_utc(value: datetime.datetime) -> datetime.datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=datetime.timezone.utc)
    return value.astimezone(datetime.timezone.utc)


def _iso_datetime(value: datetime.datetime | None) -> str:
    if value is None:
        return ""
    return _as_utc(value).isoformat()


def _invite_reward_to_dict(reward: GroupInviteRewards, *, pending_settlement: bool) -> dict:
    return {
        "id": reward.id,
        "inviter_id": reward.inviter_id,
        "invited_id": reward.invited_id,
        "chat_id": reward.chat_id,
        "points_awarded": int(reward.points_awarded or 0),
        "status": reward.status,
        "pending_settlement": pending_settlement,
        "settlement_at": _reward_settlement_at(reward),
        "risk_score": int(reward.risk_score or 0),
        "risk_reason": reward.risk_reason or "",
    }


def _invite_reward_admin_to_dict(reward: GroupInviteRewards) -> dict:
    data = _invite_reward_to_dict(
        reward,
        pending_settlement=reward.status in {"pending", "qualified"} and reward.rewarded_at is None,
    )
    data.update({
        "invite_link": reward.invite_link or "",
        "settlement_at": _iso_datetime(data.get("settlement_at")),
        "joined_at": _iso_datetime(reward.joined_at),
        "pending_until": _iso_datetime(reward.pending_until),
        "qualified_at": _iso_datetime(reward.qualified_at),
        "rewarded_at": _iso_datetime(reward.rewarded_at),
    })
    return data


def _invite_reward_user_to_dict(reward: GroupInviteRewards) -> dict:
    data = _invite_reward_to_dict(
        reward,
        pending_settlement=reward.status in {"pending", "qualified"} and reward.rewarded_at is None,
    )
    data.update({
        "settlement_at": _iso_datetime(data.get("settlement_at")),
        "joined_at": _iso_datetime(reward.joined_at),
        "pending_until": _iso_datetime(reward.pending_until),
        "qualified_at": _iso_datetime(reward.qualified_at),
        "rewarded_at": _iso_datetime(reward.rewarded_at),
        "invited_id_masked": _mask_telegram_id(reward.invited_id),
        "reason": _public_invite_reward_reason(reward),
    })
    data.pop("invited_id", None)
    return data


def _mask_telegram_id(value: int | str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return f"...{text[-4:]}"


def _public_invite_reward_reason(reward: GroupInviteRewards) -> str:
    if reward.status not in {"risk_blocked", "rejected"}:
        return ""
    reason = str(reward.risk_reason or "").replace("\r", " ").replace("\n", " ").strip()
    return reason[:120]


def _invite_retention_snapshot_to_dict(snapshot: InviteRetentionSnapshots) -> dict:
    return {
        "id": snapshot.id,
        "reward_id": snapshot.reward_id,
        "inviter_id": snapshot.inviter_id,
        "invited_id": snapshot.invited_id,
        "chat_id": snapshot.chat_id,
        "activity_type": snapshot.activity_type,
        "activity_at": snapshot.activity_at,
        "window_start": snapshot.window_start,
        "window_end": snapshot.window_end,
        "retained_7d": bool(snapshot.retained_7d),
    }


async def get_bot_setting(key: str, default: str = "") -> str:
    async with Database().session() as s:
        value = (await s.execute(
            select(BotSettings.value).where(BotSettings.key == key)
        )).scalar_one_or_none()
        return value if value is not None else default


async def get_group_invite_reward_tiers_text(default: str = "") -> str:
    return await get_bot_setting(GROUP_INVITE_REWARD_TIERS_KEY, default)


async def get_group_invite_share_template(locale: str | None = None) -> str:
    template = ""
    normalized_locale = (locale or "").strip().lower()
    if normalized_locale:
        template = await get_bot_setting(f"{GROUP_INVITE_SHARE_TEMPLATE_KEY}_{normalized_locale}", "")
    if not template:
        template = await get_bot_setting(
            GROUP_INVITE_SHARE_TEMPLATE_KEY,
            DEFAULT_GROUP_INVITE_SHARE_TEMPLATE,
        )
    return template or DEFAULT_GROUP_INVITE_SHARE_TEMPLATE
