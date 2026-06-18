from decimal import Decimal
from typing import Any

from sqlalchemy import exc, select, update

from bot.database.methods.read import invalidate_user_cache, invalidate_stats_cache, invalidate_item_cache, \
    invalidate_category_cache
from bot.database.methods.cache_utils import safe_create_task
from bot.database.models import User, ItemValues, Goods, Categories, BoughtGoods, Role
from bot.database.models.main import LedgerEntries, PromoCodes, FraudEvents
from bot.database import Database
from bot.i18n import is_supported_locale, localize, normalize_locale


async def set_role(telegram_id: int, role: int) -> None:
    """Set user's role (by Telegram ID) and commit."""
    async with Database().session() as s:
        await s.execute(
            update(User).where(User.telegram_id == telegram_id).values(role_id=role)
        )

    safe_create_task(invalidate_user_cache(telegram_id))


async def update_balance(telegram_id: int, summ: int) -> None:
    """Increase user's balance by `summ` and commit."""
    async with Database().session() as s:
        user = (await s.execute(
            select(User).where(User.telegram_id == telegram_id).with_for_update()
        )).scalars().one_or_none()
        if not user:
            return
        user.balance += summ
        s.add(LedgerEntries(
            user_id=telegram_id,
            account_type="balance",
            entry_type="manual_adjustment",
            amount=Decimal(str(summ)).quantize(Decimal("0.01")),
            status="available",
            reference_type="user_balance",
            reference_id=str(telegram_id),
        ))

    safe_create_task(invalidate_user_cache(telegram_id))
    safe_create_task(invalidate_stats_cache())


async def set_user_locale(telegram_id: int, locale: str) -> bool:
    """Set user's preferred locale. Returns False for unsupported locale or missing user."""
    normalized = normalize_locale(locale)
    if not normalized or not is_supported_locale(normalized):
        return False

    async with Database().session() as s:
        result = await s.execute(select(User).where(User.telegram_id == telegram_id))
        user = result.scalars().first()
        if not user:
            return False
        user.locale = normalized

    await invalidate_user_cache(telegram_id)
    return True


async def update_item(
    item_name: str,
    new_name: str,
    description: str,
    price,
    category: str,
    points_price: int | None = None,
) -> tuple[bool, str | None]:
    """
    Update a Goods record with proper locking. Now uses integer PKs.
    """
    try:
        async with Database().session() as s:
            result = await s.execute(
                select(Goods).where(Goods.name == item_name).with_for_update()
            )
            goods = result.scalars().one_or_none()

            if not goods:
                return False, localize("admin.goods.update.position.invalid")

            cat_id = (await s.execute(
                select(Categories.id).where(Categories.name == category)
            )).scalar()
            if not cat_id:
                return False, localize("admin.goods.update.position.invalid")

            if new_name == item_name:
                goods.description = description
                goods.price = price
                if points_price is not None:
                    goods.points_price = max(int(points_price), 0)
                goods.category_id = cat_id
                return True, None

            existing = (await s.execute(
                select(Goods).where(Goods.name == new_name)
            )).scalars().first()
            if existing:
                return False, localize("admin.goods.update.position.exists")

            goods.name = new_name
            goods.description = description
            goods.price = price
            if points_price is not None:
                goods.points_price = max(int(points_price), 0)
            goods.category_id = cat_id

            await s.execute(
                update(BoughtGoods).where(BoughtGoods.item_name == item_name).values(item_name=new_name)
            )

            safe_create_task(invalidate_item_cache(item_name, category))
            if new_name != item_name:
                safe_create_task(invalidate_item_cache(new_name, category))

            return True, None

    except exc.SQLAlchemyError as e:
        return False, f"DB Error: {e.__class__.__name__}"


async def set_user_blocked(
        telegram_id: int,
        blocked: bool,
        *,
        reason: str = "",
        actor_id: int | None = None,
        source: str = "admin",
) -> bool:
    """Set user blocked status and commit."""
    async with Database().session() as s:
        result = await s.execute(select(User).where(User.telegram_id == telegram_id))
        user = result.scalars().first()
        if user:
            user.is_blocked = blocked
            event_type = "ban" if blocked else "unban"
            s.add(FraudEvents(
                subject_type="user",
                subject_id=str(telegram_id),
                event_type=event_type,
                evidence={
                    "blocked": blocked,
                    "reason": str(reason or "")[:255],
                    "actor_id": actor_id,
                    "source": source,
                },
                score_delta=5 if blocked else -5,
                status="open",
            ))
            safe_create_task(invalidate_user_cache(telegram_id))
            return True
        return False


