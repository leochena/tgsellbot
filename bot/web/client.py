import logging
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from html import escape
from typing import Any

from sqlalchemy import case
from sqlalchemy import delete as sa_delete
from sqlalchemy import exists, func, select, update as sa_update
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.routing import Route

from bot.database import Database
from bot.database.methods.audit import log_audit
from bot.database.methods.read import (
    invalidate_category_cache,
    invalidate_item_cache,
    invalidate_stats_cache,
)
from bot.database.models import BoughtGoods, Categories, Goods, ItemValues
from bot.database.models.main import CartItems, PromoCodes, stock_value_hash
from bot.misc import EnvKeys
from bot.misc.stock_format import stock_values_from_input
from bot.web.admin_i18n import get_admin_font_size

logger = logging.getLogger(__name__)


class ClientError(Exception):
    def __init__(self, message: str, status_code: int = 400, code: str = "bad_request"):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code


def _json_ok(data: dict[str, Any] | None = None, status_code: int = 200) -> JSONResponse:
    return JSONResponse({"ok": True, **(data or {})}, status_code=status_code)


def _json_error(message: str, status_code: int = 400, code: str = "bad_request") -> JSONResponse:
    return JSONResponse(
        {"ok": False, "error": message, "code": code},
        status_code=status_code,
    )


def _is_authenticated(request: Request) -> bool:
    return bool(request.session.get("authenticated"))


async def _request_json(request: Request) -> dict[str, Any]:
    try:
        data = await request.json()
    except Exception as exc:
        raise ClientError("请求体必须是 JSON。") from exc
    if not isinstance(data, dict):
        raise ClientError("请求体必须是 JSON 对象。")
    return data


async def _api_guard(request: Request, handler, *args):
    if not _is_authenticated(request):
        return _json_error("未登录，请先登录后台。", 401, "unauthorized")
    try:
        return await handler(request, *args)
    except ClientError as exc:
        return _json_error(exc.message, exc.status_code, exc.code)
    except Exception:
        logger.exception("Client API request failed")
        return _json_error("服务器处理失败，请查看日志。", 500, "server_error")


def _clean_text(value: Any, field: str, max_len: int, *, allow_empty: bool = False) -> str:
    text = str(value or "").strip()
    if not text and not allow_empty:
        raise ClientError(f"{field}不能为空。")
    if len(text) > max_len:
        raise ClientError(f"{field}不能超过 {max_len} 个字符。")
    return text


def _parse_price(value: Any) -> Decimal:
    try:
        price = Decimal(str(value).strip())
    except (InvalidOperation, AttributeError) as exc:
        raise ClientError("价格必须是数字。") from exc
    if price < 0:
        raise ClientError("价格不能为负数。")
    return price.quantize(Decimal("0.01"))


def _parse_decimal(value: Any, field: str) -> Decimal:
    try:
        parsed = Decimal(str(value).strip())
    except (InvalidOperation, AttributeError) as exc:
        raise ClientError(f"{field}必须是数字。") from exc
    if parsed <= 0:
        raise ClientError(f"{field}必须大于 0。")
    return parsed.quantize(Decimal("0.01"))


