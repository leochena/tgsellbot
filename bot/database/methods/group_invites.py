from __future__ import annotations

import datetime
from collections.abc import Awaitable, Callable

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from bot.database import Database
from bot.database.methods.audit import log_audit
from bot.database.methods.create import create_user
from bot.database.methods.read import invalidate_user_cache
from bot.database.models import User
from bot.database.models.main import BotSettings, GroupInviteLinks, GroupInviteRewards

GROUP_INVITE_SHARE_TEMPLATE_KEY = "group_invite_share_template"
GROUP_INVITE_REWARD_TIERS_KEY = "group_invite_reward_tiers"
DEFAULT_GROUP_INVITE_SHARE_TEMPLATE = (
    "点击加入 AI 公益分享频道：{link}\n"
    "每日签到免费领取积分，积分可抽奖、兑换商品。分享 GPT Plus、接码、邮箱等资源。"
)
DEFAULT_GROUP_INVITE_REWARD_TIERS = "1=1,10=2,30=3"


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


async def reward_group_inviter_after_checkin(
        invited_id: int,
        chat_id: int | str,
        points: int,
        reward_tiers: str | None = None,
) -> dict | None:
    """
    Award inviter points once after the invited user successfully checks in.
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
                GroupInviteRewards.rewarded_at.is_not(None),
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

        inviter.points_balance += points
        reward.rewarded_at = datetime.datetime.now(datetime.timezone.utc)
        reward.points_awarded = points
        inviter_id = int(inviter.telegram_id)
        reward_id = reward.id

    await invalidate_user_cache(inviter_id)
    await log_audit(
        "group_invite_reward",
        user_id=inviter_id,
        resource_type="GroupInviteReward",
        resource_id=str(reward_id),
        details=f"invited={invited_id}, chat_id={chat_id_str}, points={points}",
    )
    return {
        "id": reward_id,
        "inviter_id": inviter_id,
        "invited_id": invited_id,
        "chat_id": chat_id_str,
        "points_awarded": points,
        "successful_invite_count": successful_invite_count,
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