async def record_user_appeal(
        telegram_id: int,
        *,
        reason: str,
        source: str = "mini_app",
        evidence: dict | None = None,
        dedupe_key: str | None = None,
) -> dict[str, Any]:
    from bot.database.methods.platform import _redact_evidence, _safe_summary

    appeal_dedupe_key = _safe_summary(dedupe_key or "", max_len=128)
    async with Database().session() as s:
        user = (await s.execute(select(User).where(User.telegram_id == telegram_id))).scalars().one_or_none()
        if not user:
            raise ValueError("user not found")
        if appeal_dedupe_key:
            existing = (await s.execute(
                select(FraudEvents)
                .where(
                    FraudEvents.subject_type == "user",
                    FraudEvents.subject_id == str(telegram_id),
                    FraudEvents.event_type == "appeal",
                    FraudEvents.status.in_(("open", "under_review")),
                )
                .order_by(FraudEvents.created_at.asc(), FraudEvents.id.asc())
            )).scalars().all()
            for event in existing:
                if (event.evidence or {}).get("dedupe_key") == appeal_dedupe_key:
                    return {
                        "id": event.id,
                        "subject_id": event.subject_id,
                        "event_type": event.event_type,
                        "status": event.status,
                        "duplicate": True,
                    }
        appeal_evidence = {
            "reason": _safe_summary(reason, max_len=1000),
            "source": _safe_summary(source, max_len=64),
            "evidence": _redact_evidence(evidence or {}),
        }
        if appeal_dedupe_key:
            appeal_evidence["dedupe_key"] = appeal_dedupe_key
        appeal = FraudEvents(
            subject_type="user",
            subject_id=str(telegram_id),
            event_type="appeal",
            evidence=appeal_evidence,
            score_delta=0,
            status="open",
        )
        s.add(appeal)
        await s.flush()
        return {
            "id": appeal.id,
            "subject_id": appeal.subject_id,
            "event_type": appeal.event_type,
            "status": appeal.status,
            "duplicate": False,
        }


async def is_user_blocked(telegram_id: int) -> bool:
    """Check if user is blocked."""
    async with Database().session() as s:
        result = await s.execute(select(User).where(User.telegram_id == telegram_id))
        user = result.scalars().first()
        return user.is_blocked if user else False


async def update_category(category_name: str, new_name: str) -> None:
    """Rename a category. With integer PKs, just update the name field."""
    async with Database().session() as s:
        result = await s.execute(
            select(Categories).where(Categories.name == category_name).with_for_update()
        )
        category = result.scalars().one_or_none()

        if not category:
            raise ValueError("Category not found")

        category.name = new_name

    safe_create_task(invalidate_category_cache(category_name))
    if new_name != category_name:
        safe_create_task(invalidate_category_cache(new_name))


async def update_role(role_id: int, name: str, permissions: int) -> tuple[bool, str | None]:
    """Update role name and permissions. Returns (success, error_message)."""
    async with Database().session() as s:
        result = await s.execute(
            select(Role).where(Role.id == role_id).with_for_update()
        )
        role = result.scalars().first()
        if not role:
            return False, "Role not found"
        if role.name != name:
            existing = (await s.execute(select(Role).where(Role.name == name))).scalars().first()
            if existing:
                return False, "Role name already exists"
        role.name = name
        role.permissions = permissions
        return True, None


async def toggle_promo_code(promo_id: int) -> bool | None:
    """Toggle promo code active status. Returns new is_active or None if not found."""
    async with Database().session() as s:
        result = await s.execute(
            select(PromoCodes).where(PromoCodes.id == promo_id).with_for_update()
        )
        promo = result.scalars().first()
        if not promo:
            return None
        promo.is_active = not promo.is_active
        return promo.is_active