def _parse_positive_int(value: Any, field: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ClientError(f"{field}必须是有效数字。") from exc
    if parsed <= 0:
        raise ClientError(f"{field}必须是有效数字。")
    return parsed


def _parse_non_negative_int(value: Any, field: str) -> int:
    if value in (None, ""):
        return 0
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ClientError(f"{field}必须是有效数字。") from exc
    if parsed < 0:
        raise ClientError(f"{field}不能为负数。")
    return parsed


def _parse_positive_int_with_default(value: Any, field: str, default: int = 1) -> int:
    if value in (None, ""):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ClientError(f"{field}必须是有效数字。") from exc
    if parsed <= 0:
        raise ClientError(f"{field}必须大于 0。")
    return parsed


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on", "infinite"}


def _stock_lines(raw: Any, *, max_lines: int = 1000) -> tuple[list[str], int, int]:
    try:
        return stock_values_from_input(raw, max_lines=max_lines)
    except ValueError as exc:
        raise ClientError(str(exc)) from exc


def _mask_value(value: str | None) -> str:
    text = value or ""
    if not text:
        return "空值"
    if len(text) <= 4:
        return "*" * len(text)
    if len(text) <= 10:
        return f"{text[:2]}...{text[-2:]}"
    return f"{text[:4]}...{text[-4:]}"


def _normalize_promo_code(value: Any) -> str:
    code = _clean_text(value, "兑换码", 50).upper()
    if any(ch.isspace() for ch in code):
        raise ClientError("兑换码不能包含空格。")
    return code


def _parse_promo_expires(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        try:
            parsed = datetime.strptime(text, "%Y-%m-%d")
        except ValueError as exc:
            raise ClientError("过期时间格式无效。") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _promo_label(discount_type: str) -> str:
    labels = {
        "balance": "余额兑换码",
        "percent": "商品折扣码（百分比）",
        "fixed": "商品折扣码（固定减免）",
    }
    return labels.get(discount_type, discount_type)


async def catalog_snapshot() -> dict[str, Any]:
    async with Database().session() as s:
        category_rows = (
            await s.execute(select(Categories.id, Categories.name).order_by(Categories.name.asc()))
        ).all()

        product_count_rows = (
            await s.execute(
                select(Goods.category_id, func.count(Goods.id))
                .group_by(Goods.category_id)
            )
        ).all()
        product_counts = {row[0]: row[1] for row in product_count_rows}

        stock_count = func.count(ItemValues.id).label("stock_count")
        infinite_count = func.sum(
            case((ItemValues.is_infinity.is_(True), 1), else_=0)
        ).label("infinite_count")

        product_rows = (
            await s.execute(
                select(
                    Goods.id,
                    Goods.name,
                    Goods.description,
                    Goods.price,
                    Goods.points_price,
                    Goods.points_max_per_redeem,
                    Goods.lottery_enabled,
                    Goods.lottery_level,
                    Goods.lottery_winners_count,
                    Goods.category_id,
                    Categories.name.label("category_name"),
                    stock_count,
                    infinite_count,
                )
                .join(Categories, Categories.id == Goods.category_id)
                .outerjoin(ItemValues, ItemValues.item_id == Goods.id)
                .group_by(
                    Goods.id,
                    Goods.name,
                    Goods.description,
                    Goods.price,
                    Goods.points_price,
                    Goods.points_max_per_redeem,
                    Goods.lottery_enabled,
                    Goods.lottery_level,
                    Goods.lottery_winners_count,
                    Goods.category_id,
                    Categories.name,
                )
                .order_by(Categories.name.asc(), Goods.name.asc())
            )
        ).all()

    categories = [
        {
            "id": row.id,
            "name": row.name,
            "products_count": product_counts.get(row.id, 0),
        }
        for row in category_rows
    ]

    products = [
        {
            "id": row.id,
            "name": row.name,
            "description": row.description,
            "price": str(row.price),
            "points_price": int(row.points_price or 0),
            "points_max_per_redeem": int(row.points_max_per_redeem or 1),
            "lottery_enabled": bool(row.lottery_enabled),
            "lottery_level": row.lottery_level or "",
            "lottery_winners_count": int(row.lottery_winners_count or 1),
            "category_id": row.category_id,
            "category_name": row.category_name,
            "stock_count": int(row.stock_count or 0),
            "is_infinity": int(row.infinite_count or 0) > 0,
        }
        for row in product_rows
    ]

    return {
        "categories": categories,
        "products": products,
        "stats": {
            "categories": len(categories),
            "products": len(products),
            "stock_values": sum(p["stock_count"] for p in products),
            "infinite_products": sum(1 for p in products if p["is_infinity"]),
        },
    }


async def promo_snapshot() -> dict[str, Any]:
    async with Database().session() as s:
        rows = (
            await s.execute(
                select(
                    PromoCodes,
                    Categories.name.label("category_name"),
                    Goods.name.label("item_name"),
                )
                .outerjoin(Categories, Categories.id == PromoCodes.category_id)
                .outerjoin(Goods, Goods.id == PromoCodes.item_id)
                .order_by(PromoCodes.created_at.desc(), PromoCodes.id.desc())
            )
        ).all()

    promos = []
    for row in rows:
        promo = row.PromoCodes
        promos.append(
            {
                "id": promo.id,
                "code": promo.code,
                "discount_type": promo.discount_type,
                "discount_type_label": _promo_label(promo.discount_type),
                "discount_value": str(promo.discount_value),
                "max_uses": int(promo.max_uses or 0),
                "current_uses": int(promo.current_uses or 0),
                "expires_at": promo.expires_at.isoformat() if promo.expires_at else "",
                "category_id": promo.category_id,
                "category_name": row.category_name or "",
                "item_id": promo.item_id,
                "item_name": row.item_name or "",
                "is_active": bool(promo.is_active),
                "created_at": promo.created_at.isoformat() if promo.created_at else "",
            }
        )

    return {
        "promos": promos,
        "stats": {
            "promos": len(promos),
            "active": sum(1 for promo in promos if promo["is_active"]),
            "balance": sum(1 for promo in promos if promo["discount_type"] == "balance"),
            "product": sum(1 for promo in promos if promo["discount_type"] != "balance"),
        },
    }


async def create_category_record(data: dict[str, Any], ip_address: str | None = None) -> dict[str, Any]:
    name = _clean_text(data.get("name"), "分类名称", 100)

    async with Database().session() as s:
        duplicate = (
            await s.execute(select(exists().where(Categories.name == name)))
        ).scalar()
        if duplicate:
            raise ClientError("分类已存在。", 409, "category_exists")

        category = Categories(name=name)
        s.add(category)
        await s.flush()
        category_id = category.id

    await invalidate_stats_cache()
    await log_audit(
        "client_create_category",
        resource_type="Category",
        resource_id=name,
        ip_address=ip_address,
    )
    return {"category": {"id": category_id, "name": name, "products_count": 0}}


async def update_category_record(
    category_id: int,
    data: dict[str, Any],
    ip_address: str | None = None,
) -> dict[str, Any]:
    name = _clean_text(data.get("name"), "分类名称", 100)

    async with Database().session() as s:
        category = (
            await s.execute(select(Categories).where(Categories.id == category_id).with_for_update())
        ).scalars().one_or_none()
        if not category:
            raise ClientError("分类不存在。", 404, "category_not_found")

        duplicate = (
            await s.execute(
                select(exists().where(Categories.name == name, Categories.id != category_id))
            )
        ).scalar()
        if duplicate:
            raise ClientError("分类名称已存在。", 409, "category_exists")

        old_name = category.name
        category.name = name

    await invalidate_category_cache(old_name)
    await invalidate_category_cache(name)
    await log_audit(
        "client_update_category",
        resource_type="Category",
        resource_id=str(category_id),
        details=f"old_name={old_name}, new_name={name}",
        ip_address=ip_address,
    )
    return {"category": {"id": category_id, "name": name}}


async def delete_category_record(category_id: int, ip_address: str | None = None) -> dict[str, Any]:
    async with Database().session() as s:
        category = (
            await s.execute(select(Categories).where(Categories.id == category_id).with_for_update())
        ).scalars().one_or_none()
        if not category:
            raise ClientError("分类不存在。", 404, "category_not_found")

        product_rows = (
            await s.execute(select(Goods.id, Goods.name).where(Goods.category_id == category_id))
        ).all()
        product_ids = [row.id for row in product_rows]
        product_names = [row.name for row in product_rows]
        category_name = category.name

        if product_ids:
            await s.execute(sa_delete(ItemValues).where(ItemValues.item_id.in_(product_ids)))
            await s.execute(sa_delete(Goods).where(Goods.id.in_(product_ids)))
        await s.delete(category)

    await invalidate_category_cache(category_name)
    await invalidate_stats_cache()
    for product_name in product_names:
        await invalidate_item_cache(product_name)
    await log_audit(
        "client_delete_category",
        resource_type="Category",
        resource_id=category_name,
        details=f"deleted_products={len(product_names)}",
        ip_address=ip_address,
    )
    return {"deleted_products": len(product_names)}


async def create_product_record(data: dict[str, Any], ip_address: str | None = None) -> dict[str, Any]:
    name = _clean_text(data.get("name"), "商品位名称", 100)
    description = _clean_text(data.get("description", ""), "商品说明", 5000, allow_empty=True)
    price = _parse_price(data.get("price"))
    points_price = _parse_non_negative_int(data.get("points_price"), "积分价")
    points_max_per_redeem = _parse_positive_int_with_default(data.get("points_max_per_redeem"), "单次兑换上限")
    lottery_enabled = _as_bool(data.get("lottery_enabled"))
    lottery_level = _clean_text(data.get("lottery_level", ""), "获奖等级", 64, allow_empty=not lottery_enabled)
    lottery_winners_count = _parse_positive_int_with_default(data.get("lottery_winners_count"), "获奖人数")
    category_id = _parse_positive_int(data.get("category_id"), "分类")
    is_infinity = _as_bool(data.get("is_infinity"))
    values, skipped_empty, skipped_duplicate = _stock_lines(data.get("stock_values"))

    if is_infinity and not values:
        raise ClientError("无限库存商品必须填写交付内容。")

    async with Database().session() as s:
        category = (
            await s.execute(select(Categories).where(Categories.id == category_id))
        ).scalars().one_or_none()
        if not category:
            raise ClientError("分类不存在。", 404, "category_not_found")

        duplicate = (
            await s.execute(select(exists().where(Goods.name == name)))
        ).scalar()
        if duplicate:
            raise ClientError("商品位名称已存在。", 409, "product_exists")

        product = Goods(
            name=name,
            description=description,
            price=price,
            points_price=points_price,
            points_max_per_redeem=points_max_per_redeem,
            lottery_enabled=lottery_enabled,
            lottery_level=lottery_level if lottery_enabled else "",
            lottery_winners_count=lottery_winners_count,
            category_id=category_id,
        )
        s.add(product)
        await s.flush()

        add_values = values[:1] if is_infinity else values
        for value in add_values:
            s.add(ItemValues(item_id=product.id, value=value, is_infinity=is_infinity))
        product_id = product.id

    await invalidate_item_cache(name, category.name)
    await invalidate_stats_cache()
    await log_audit(
        "client_create_product",
        resource_type="Item",
        resource_id=name,
        details=f"category={category.name}, values={len(add_values)}, infinite={is_infinity}",
        ip_address=ip_address,
    )
    return {
        "product": {
            "id": product_id,
            "name": name,
            "description": description,
            "price": str(price),
            "points_price": points_price,
            "points_max_per_redeem": points_max_per_redeem,
            "lottery_enabled": lottery_enabled,
            "lottery_level": lottery_level if lottery_enabled else "",
            "lottery_winners_count": lottery_winners_count,
            "category_id": category_id,
            "category_name": category.name,
            "stock_count": len(add_values),
            "is_infinity": is_infinity,
        },
        "stock": {
            "added": len(add_values),
            "skipped_empty": skipped_empty,
            "skipped_duplicate": skipped_duplicate,
            "skipped_extra_infinite": max(0, len(values) - 1) if is_infinity else 0,
        },
    }


async def update_product_record(
    product_id: int,
    data: dict[str, Any],
    ip_address: str | None = None,
) -> dict[str, Any]:
    name = _clean_text(data.get("name"), "商品位名称", 100)
    description = _clean_text(data.get("description", ""), "商品说明", 5000, allow_empty=True)
    price = _parse_price(data.get("price"))
    points_price = _parse_non_negative_int(data.get("points_price"), "积分价")
    points_max_per_redeem = _parse_positive_int_with_default(data.get("points_max_per_redeem"), "单次兑换上限")
    lottery_enabled = _as_bool(data.get("lottery_enabled"))
    lottery_level = _clean_text(data.get("lottery_level", ""), "获奖等级", 64, allow_empty=not lottery_enabled)
    lottery_winners_count = _parse_positive_int_with_default(data.get("lottery_winners_count"), "获奖人数")
    category_id = _parse_positive_int(data.get("category_id"), "分类")
    requested_mode = data.get("is_infinity")
    values, skipped_empty, skipped_duplicate = _stock_lines(data.get("stock_values"))

    async with Database().session() as s:
        product = (
            await s.execute(select(Goods).where(Goods.id == product_id).with_for_update())
        ).scalars().one_or_none()
        if not product:
            raise ClientError("商品位不存在。", 404, "product_not_found")

        category = (
            await s.execute(select(Categories).where(Categories.id == category_id))
        ).scalars().one_or_none()
        if not category:
            raise ClientError("分类不存在。", 404, "category_not_found")

        duplicate = (
            await s.execute(
                select(exists().where(Goods.name == name, Goods.id != product_id))
            )
        ).scalar()
        if duplicate:
            raise ClientError("商品位名称已存在。", 409, "product_exists")

        old_name = product.name
        current_infinite = (
            await s.execute(
                select(exists().where(
                    ItemValues.item_id == product_id,
                    ItemValues.is_infinity.is_(True),
                ))
            )
        ).scalar()

        mode_changed = requested_mode is not None and _as_bool(requested_mode) != current_infinite
        new_infinite = _as_bool(requested_mode, current_infinite)
        added = 0

        if mode_changed:
            await s.execute(sa_delete(ItemValues).where(ItemValues.item_id == product_id))
            if new_infinite:
                if not values:
                    raise ClientError("切换为无限库存时必须填写交付内容。")
                s.add(ItemValues(item_id=product_id, value=values[0], is_infinity=True))
                added = 1
            else:
                for value in values:
                    s.add(ItemValues(item_id=product_id, value=value, is_infinity=False))
                added = len(values)

        product.name = name
        product.description = description
        product.price = price
        product.points_price = points_price
        product.points_max_per_redeem = points_max_per_redeem
        product.lottery_enabled = lottery_enabled
        product.lottery_level = lottery_level if lottery_enabled else ""
        product.lottery_winners_count = lottery_winners_count
        product.category_id = category_id

        if name != old_name:
            await s.execute(
                sa_update(BoughtGoods)
                .where(BoughtGoods.item_name == old_name)
                .values(item_name=name)
            )
            await s.execute(
                sa_update(CartItems)
                .where(CartItems.item_name == old_name)
                .values(item_name=name)
            )

    await invalidate_item_cache(old_name)
    await invalidate_item_cache(name, category.name)
    await invalidate_stats_cache()
    await log_audit(
        "client_update_product",
        resource_type="Item",
        resource_id=name,
        details=f"old_name={old_name}, mode_changed={mode_changed}, values={added}",
        ip_address=ip_address,
    )
    return {
        "product": {
            "id": product_id,
            "name": name,
            "description": description,
            "price": str(price),
            "points_price": points_price,
            "points_max_per_redeem": points_max_per_redeem,
            "lottery_enabled": lottery_enabled,
            "lottery_level": lottery_level if lottery_enabled else "",
            "lottery_winners_count": lottery_winners_count,
            "category_id": category_id,
            "category_name": category.name,
            "is_infinity": new_infinite,
        },
        "stock": {
            "added": added,
            "skipped_empty": skipped_empty if mode_changed else 0,
            "skipped_duplicate": skipped_duplicate if mode_changed else 0,
        },
    }


async def delete_product_record(product_id: int, ip_address: str | None = None) -> dict[str, Any]:
    async with Database().session() as s:
        product = (
            await s.execute(select(Goods).where(Goods.id == product_id).with_for_update())
        ).scalars().one_or_none()
        if not product:
            raise ClientError("商品位不存在。", 404, "product_not_found")

        name = product.name
        await s.execute(sa_delete(ItemValues).where(ItemValues.item_id == product_id))
        await s.delete(product)

    await invalidate_item_cache(name)
    await invalidate_stats_cache()
    await log_audit(
        "client_delete_product",
        resource_type="Item",
        resource_id=name,
        ip_address=ip_address,
    )
    return {"deleted": True}


async def add_stock_record(
    product_id: int,
    data: dict[str, Any],
    ip_address: str | None = None,
) -> dict[str, Any]:
    values, skipped_empty, skipped_duplicate = _stock_lines(data.get("stock_values"))
    if not values:
        raise ClientError("请填写要添加的库存内容。")

    async with Database().session() as s:
        product = (
            await s.execute(select(Goods).where(Goods.id == product_id))
        ).scalars().one_or_none()
        if not product:
            raise ClientError("商品位不存在。", 404, "product_not_found")

        infinite = (
            await s.execute(
                select(exists().where(
                    ItemValues.item_id == product_id,
                    ItemValues.is_infinity.is_(True),
                ))
            )
        ).scalar()
        if infinite:
            raise ClientError("无限库存商品不能追加普通库存，请先编辑商品位切换库存模式。", 409, "infinite_stock")

        value_hashes = {stock_value_hash(value): value for value in values}
        existing_rows = (
            await s.execute(
                select(ItemValues.value_hash).where(
                    ItemValues.item_id == product_id,
                    ItemValues.value_hash.in_(value_hashes.keys()),
                )
            )
        ).all()
        existing_hashes = {row[0] for row in existing_rows}
        add_values = [value for value in values if stock_value_hash(value) not in existing_hashes]

        for value in add_values:
            s.add(ItemValues(item_id=product_id, value=value, is_infinity=False))

        product_name = product.name

    await invalidate_item_cache(product_name)
    await invalidate_stats_cache()
    await log_audit(
        "client_add_stock",
        resource_type="Item",
        resource_id=product_name,
        details=f"added={len(add_values)}, dup={len(existing_hashes)}",
        ip_address=ip_address,
    )
    return {
        "stock": {
            "added": len(add_values),
            "skipped_empty": skipped_empty,
            "skipped_duplicate": skipped_duplicate,
            "skipped_existing": len(existing_hashes),
        }
    }


async def stock_preview(product_id: int, limit: int = 50) -> dict[str, Any]:
    limit = max(1, min(int(limit or 50), 200))
    async with Database().session() as s:
        product = (
            await s.execute(select(Goods).where(Goods.id == product_id))
        ).scalars().one_or_none()
        if not product:
            raise ClientError("商品位不存在。", 404, "product_not_found")

        total = (
            await s.execute(
                select(func.count(ItemValues.id)).where(ItemValues.item_id == product_id)
            )
        ).scalar() or 0
        rows = (
            await s.execute(
                select(ItemValues.id, ItemValues.value, ItemValues.is_infinity)
                .where(ItemValues.item_id == product_id)
                .order_by(ItemValues.id.asc())
                .limit(limit)
            )
        ).all()

    return {
        "product": {"id": product.id, "name": product.name},
        "total": total,
        "items": [
            {
                "id": row.id,
                "value_masked": _mask_value(row.value),
                "length": len(row.value or ""),
                "is_infinity": bool(row.is_infinity),
            }
            for row in rows
        ],
    }


async def delete_stock_record(stock_id: int, ip_address: str | None = None) -> dict[str, Any]:
    async with Database().session() as s:
        row = (
            await s.execute(
                select(ItemValues, Goods.name.label("product_name"))
                .join(Goods, Goods.id == ItemValues.item_id)
                .where(ItemValues.id == stock_id)
                .with_for_update()
            )
        ).first()
        if not row:
            raise ClientError("库存不存在。", 404, "stock_not_found")

        product_name = row.product_name
        await s.delete(row.ItemValues)

    await invalidate_item_cache(product_name)
    await invalidate_stats_cache()
    await log_audit(
        "client_delete_stock",
        resource_type="Stock",
        resource_id=str(stock_id),
        details=f"product={product_name}",
        ip_address=ip_address,
    )
    return {"deleted": True}


async def create_promo_record(data: dict[str, Any], ip_address: str | None = None) -> dict[str, Any]:
    code = _normalize_promo_code(data.get("code"))
    discount_type = _clean_text(data.get("discount_type"), "兑换码类型", 10)
    if discount_type not in {"balance", "percent", "fixed"}:
        raise ClientError("兑换码类型无效。")

    discount_value = _parse_decimal(data.get("discount_value"), "数值")
    if discount_type == "percent" and discount_value > Decimal("100"):
        raise ClientError("百分比折扣不能超过 100。")

    max_uses = _parse_non_negative_int(data.get("max_uses"), "最大使用次数")
    expires_at = _parse_promo_expires(data.get("expires_at"))
    is_active = _as_bool(data.get("is_active"), True)
    category_id = None
    item_id = None

    if discount_type != "balance":
        raw_item_id = data.get("item_id")
        raw_category_id = data.get("category_id")
        if raw_item_id not in (None, ""):
            item_id = _parse_positive_int(raw_item_id, "绑定商品")
        elif raw_category_id not in (None, ""):
            category_id = _parse_positive_int(raw_category_id, "绑定分类")

    async with Database().session() as s:
        duplicate = (
            await s.execute(select(exists().where(func.upper(PromoCodes.code) == code)))
        ).scalar()
        if duplicate:
            raise ClientError("该兑换码已存在。", 409, "promo_exists")

        category_name = ""
        item_name = ""
        if category_id:
            category = (
                await s.execute(select(Categories).where(Categories.id == category_id))
            ).scalars().one_or_none()
            if not category:
                raise ClientError("绑定分类不存在。", 404, "category_not_found")
            category_name = category.name
        if item_id:
            item = (
                await s.execute(select(Goods).where(Goods.id == item_id))
            ).scalars().one_or_none()
            if not item:
                raise ClientError("绑定商品不存在。", 404, "product_not_found")
            item_name = item.name

        promo = PromoCodes(
            code=code,
            discount_type=discount_type,
            discount_value=discount_value,
            max_uses=max_uses,
            expires_at=expires_at,
            category_id=category_id,
            item_id=item_id,
            is_active=is_active,
        )
        s.add(promo)
        await s.flush()
        promo_id = promo.id

    await invalidate_stats_cache()
    await log_audit(
        "client_create_promo",
        resource_type="PromoCode",
        resource_id=code,
        details=f"type={discount_type}, value={discount_value}, max_uses={max_uses}",
        ip_address=ip_address,
    )
    return {
        "promo": {
            "id": promo_id,
            "code": code,
            "discount_type": discount_type,
            "discount_type_label": _promo_label(discount_type),
            "discount_value": str(discount_value),
            "max_uses": max_uses,
            "current_uses": 0,
            "expires_at": expires_at.isoformat() if expires_at else "",
            "category_id": category_id,
            "category_name": category_name,
            "item_id": item_id,
            "item_name": item_name,
            "is_active": is_active,
        }
    }


async def toggle_promo_record(promo_id: int, ip_address: str | None = None) -> dict[str, Any]:
    async with Database().session() as s:
        promo = (
            await s.execute(select(PromoCodes).where(PromoCodes.id == promo_id).with_for_update())
        ).scalars().one_or_none()
        if not promo:
            raise ClientError("兑换码不存在。", 404, "promo_not_found")
        promo.is_active = not promo.is_active
        is_active = bool(promo.is_active)
        code = promo.code

    await invalidate_stats_cache()
    await log_audit(
        "client_toggle_promo",
        resource_type="PromoCode",
        resource_id=code,
        details=f"is_active={is_active}",
        ip_address=ip_address,
    )
    return {"promo": {"id": promo_id, "code": code, "is_active": is_active}}


async def delete_promo_record(promo_id: int, ip_address: str | None = None) -> dict[str, Any]:
    async with Database().session() as s:
        promo = (
            await s.execute(select(PromoCodes).where(PromoCodes.id == promo_id).with_for_update())
        ).scalars().one_or_none()
        if not promo:
            raise ClientError("兑换码不存在。", 404, "promo_not_found")
        code = promo.code
        await s.delete(promo)

    await invalidate_stats_cache()
    await log_audit(
        "client_delete_promo",
        resource_type="PromoCode",
        resource_id=code,
        ip_address=ip_address,
    )
    return {"deleted": True}


async def client_page(request: Request):
    return RedirectResponse("/admin/operations", status_code=302)


async def operations_app_page(request: Request):
    if not _is_authenticated(request):
        return RedirectResponse("/admin/login", status_code=302)
    return HTMLResponse(_client_html(font_size=get_admin_font_size(request)))


async def client_home(request: Request):
    return RedirectResponse("/admin/operations", status_code=302)


def _client_html(font_size: int | None = None) -> str:
    balance_currency = escape(str(EnvKeys.BALANCE_CURRENCY))
    pay_currency = escape(str(EnvKeys.PAY_CURRENCY))
    stars_per_value = escape(str(EnvKeys.STARS_PER_VALUE))
    admin_font_size = str(font_size or 12)
    return (
        CLIENT_HTML
        .replace("__BALANCE_CURRENCY__", balance_currency)
        .replace("__PAY_CURRENCY__", pay_currency)
        .replace("__STARS_PER_VALUE__", stars_per_value)
        .replace("__ADMIN_FONT_SIZE__", admin_font_size)
    )


async def api_catalog(request: Request):
    return await _api_guard(request, _api_catalog)


async def _api_catalog(request: Request):
    return _json_ok({"catalog": await catalog_snapshot()})


async def api_promos(request: Request):
    return await _api_guard(request, _api_promos)


async def _api_promos(request: Request):
    return _json_ok({"promos": await promo_snapshot()})


async def api_create_category(request: Request):
    return await _api_guard(request, _api_create_category)


async def _api_create_category(request: Request):
    data = await _request_json(request)
    result = await create_category_record(data, request.client.host if request.client else None)
    return _json_ok(result, 201)


async def api_update_category(request: Request):
    return await _api_guard(request, _api_update_category, int(request.path_params["category_id"]))


async def _api_update_category(request: Request, category_id: int):
    data = await _request_json(request)
    result = await update_category_record(category_id, data, request.client.host if request.client else None)
    return _json_ok(result)


async def api_delete_category(request: Request):
    return await _api_guard(request, _api_delete_category, int(request.path_params["category_id"]))


async def _api_delete_category(request: Request, category_id: int):
    result = await delete_category_record(category_id, request.client.host if request.client else None)
    return _json_ok(result)


async def api_create_product(request: Request):
    return await _api_guard(request, _api_create_product)


async def _api_create_product(request: Request):
    data = await _request_json(request)
    result = await create_product_record(data, request.client.host if request.client else None)
    return _json_ok(result, 201)


async def api_update_product(request: Request):
    return await _api_guard(request, _api_update_product, int(request.path_params["product_id"]))


async def _api_update_product(request: Request, product_id: int):
    data = await _request_json(request)
    result = await update_product_record(product_id, data, request.client.host if request.client else None)
    return _json_ok(result)


async def api_delete_product(request: Request):
    return await _api_guard(request, _api_delete_product, int(request.path_params["product_id"]))


async def _api_delete_product(request: Request, product_id: int):
    result = await delete_product_record(product_id, request.client.host if request.client else None)
    return _json_ok(result)


async def api_add_stock(request: Request):
    return await _api_guard(request, _api_add_stock, int(request.path_params["product_id"]))


async def _api_add_stock(request: Request, product_id: int):
    data = await _request_json(request)
    result = await add_stock_record(product_id, data, request.client.host if request.client else None)
    return _json_ok(result, 201)


async def api_list_stock(request: Request):
    return await _api_guard(request, _api_list_stock, int(request.path_params["product_id"]))


async def _api_list_stock(request: Request, product_id: int):
    limit = int(request.query_params.get("limit", 50))
    return _json_ok({"stock": await stock_preview(product_id, limit)})


async def api_delete_stock(request: Request):
    return await _api_guard(request, _api_delete_stock, int(request.path_params["stock_id"]))


async def _api_delete_stock(request: Request, stock_id: int):
    return _json_ok(await delete_stock_record(stock_id, request.client.host if request.client else None))


async def api_create_promo(request: Request):
    return await _api_guard(request, _api_create_promo)


async def _api_create_promo(request: Request):
    data = await _request_json(request)
    result = await create_promo_record(data, request.client.host if request.client else None)
    return _json_ok(result, 201)


async def api_toggle_promo(request: Request):
    return await _api_guard(request, _api_toggle_promo, int(request.path_params["promo_id"]))


async def _api_toggle_promo(request: Request, promo_id: int):
    return _json_ok(await toggle_promo_record(promo_id, request.client.host if request.client else None))


async def api_delete_promo(request: Request):
    return await _api_guard(request, _api_delete_promo, int(request.path_params["promo_id"]))


async def _api_delete_promo(request: Request, promo_id: int):
    return _json_ok(await delete_promo_record(promo_id, request.client.host if request.client else None))


client_routes = [
    Route("/", client_home, methods=["GET"]),
    Route("/client", client_page, methods=["GET"]),
    Route("/admin/operations/app", operations_app_page, methods=["GET"]),
    Route("/admin/api/catalog", api_catalog, methods=["GET"]),
    Route("/admin/api/promos", api_promos, methods=["GET"]),
    Route("/admin/api/categories", api_create_category, methods=["POST"]),
    Route("/admin/api/categories/{category_id:int}", api_update_category, methods=["PUT"]),
    Route("/admin/api/categories/{category_id:int}", api_delete_category, methods=["DELETE"]),
    Route("/admin/api/products", api_create_product, methods=["POST"]),
    Route("/admin/api/products/{product_id:int}", api_update_product, methods=["PUT"]),
    Route("/admin/api/products/{product_id:int}", api_delete_product, methods=["DELETE"]),
    Route("/admin/api/products/{product_id:int}/stock", api_list_stock, methods=["GET"]),
    Route("/admin/api/products/{product_id:int}/stock", api_add_stock, methods=["POST"]),
    Route("/admin/api/stock/{stock_id:int}", api_delete_stock, methods=["DELETE"]),
    Route("/admin/api/promos", api_create_promo, methods=["POST"]),
    Route("/admin/api/promos/{promo_id:int}/toggle", api_toggle_promo, methods=["POST"]),
    Route("/admin/api/promos/{promo_id:int}", api_delete_promo, methods=["DELETE"]),
]


CLIENT_HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Telegram 商店后台 · 商品运营</title>
  <style>
    :root {
      color-scheme: light;
      font-size: __ADMIN_FONT_SIZE__pt;
      --bg: #f6f7f8;
      --panel: #ffffff;
      --line: #d9dee5;
      --text: #17202a;
      --muted: #657184;
      --accent: #00796b;
      --accent-2: #1f6feb;
      --danger: #b42318;
      --warn: #9a6700;
      --ok: #1a7f37;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font: 1rem/1.45 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      padding: 14px 20px;
      background: #ffffff;
      border-bottom: 1px solid var(--line);
      position: sticky;
      top: 0;
      z-index: 20;
    }
    h1 { margin: 0; font-size: 1.125rem; font-weight: 700; }
    h2 { margin: 0 0 12px; font-size: 1rem; }
    main { padding: 18px 20px 28px; }
    .actions, .row, .filters { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
    .grid { display: grid; gap: 14px; }
    .top { grid-template-columns: minmax(280px, 0.8fr) minmax(360px, 1.2fr); align-items: start; }
    .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
    }
    .metrics { display: grid; grid-template-columns: repeat(5, minmax(120px, 1fr)); gap: 10px; margin-bottom: 14px; }
    .metric {
      background: #ffffff;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
      min-height: 70px;
    }
    .metric strong { display: block; font-size: 1.35rem; line-height: 1.1; }
    .metric span { color: var(--muted); font-size: .9rem; }
    label { display: grid; gap: 5px; color: var(--muted); font-size: .9rem; }
    input, select, textarea {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 8px 9px;
      background: #ffffff;
      color: var(--text);
      font: inherit;
      min-height: 36px;
    }
    textarea { min-height: 96px; resize: vertical; }
    button, .linkbtn {
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #ffffff;
      color: var(--text);
      padding: 8px 10px;
      min-height: 36px;
      cursor: pointer;
      text-decoration: none;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 6px;
      white-space: nowrap;
    }
    button.primary { background: var(--accent); border-color: var(--accent); color: #ffffff; }
    button.blue { background: var(--accent-2); border-color: var(--accent-2); color: #ffffff; }
    button.danger { border-color: #f1b8b3; color: var(--danger); }
    button:disabled { cursor: not-allowed; opacity: 0.55; }
    table { width: 100%; border-collapse: collapse; background: #ffffff; border: 1px solid var(--line); border-radius: 8px; overflow: hidden; }
    th, td { padding: 10px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }
    th { color: var(--muted); font-size: .9rem; font-weight: 700; background: #fafbfc; }
    tr:last-child td { border-bottom: 0; }
    .name { font-weight: 700; }
    .muted { color: var(--muted); }
    .badge {
      display: inline-flex;
      align-items: center;
      min-height: 24px;
      border-radius: 999px;
      padding: 2px 8px;
      font-size: .9rem;
      border: 1px solid var(--line);
      color: var(--muted);
      background: #ffffff;
    }
    .badge.ok { color: var(--ok); border-color: #b7e2c0; }
    .badge.warn { color: var(--warn); border-color: #ecd59b; }
    .category-list { display: grid; gap: 8px; }
    .category-item {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 8px;
      align-items: center;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 9px;
      background: #ffffff;
    }
    .form-grid { display: grid; grid-template-columns: 1fr 130px; gap: 10px; }
    .form-grid .wide { grid-column: 1 / -1; }
    #status {
      min-height: 22px;
      color: var(--muted);
      font-size: 1rem;
    }
    #status.error { color: var(--danger); }
    #status.ok { color: var(--ok); }
    dialog {
      width: min(720px, calc(100vw - 28px));
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 0;
      box-shadow: 0 18px 50px rgba(0, 0, 0, 0.18);
    }
    dialog::backdrop { background: rgba(23, 32, 42, 0.35); }
    .modal-head, .modal-body, .modal-foot { padding: 14px; }
    .modal-head { border-bottom: 1px solid var(--line); display: flex; justify-content: space-between; align-items: center; }
    .modal-body { display: grid; gap: 10px; }
    .modal-foot { border-top: 1px solid var(--line); display: flex; justify-content: flex-end; gap: 8px; }
    .stock-list { display: grid; gap: 6px; max-height: 260px; overflow: auto; }
    .file-row {
      display: flex;
      gap: 8px;
      align-items: center;
      flex-wrap: wrap;
      margin-top: 6px;
    }
    .file-row input[type=file] {
      width: auto;
      min-height: 0;
      padding: 6px;
    }
    .stock-row {
      display: grid;
      grid-template-columns: 72px 1fr 74px 62px;
      gap: 8px;
      align-items: center;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 7px;
      background: #ffffff;
    }
    .help-grid { display: grid; grid-template-columns: repeat(2, minmax(220px, 1fr)); gap: 10px; margin-bottom: 12px; }
    .help-box {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px;
      background: #ffffff;
    }
    .help-box strong { display: block; margin-bottom: 4px; }
    @media (max-width: 900px) {
      header { align-items: flex-start; flex-direction: column; }
      .top, .metrics { grid-template-columns: 1fr; }
      .form-grid { grid-template-columns: 1fr; }
      .help-grid { grid-template-columns: 1fr; }
      th:nth-child(3), td:nth-child(3) { display: none; }
      .stock-row { grid-template-columns: 54px 1fr 62px; }
      .stock-row .len { display: none; }
    }
  </style>
</head>
<body>
  <header>
    <div>
      <h1>Telegram 商店后台 · 商品运营</h1>
      <div class="muted">后台会话 · 余额单位 __BALANCE_CURRENCY__，不是真实 __PAY_CURRENCY__ · Stars 换算：1 __BALANCE_CURRENCY__ = __STARS_PER_VALUE__ ⭐</div>
    </div>
    <div class="actions">
      <a class="linkbtn" href="#promoSection">兑换码</a>
      <button id="refreshBtn">刷新</button>
      <div id="status"></div>
    </div>
  </header>
  <main class="grid">
    <section class="metrics">
      <div class="metric"><strong id="mCategories">0</strong><span>分类</span></div>
      <div class="metric"><strong id="mProducts">0</strong><span>商品位</span></div>
      <div class="metric"><strong id="mStock">0</strong><span>库存条目</span></div>
      <div class="metric"><strong id="mInfinite">0</strong><span>无限库存</span></div>
      <div class="metric"><strong id="mPromos">0</strong><span>兑换码</span></div>
    </section>

    <section class="grid top">
      <div class="panel">
        <h2>分类</h2>
        <form id="categoryForm" class="row">
          <input name="name" maxlength="100" placeholder="分类名称" required>
          <button class="primary" type="submit">添加</button>
        </form>
        <div id="categoryList" class="category-list" style="margin-top:12px"></div>
      </div>

      <div class="panel">
        <h2>添加商品位</h2>
        <form id="productForm" class="form-grid">
          <label>名称<input name="name" maxlength="100" required></label>
          <label>余额价格（__BALANCE_CURRENCY__）<input name="price" inputmode="decimal" required></label>
          <label>积分兑换价<input name="points_price" inputmode="numeric" placeholder="0 表示不可兑换" value="0"></label>
          <label>单次兑换上限<input name="points_max_per_redeem" inputmode="numeric" min="1" value="1"></label>
          <label>分类<select name="category_id" required></select></label>
          <label>库存模式<select name="is_infinity"><option value="0">普通库存</option><option value="1">无限库存</option></select></label>
          <label>加入奖品池<select name="lottery_enabled"><option value="0">否</option><option value="1">是</option></select></label>
          <label>获奖等级<input name="lottery_level" maxlength="64" placeholder="例如 一等奖"></label>
          <label>该奖项中奖人数<input name="lottery_winners_count" inputmode="numeric" min="1" value="1"></label>
          <div class="wide muted">Stars 只用于充值内部余额；商品购买扣 __BALANCE_CURRENCY__。积分兑换价是签到积分通道。奖品池字段只在抽奖开奖时生效。</div>
          <label class="wide">说明<textarea name="description"></textarea></label>
          <label class="wide">库存内容<textarea name="stock_values" placeholder="每行一条，或粘贴 JSON 数组/对象"></textarea></label>
          <div class="wide file-row">
            <input id="productJsonFile" type="file" accept=".json,application/json" multiple>
            <span class="muted">支持多选 JSON：数组代表多条库存；对象代表一条结构化库存；选择文件只会填入库存内容，还需要填写商品信息并点击创建商品位。</span>
          </div>
          <div class="wide actions"><button class="primary" type="submit">创建商品位</button></div>
        </form>
      </div>
    </section>

    <section class="panel">
      <div class="row" style="justify-content:space-between;margin-bottom:12px">
        <h2 style="margin:0">商品位</h2>
        <div class="filters">
          <input id="searchInput" placeholder="搜索名称、分类、说明">
          <select id="categoryFilter"></select>
        </div>
      </div>
      <div style="overflow:auto">
        <table>
          <thead>
            <tr>
              <th>商品位</th>
              <th>分类</th>
              <th>说明</th>
              <th>余额价格</th>
              <th>积分兑换</th>
              <th>奖品池</th>
              <th>库存</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody id="productRows"></tbody>
        </table>
      </div>
    </section>

    <section id="promoSection" class="panel">
      <div class="row" style="justify-content:space-between;margin-bottom:12px">
        <h2 style="margin:0">兑换码</h2>
        <span class="muted">余额兑换码在机器人首页兑换；商品折扣码在商品详情页使用。</span>
      </div>
      <div class="help-grid">
        <div class="help-box">
          <strong>余额兑换码</strong>
          <div class="muted">用户点击机器人首页“余额兑换码”输入，成功后增加内部余额 __BALANCE_CURRENCY__。这不是免费提现，也不是真实 __PAY_CURRENCY__。</div>
        </div>
        <div class="help-box">
          <strong>商品折扣码</strong>
          <div class="muted">用户进入商品详情后点击“商品折扣码”输入，只抵扣该商品购买价格。可以绑定分类或单个商品。</div>
        </div>
      </div>
      <form id="promoForm" class="form-grid">
        <label>兑换码<input name="code" maxlength="50" autocomplete="off" placeholder="例如 VIP50 或 BALANCE100" required></label>
        <label>类型<select name="discount_type" id="promoType">
          <option value="balance">余额兑换码：增加 __BALANCE_CURRENCY__</option>
          <option value="percent">商品折扣码：百分比</option>
          <option value="fixed">商品折扣码：固定减免</option>
        </select></label>
        <label>数值<input name="discount_value" inputmode="decimal" placeholder="余额金额/折扣百分比/减免金额" required></label>
        <label>最大使用次数<input name="max_uses" inputmode="numeric" min="0" value="1"></label>
        <label>过期时间<input name="expires_at" type="datetime-local"></label>
        <label>状态<select name="is_active"><option value="1">启用</option><option value="0">停用</option></select></label>
        <label>绑定分类<select name="category_id" id="promoCategory"></select></label>
        <label>绑定商品<select name="item_id" id="promoProduct"></select></label>
        <div class="wide muted" id="promoHint">余额兑换码不绑定商品或分类；创建后用户可在机器人首页兑换。</div>
        <div class="wide actions"><button class="primary" type="submit">创建兑换码</button></div>
      </form>
      <div style="overflow:auto;margin-top:12px">
        <table>
          <thead>
            <tr>
              <th>兑换码</th>
              <th>类型</th>
              <th>数值</th>
              <th>使用次数</th>
              <th>绑定</th>
              <th>过期</th>
              <th>状态</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody id="promoRows"></tbody>
        </table>
      </div>
    </section>
  </main>

  <dialog id="editDialog">
    <form method="dialog">
      <div class="modal-head"><h2 style="margin:0">编辑商品位</h2><button value="cancel">关闭</button></div>
      <div class="modal-body">
        <input type="hidden" id="editId">
        <div class="form-grid">
          <label>名称<input id="editName" maxlength="100" required></label>
          <label>余额价格（__BALANCE_CURRENCY__）<input id="editPrice" inputmode="decimal" required></label>
          <label>积分兑换价<input id="editPointsPrice" inputmode="numeric" placeholder="0 表示不可兑换"></label>
          <label>单次兑换上限<input id="editPointsMaxPerRedeem" inputmode="numeric" min="1"></label>
          <label>分类<select id="editCategory" required></select></label>
          <label>库存模式<select id="editMode"><option value="0">普通库存</option><option value="1">无限库存</option></select></label>
          <label>加入奖品池<select id="editLotteryEnabled"><option value="0">否</option><option value="1">是</option></select></label>
          <label>获奖等级<input id="editLotteryLevel" maxlength="64" placeholder="例如 一等奖"></label>
          <label>该奖项中奖人数<input id="editLotteryWinnersCount" inputmode="numeric" min="1"></label>
          <div class="wide muted">Stars 只用于充值内部余额；商品购买扣 __BALANCE_CURRENCY__。积分兑换价是签到积分通道。奖品池字段只在抽奖开奖时生效。</div>
          <label class="wide">说明<textarea id="editDescription"></textarea></label>
          <label class="wide">切换库存内容<textarea id="editStock" placeholder="切换库存模式时填写；支持 JSON"></textarea></label>
          <div class="wide file-row">
            <input id="editJsonFile" type="file" accept=".json,application/json" multiple>
            <span class="muted">可多选 JSON 文件，选择后会覆盖上方库存内容。</span>
          </div>
        </div>
      </div>
      <div class="modal-foot">
        <button value="cancel">取消</button>
        <button id="saveEditBtn" class="primary" value="default">保存</button>
      </div>
    </form>
  </dialog>

  <dialog id="stockDialog">
    <form method="dialog">
      <div class="modal-head"><h2 id="stockTitle" style="margin:0">库存</h2><button value="cancel">关闭</button></div>
      <div class="modal-body">
        <input type="hidden" id="stockProductId">
        <div id="stockList" class="stock-list"></div>
        <label>追加库存<textarea id="stockValues" placeholder="每行一条，或粘贴 JSON 数组/对象"></textarea></label>
        <div class="file-row">
          <input id="stockJsonFile" type="file" accept=".json,application/json" multiple>
          <span class="muted">可多选 JSON 文件，JSON 数组会一次追加多条。</span>
        </div>
      </div>
      <div class="modal-foot">
        <button value="cancel">取消</button>
        <button id="addStockBtn" class="blue" value="default">追加</button>
      </div>
    </form>
  </dialog>

  <script>
    const state = { categories: [], products: [], promos: [], promoStats: {} };
    const $ = (id) => document.getElementById(id);

    function setStatus(text, kind = "") {
      const el = $("status");
      el.textContent = text || "";
      el.className = kind;
    }

    async function api(path, options = {}) {
      const response = await fetch(path, {
        headers: { "Content-Type": "application/json", ...(options.headers || {}) },
        credentials: "same-origin",
        ...options
      });
      const data = await response.json().catch(() => ({}));
      if (response.status === 401) {
        window.location.href = "/admin/login";
        throw new Error("未登录");
      }
      if (!response.ok || data.ok === false) {
        throw new Error(data.error || "请求失败");
      }
      return data;
    }

    function optionLists() {
      const selects = [document.querySelector("#productForm select[name=category_id]"), $("editCategory")];
      for (const select of selects) {
        select.textContent = "";
        for (const category of state.categories) {
          select.append(new Option(category.name, category.id));
        }
      }

      const promoCategory = $("promoCategory");
      const currentPromoCategory = promoCategory.value;
      promoCategory.textContent = "";
      promoCategory.append(new Option("不绑定分类", ""));
      for (const category of state.categories) {
        promoCategory.append(new Option(category.name, category.id));
      }
      promoCategory.value = currentPromoCategory;

      const promoProduct = $("promoProduct");
      const currentPromoProduct = promoProduct.value;
      promoProduct.textContent = "";
      promoProduct.append(new Option("不绑定商品", ""));
      for (const product of state.products) {
        promoProduct.append(new Option(`${product.name}（${product.category_name}）`, product.id));
      }
      promoProduct.value = currentPromoProduct;

      const filter = $("categoryFilter");
      const selected = filter.value;
      filter.textContent = "";
      filter.append(new Option("全部分类", ""));
      for (const category of state.categories) {
        filter.append(new Option(category.name, category.id));
      }
      filter.value = selected;
    }

    function renderCategories() {
      const list = $("categoryList");
      list.textContent = "";
      for (const category of state.categories) {
        const item = document.createElement("div");
        item.className = "category-item";

        const title = document.createElement("div");
        const name = document.createElement("div");
        name.className = "name";
        name.textContent = category.name;
        const count = document.createElement("div");
        count.className = "muted";
        count.textContent = `${category.products_count || 0} 个商品位`;
        title.append(name, count);

        const actions = document.createElement("div");
        actions.className = "actions";
        const rename = document.createElement("button");
        rename.type = "button";
        rename.textContent = "重命名";
        rename.onclick = () => renameCategory(category);
        const del = document.createElement("button");
        del.type = "button";
        del.className = "danger";
        del.textContent = "删除";
        del.onclick = () => deleteCategory(category);
        actions.append(rename, del);

        item.append(title, actions);
        list.append(item);
      }
    }

    function productMatches(product) {
      const q = $("searchInput").value.trim().toLowerCase();
      const cat = $("categoryFilter").value;
      if (cat && String(product.category_id) !== cat) return false;
      if (!q) return true;
      return [product.name, product.category_name, product.description].some(v => String(v || "").toLowerCase().includes(q));
    }

    function renderProducts() {
      const body = $("productRows");
      body.textContent = "";
      const products = state.products.filter(productMatches);
      if (!products.length) {
        const tr = document.createElement("tr");
        const td = document.createElement("td");
        td.colSpan = 8;
        td.className = "empty";
        td.textContent = state.products.length
          ? "没有符合筛选条件的商品位。"
          : "还没有商品位。选择 JSON 文件只会导入库存内容，还需要填写名称、价格、分类并点击创建商品位才会上架。";
        tr.append(td);
        body.append(tr);
        return;
      }
      for (const product of products) {
        const tr = document.createElement("tr");
        const name = document.createElement("td");
        const nameStrong = document.createElement("div");
        nameStrong.className = "name";
        nameStrong.textContent = product.name;
        const idLine = document.createElement("div");
        idLine.className = "muted";
        idLine.textContent = `#${product.id}`;
        name.append(nameStrong, idLine);

        const category = document.createElement("td");
        category.textContent = product.category_name;

        const desc = document.createElement("td");
        desc.textContent = product.description || "";

        const price = document.createElement("td");
        price.textContent = product.price;

        const points = document.createElement("td");
        points.textContent = product.points_price > 0
          ? `${product.points_price} 积分 / 最多 ${product.points_max_per_redeem || 1}`
          : "不可兑换";

        const lottery = document.createElement("td");
        lottery.textContent = product.lottery_enabled
          ? `${product.lottery_level || "奖品"} × ${product.lottery_winners_count || 1}`
          : "未加入";

        const stock = document.createElement("td");
        const badge = document.createElement("span");
        badge.className = `badge ${product.is_infinity ? "warn" : (product.stock_count > 0 ? "ok" : "")}`;
        badge.textContent = product.is_infinity ? "无限" : `${product.stock_count} 条`;
        stock.append(badge);

        const actions = document.createElement("td");
        const actionBox = document.createElement("div");
        actionBox.className = "actions";
        const edit = document.createElement("button");
        edit.type = "button";
        edit.textContent = "编辑";
        edit.onclick = () => openEdit(product);
        const stockBtn = document.createElement("button");
        stockBtn.type = "button";
        stockBtn.textContent = "库存";
        stockBtn.onclick = () => openStock(product);
        const del = document.createElement("button");
        del.type = "button";
        del.className = "danger";
        del.textContent = "删除";
        del.onclick = () => deleteProduct(product);
        actionBox.append(edit, stockBtn, del);
        actions.append(actionBox);

        tr.append(name, category, desc, price, points, lottery, stock, actions);
        body.append(tr);
      }
    }

    function formatPromoDate(value) {
      if (!value) return "不过期";
      const date = new Date(value);
      if (Number.isNaN(date.getTime())) return value;
      return date.toLocaleString();
    }

    function promoBindingText(promo) {
      if (promo.discount_type === "balance") return "不绑定";
      if (promo.item_name) return `商品：${promo.item_name}`;
      if (promo.category_name) return `分类：${promo.category_name}`;
      return "全店";
    }

    function renderPromos() {
      const body = $("promoRows");
      body.textContent = "";
      if (!state.promos.length) {
        const tr = document.createElement("tr");
        const td = document.createElement("td");
        td.colSpan = 8;
        td.className = "empty";
        td.textContent = "暂无兑换码。可以在上方直接创建余额兑换码或商品折扣码。";
        tr.append(td);
        body.append(tr);
        return;
      }
      for (const promo of state.promos) {
        const tr = document.createElement("tr");

        const code = document.createElement("td");
        const codeStrong = document.createElement("div");
        codeStrong.className = "name";
        codeStrong.textContent = promo.code;
        const idLine = document.createElement("div");
        idLine.className = "muted";
        idLine.textContent = `#${promo.id}`;
        code.append(codeStrong, idLine);

        const type = document.createElement("td");
        type.textContent = promo.discount_type_label || promo.discount_type;

        const value = document.createElement("td");
        value.textContent = promo.discount_type === "percent"
          ? `${promo.discount_value}%`
          : promo.discount_value;

        const uses = document.createElement("td");
        uses.textContent = `${promo.current_uses || 0}/${promo.max_uses || "不限"}`;

        const binding = document.createElement("td");
        binding.textContent = promoBindingText(promo);

        const expires = document.createElement("td");
        expires.textContent = formatPromoDate(promo.expires_at);

        const active = document.createElement("td");
        const badge = document.createElement("span");
        badge.className = `badge ${promo.is_active ? "ok" : ""}`;
        badge.textContent = promo.is_active ? "启用" : "停用";
        active.append(badge);

        const actions = document.createElement("td");
        const actionBox = document.createElement("div");
        actionBox.className = "actions";
        const toggle = document.createElement("button");
        toggle.type = "button";
        toggle.textContent = promo.is_active ? "停用" : "启用";
        toggle.onclick = () => togglePromo(promo);
        const del = document.createElement("button");
        del.type = "button";
        del.className = "danger";
        del.textContent = "删除";
        del.onclick = () => deletePromo(promo);
        actionBox.append(toggle, del);
        actions.append(actionBox);

        tr.append(code, type, value, uses, binding, expires, active, actions);
        body.append(tr);
      }
    }

    function renderAll() {
      $("mCategories").textContent = state.stats.categories;
      $("mProducts").textContent = state.stats.products;
      $("mStock").textContent = state.stats.stock_values;
      $("mInfinite").textContent = state.stats.infinite_products;
      $("mPromos").textContent = state.promoStats.promos || 0;
      optionLists();
      renderCategories();
      renderProducts();
      renderPromos();
      updatePromoFormState();
    }

    async function loadCatalog() {
      setStatus("正在刷新...");
      const [catalogData, promoData] = await Promise.all([
        api("/admin/api/catalog"),
        api("/admin/api/promos")
      ]);
      Object.assign(state, catalogData.catalog);
      state.promos = promoData.promos.promos;
      state.promoStats = promoData.promos.stats;
      renderAll();
      setStatus("已同步", "ok");
    }

    const JSON_STOCK_KEYS = ["items", "stock", "values", "data"];

    function isJsonFile(file) {
      return file.name.toLowerCase().endsWith(".json") || file.type === "application/json";
    }

    function jsonStockItemsFromValue(value) {
      if (Array.isArray(value)) return value;
      if (value && typeof value === "object") {
        for (const key of JSON_STOCK_KEYS) {
          if (Array.isArray(value[key])) return value[key];
        }
        return [value];
      }
      return [value];
    }

    function jsonImportStatus(files, count) {
      if (files.length === 1) {
        return `已导入 ${files[0].name}，共 ${count} 条库存`;
      }
      return `已导入 ${files.length} 个 JSON 文件，共 ${count} 条库存`;
    }

    function bindJsonFileInput(inputId, textareaGetter, afterImportHint = "") {
      const input = $(inputId);
      input.onchange = async () => {
        const files = Array.from(input.files || []);
        if (!files.length) return;
        const importedValues = [];
        let singleFileText = "";
        try {
          for (const file of files) {
            if (!isJsonFile(file)) {
              throw new Error(`${file.name} 不是 .json 文件。`);
            }
            const text = await file.text();
            let parsed;
            try {
              parsed = JSON.parse(text);
            } catch (err) {
              throw new Error(`${file.name} JSON 格式无效。`);
            }
            if (files.length === 1) singleFileText = text.trim();
            importedValues.push(...jsonStockItemsFromValue(parsed));
          }
          textareaGetter().value = files.length === 1
            ? singleFileText
            : JSON.stringify(importedValues, null, 2);
          setStatus(`${jsonImportStatus(files, importedValues.length)}${afterImportHint}`, "ok");
        } catch (err) {
          setStatus(err.message || "JSON 文件格式无效。", "error");
        } finally {
          input.value = "";
        }
      };
    }

    async function renameCategory(category) {
      const name = prompt("分类名称", category.name);
      if (!name || name.trim() === category.name) return;
      await api(`/admin/api/categories/${category.id}`, {
        method: "PUT",
        body: JSON.stringify({ name })
      });
      await loadCatalog();
    }

    async function deleteCategory(category) {
      if (!confirm(`删除分类“${category.name}”？分类下商品位会一起删除。`)) return;
      await api(`/admin/api/categories/${category.id}`, { method: "DELETE" });
      await loadCatalog();
    }

    async function deleteProduct(product) {
      if (!confirm(`删除商品位“${product.name}”？`)) return;
      await api(`/admin/api/products/${product.id}`, { method: "DELETE" });
      await loadCatalog();
    }

    async function togglePromo(promo) {
      await api(`/admin/api/promos/${promo.id}/toggle`, { method: "POST" });
      await loadCatalog();
    }

    async function deletePromo(promo) {
      if (!confirm(`删除兑换码“${promo.code}”？`)) return;
      await api(`/admin/api/promos/${promo.id}`, { method: "DELETE" });
      await loadCatalog();
    }

    function updatePromoFormState() {
      const type = $("promoType").value;
      const isBalance = type === "balance";
      $("promoCategory").disabled = isBalance;
      $("promoProduct").disabled = isBalance;
      if (isBalance) {
        $("promoCategory").value = "";
        $("promoProduct").value = "";
        $("promoHint").textContent = "余额兑换码不绑定商品或分类；创建后用户可在机器人首页兑换。";
      } else {
        $("promoHint").textContent = "商品折扣码可不绑定，也可绑定分类或单个商品；如果同时选择商品和分类，优先生效商品绑定。";
      }
    }

    function openEdit(product) {
      $("editId").value = product.id;
      $("editName").value = product.name;
      $("editPrice").value = product.price;
      $("editPointsPrice").value = product.points_price || 0;
      $("editPointsMaxPerRedeem").value = product.points_max_per_redeem || 1;
      $("editCategory").value = product.category_id;
      $("editLotteryEnabled").value = product.lottery_enabled ? "1" : "0";
      $("editLotteryLevel").value = product.lottery_level || "";
      $("editLotteryWinnersCount").value = product.lottery_winners_count || 1;
      $("editDescription").value = product.description || "";
      $("editMode").value = product.is_infinity ? "1" : "0";
      $("editStock").value = "";
      $("editDialog").showModal();
    }

    async function openStock(product) {
      $("stockProductId").value = product.id;
      $("stockTitle").textContent = `库存 - ${product.name}`;
      $("stockValues").value = "";
      $("addStockBtn").disabled = product.is_infinity;
      const data = await api(`/admin/api/products/${product.id}/stock?limit=50`);
      renderStockList(data.stock);
      if (!$("stockDialog").open) $("stockDialog").showModal();
    }

    function renderStockList(stock) {
      const list = $("stockList");
      list.textContent = "";
      if (!stock.items.length) {
        const empty = document.createElement("div");
        empty.className = "muted";
        empty.textContent = "暂无库存";
        list.append(empty);
        return;
      }
      for (const item of stock.items) {
        const row = document.createElement("div");
        row.className = "stock-row";
        const id = document.createElement("span");
        id.className = "muted";
        id.textContent = `#${item.id}`;
        const masked = document.createElement("span");
        masked.textContent = item.value_masked;
        const len = document.createElement("span");
        len.className = "muted len";
        len.textContent = `${item.length} 字符`;
        const del = document.createElement("button");
        del.type = "button";
        del.className = "danger";
        del.textContent = "删除";
        del.onclick = async () => {
          if (!confirm(`删除库存 #${item.id}？`)) return;
          await api(`/admin/api/stock/${item.id}`, { method: "DELETE" });
          await openStock({ id: stock.product.id, name: stock.product.name, is_infinity: false });
          await loadCatalog();
        };
        row.append(id, masked, len, del);
        list.append(row);
      }
    }

    $("refreshBtn").onclick = () => loadCatalog().catch(err => setStatus(err.message, "error"));
    $("searchInput").oninput = renderProducts;
    $("categoryFilter").onchange = renderProducts;
    $("promoType").onchange = updatePromoFormState;
    bindJsonFileInput(
      "productJsonFile",
      () => document.querySelector("#productForm textarea[name=stock_values]"),
      "；请填写名称、价格、分类并点击创建商品位。"
    );
    bindJsonFileInput("editJsonFile", () => $("editStock"));
    bindJsonFileInput("stockJsonFile", () => $("stockValues"));

    $("categoryForm").onsubmit = async (event) => {
      event.preventDefault();
      const target = event.currentTarget;
      const form = new FormData(target);
      try {
        await api("/admin/api/categories", { method: "POST", body: JSON.stringify({ name: form.get("name") }) });
        target.reset();
        await loadCatalog();
      } catch (err) { setStatus(err.message, "error"); }
    };

    $("productForm").onsubmit = async (event) => {
      event.preventDefault();
      const target = event.currentTarget;
      const form = new FormData(target);
      const payload = {
        name: form.get("name"),
        price: form.get("price"),
        points_price: form.get("points_price"),
        points_max_per_redeem: form.get("points_max_per_redeem"),
        lottery_enabled: form.get("lottery_enabled") === "1",
        lottery_level: form.get("lottery_level"),
        lottery_winners_count: form.get("lottery_winners_count"),
        category_id: form.get("category_id"),
        description: form.get("description"),
        is_infinity: form.get("is_infinity") === "1",
        stock_values: form.get("stock_values")
      };
      try {
        await api("/admin/api/products", { method: "POST", body: JSON.stringify(payload) });
        target.reset();
        await loadCatalog();
      } catch (err) { setStatus(err.message, "error"); }
    };

    $("promoForm").onsubmit = async (event) => {
      event.preventDefault();
      const target = event.currentTarget;
      const form = new FormData(target);
      const payload = {
        code: form.get("code"),
        discount_type: form.get("discount_type"),
        discount_value: form.get("discount_value"),
        max_uses: form.get("max_uses"),
        expires_at: form.get("expires_at"),
        is_active: form.get("is_active") === "1",
        category_id: form.get("category_id"),
        item_id: form.get("item_id")
      };
      try {
        await api("/admin/api/promos", { method: "POST", body: JSON.stringify(payload) });
        target.reset();
        await loadCatalog();
      } catch (err) { setStatus(err.message, "error"); }
    };

    $("saveEditBtn").onclick = async (event) => {
      event.preventDefault();
      const id = $("editId").value;
      const payload = {
        name: $("editName").value,
        price: $("editPrice").value,
        points_price: $("editPointsPrice").value,
        points_max_per_redeem: $("editPointsMaxPerRedeem").value,
        lottery_enabled: $("editLotteryEnabled").value === "1",
        lottery_level: $("editLotteryLevel").value,
        lottery_winners_count: $("editLotteryWinnersCount").value,
        category_id: $("editCategory").value,
        description: $("editDescription").value,
        is_infinity: $("editMode").value === "1",
        stock_values: $("editStock").value
      };
      try {
        await api(`/admin/api/products/${id}`, { method: "PUT", body: JSON.stringify(payload) });
        $("editDialog").close();
        await loadCatalog();
      } catch (err) { setStatus(err.message, "error"); }
    };

    $("addStockBtn").onclick = async (event) => {
      event.preventDefault();
      const id = $("stockProductId").value;
      try {
        await api(`/admin/api/products/${id}/stock`, {
          method: "POST",
          body: JSON.stringify({ stock_values: $("stockValues").value })
        });
        $("stockValues").value = "";
        const product = state.products.find(p => String(p.id) === String(id));
        await openStock(product);
        await loadCatalog();
      } catch (err) { setStatus(err.message, "error"); }
    };

    loadCatalog().catch(err => setStatus(err.message, "error"));
  </script>
</body>
</html>"""
