import logging
import time
from typing import Any

from sqladmin import Admin, ModelView, BaseView, expose
from sqladmin.authentication import AuthenticationBackend
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.middleware.sessions import SessionMiddleware
from starlette.routing import Route
from sqlalchemy import text

from markupsafe import Markup

from bot.misc import EnvKeys
from bot.database.methods.audit import log_audit
from bot.web.admin_i18n import (
    AdminLocaleMiddleware,
    admin_bool,
    admin_set_font_size_url,
    admin_set_language_url,
    admin_t,
    get_admin_font_size,
    get_admin_locale,
    set_admin_font_size,
    set_admin_language,
)

logger = logging.getLogger(__name__)


class LoginRateLimiter:
    """In-memory rate limiter for login attempts by IP."""

    def __init__(self, max_attempts: int = 5, lockout_seconds: int = 900):
        self.max_attempts = max_attempts
        self.lockout_seconds = lockout_seconds
        self._attempts: dict[str, list[float]] = {}
        self._last_cleanup: float = time.time()

    def is_blocked(self, ip: str) -> bool:
        if ip not in self._attempts:
            return False
        now = time.time()
        self._attempts[ip] = [t for t in self._attempts[ip] if now - t < self.lockout_seconds]
        return len(self._attempts[ip]) >= self.max_attempts

    def record_failure(self, ip: str) -> None:
        now = time.time()
        if now - self._last_cleanup > 600:
            self._attempts = {
                k: [t for t in v if now - t < self.lockout_seconds]
                for k, v in self._attempts.items()
                if any(now - t < self.lockout_seconds for t in v)
            }
            self._last_cleanup = now
        if ip not in self._attempts:
            self._attempts[ip] = []
        self._attempts[ip].append(now)

    def reset(self, ip: str) -> None:
        self._attempts.pop(ip, None)


_login_limiter = LoginRateLimiter()
from bot.database.main import Database
from bot.database.models.main import (
    User, Role, BoughtGoods, Operations, Payments, ReferralEarnings,
    AuditLog, CartItems, Reviews,
    CheckIns, LotteryEvents, LotteryEntries, LotteryWinners,
    BotSettings,
)
from bot.misc.metrics import get_metrics
from bot.misc.caching import get_cache_manager


# Authentication
class AdminAuth(AuthenticationBackend):
    async def login(self, request: Request) -> bool:
        ip = request.client.host

        if _login_limiter.is_blocked(ip):
            await log_audit("web_login_blocked", level="WARNING", details=f"ip={ip}", ip_address=ip)
            return False

        form = await request.form()
        username = form.get("username")
        password = form.get("password")

        if username == EnvKeys.ADMIN_USERNAME and password == EnvKeys.ADMIN_PASSWORD:
            if (
                username == "admin" and password == "admin"
                and ip not in ("127.0.0.1", "::1", "localhost")
            ):
                await log_audit("web_login_blocked_default_creds", level="WARNING", details=f"ip={ip}", ip_address=ip)
                return False
            request.session.update({"authenticated": True})
            _login_limiter.reset(ip)
            await log_audit("web_login", user_id=None, details=f"user={username}", ip_address=ip)
            return True

        _login_limiter.record_failure(ip)
        await log_audit("web_login_failed", level="WARNING", details=f"user={username}", ip_address=ip)
        return False

    async def logout(self, request: Request) -> bool:
        await log_audit("web_logout", ip_address=request.client.host)
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> bool:
        return request.session.get("authenticated", False)


def _safe_model_repr(model: Any, max_len: int = 500) -> str:
    """Return a truncated repr that excludes sensitive fields."""
    _sensitive = {"balance", "password", "secret", "token", "value"}
    parts = []
    for col in getattr(model, "__table__", None).columns if hasattr(model, "__table__") else ():
        if col.name in _sensitive:
            continue
        val = getattr(model, col.name, None)
        parts.append(f"{col.name}={val!r}")
    result = f"{type(model).__name__}({', '.join(parts)})"
    return result[:max_len]


# Audited base view for mutable models
class AuditModelView(ModelView):
    async def after_model_change(self, data: dict, model: Any, is_created: bool, request: Request) -> None:
        action = f"sqladmin_{'create' if is_created else 'update'}"
        await log_audit(
            action,
            resource_type=type(self).name,
            resource_id=str(getattr(model, 'id', getattr(model, 'name', None))),
            details=_safe_model_repr(model),
            ip_address=request.client.host,
        )

    async def after_model_delete(self, model: Any, request: Request) -> None:
        await log_audit(
            "sqladmin_delete",
            resource_type=type(self).name,
            resource_id=str(getattr(model, 'id', getattr(model, 'name', None))),
            details=_safe_model_repr(model),
            ip_address=request.client.host,
        )


class LocalizedModelView(ModelView):
    name_key = ""
    name_plural_key = ""
    column_label_keys: dict[Any, str] = {}

    def __init__(self) -> None:
        super().__init__()
        self._base_column_labels = dict(self._column_labels)

    def __getattribute__(self, name: str):
        if name == "name":
            key = object.__getattribute__(self, "name_key")
            if key:
                return admin_t(key)
        if name == "name_plural":
            key = object.__getattribute__(self, "name_plural_key")
            if key:
                return admin_t(key)
        return super().__getattribute__(name)

    @property
    def _localized_column_labels(self) -> dict[str, str]:
        labels = dict(getattr(self, "_base_column_labels", {}))
        for column, key in self.column_label_keys.items():
            labels[self._get_prop_name(column)] = admin_t(key)
        return labels

    def column_label(self, name: str) -> str:
        return self._localized_column_labels.get(name, name)

    def search_placeholder(self) -> str:
        labels = self._localized_column_labels
        return ", ".join(labels.get(field, field) for field in self._search_fields)

    async def scaffold_form(self, rules=None):
        old_labels = self._column_labels
        old_form_args = self.form_args
        self._column_labels = self._localized_column_labels
        self.form_args = _localized_form_args(old_form_args)
        try:
            return await super().scaffold_form(rules)
        finally:
            self._column_labels = old_labels
            self.form_args = old_form_args


class LocalizedAuditModelView(LocalizedModelView, AuditModelView):
    pass


def _localized_form_args(form_args: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for name, args in form_args.items():
        next_args = dict(args)
        desc_key = next_args.pop("description_key", None)
        if desc_key:
            next_args["description"] = admin_t(desc_key)
        result[name] = next_args
    return result


def _format_bool_html(model, name):
    return admin_bool(getattr(model, name, None))


COMMON_LABEL_KEYS = {
    "id": "admin_web.field.id",
    "telegram_id": "admin_web.field.telegram_id",
    "balance": "admin_web.field.balance",
    "points_balance": "admin_web.field.points_balance",
    "locale": "admin_web.field.locale",
    "role_id": "admin_web.field.role_id",
    "referral_id": "admin_web.field.referral_id",
    "registration_date": "admin_web.field.registration_date",
    "is_blocked": "admin_web.field.is_blocked",
    "name": "admin_web.field.name",
    "default": "admin_web.field.default",
    "permissions": "admin_web.field.permissions",
    "price": "admin_web.field.price",
    "points_price": "admin_web.field.points_price",
    "points_max_per_redeem": "admin_web.field.points_max_per_redeem",
    "lottery_enabled": "admin_web.field.lottery_enabled",
    "lottery_level": "admin_web.field.lottery_level",
    "lottery_winners_count": "admin_web.field.lottery_winners_count",
    "description": "admin_web.field.description",
    "category_id": "admin_web.field.category_id",
    "item_id": "admin_web.field.item_id",
    "value": "admin_web.field.value",
    "is_infinity": "admin_web.field.is_infinity",
    "item_name": "admin_web.field.item_name",
    "buyer_id": "admin_web.field.buyer_id",
    "bought_datetime": "admin_web.field.bought_datetime",
    "unique_id": "admin_web.field.unique_id",
    "user_id": "admin_web.field.user_id",
    "operation_value": "admin_web.field.operation_value",
    "operation_time": "admin_web.field.operation_time",
    "provider": "admin_web.field.provider",
    "external_id": "admin_web.field.external_id",
    "amount": "admin_web.field.amount",
    "currency": "admin_web.field.currency",
    "status": "admin_web.field.status",
    "created_at": "admin_web.field.created_at",
    "updated_at": "admin_web.field.updated_at",
    "referrer_id": "admin_web.field.referrer_id",
    "original_amount": "admin_web.field.original_amount",
    "timestamp": "admin_web.field.timestamp",
    "level": "admin_web.field.level",
    "action": "admin_web.field.action",
    "resource_type": "admin_web.field.resource_type",
    "resource_id": "admin_web.field.resource_id",
    "details": "admin_web.field.details",
    "ip_address": "admin_web.field.ip_address",
    "code": "admin_web.field.code",
    "discount_type": "admin_web.field.discount_type",
    "discount_value": "admin_web.field.discount_value",
    "max_uses": "admin_web.field.max_uses",
    "current_uses": "admin_web.field.current_uses",
    "expires_at": "admin_web.field.expires_at",
    "is_active": "admin_web.field.is_active",
    "promo_code": "admin_web.field.promo_code",
    "added_at": "admin_web.field.added_at",
    "rating": "admin_web.field.rating",
    "text": "admin_web.field.text",
    "checkin_date": "admin_web.field.checkin_date",
    "reward_amount": "admin_web.field.reward_amount",
    "points_awarded": "admin_web.field.points_awarded",
    "tickets_awarded": "admin_web.field.tickets_awarded",
    "streak": "admin_web.field.streak",
    "title": "admin_web.field.title",
    "prize": "admin_web.field.prize",
    "winner_user_id": "admin_web.field.winner_user_id",
    "created_by": "admin_web.field.created_by",
    "draw_at": "admin_web.field.draw_at",
    "min_entries": "admin_web.field.min_entries",
    "min_users": "admin_web.field.min_users",
    "auto_draw_enabled": "admin_web.field.auto_draw_enabled",
    "ended_at": "admin_web.field.ended_at",
    "source": "admin_web.field.source",
    "event_id": "admin_web.field.event_id",
    "goods_id": "admin_web.field.goods_id",
    "goods_name": "admin_web.field.goods_name",
    "prize_level": "admin_web.field.prize_level",
    "ticket_count": "admin_web.field.ticket_count",
    "key": "admin_web.field.key",
    "value": "admin_web.field.value",
}


# Model Views
class UserAdmin(LocalizedAuditModelView, model=User):
    column_list = [User.telegram_id, User.balance, User.points_balance, User.role_id, User.referral_id,
                   User.registration_date, User.is_blocked]
    column_searchable_list = [User.telegram_id]
    column_sortable_list = [User.telegram_id, User.balance, User.points_balance, User.registration_date]
    column_default_sort = (User.registration_date, True)
    name_key = "admin_web.model.user"
    name_plural_key = "admin_web.model.users"
    column_label_keys = COMMON_LABEL_KEYS
    column_formatters = {"is_blocked": _format_bool_html}
    column_formatters_detail = {"is_blocked": _format_bool_html}
    icon = "fa-solid fa-users"


_PERM_FLAGS = [
    (1,   "USE"),
    (2,   "BROADCAST"),
    (4,   "SETTINGS"),
    (8,   "USERS"),
    (16,  "CATALOG"),
    (32,  "ADMINS"),
    (64,  "OWNER"),
    (128, "STATS"),
    (256, "BALANCE"),
    (512, "PROMOS"),
]


def _format_perms_html(model, name):
    perms = getattr(model, name, 0) or 0
    if not perms:
        return Markup('<span style="color:#999">\u2014</span>')
    badges = []
    for bit, label in _PERM_FLAGS:
        if perms & bit:
            badges.append(
                f'<span style="display:inline-block;background:#e2e8f0;padding:1px 6px;'
                f'border-radius:4px;margin:1px;font-size:12px">{label}</span>'
            )
    raw = f'<span style="color:#999;font-size:11px;margin-left:4px">({perms})</span>'
    return Markup(" ".join(badges) + raw)


class RoleAdmin(LocalizedAuditModelView, model=Role):
    column_list = [Role.id, Role.name, Role.default, Role.permissions]
    column_details_exclude_list = ["users"]
    column_sortable_list = [Role.id, Role.name]
    name_key = "admin_web.model.role"
    name_plural_key = "admin_web.model.roles"
    column_label_keys = COMMON_LABEL_KEYS
    icon = "fa-solid fa-shield-halved"
    column_formatters = {"permissions": _format_perms_html, "default": _format_bool_html}
    column_formatters_detail = {"permissions": _format_perms_html, "default": _format_bool_html}
    form_args = {
        "permissions": {
            "description_key": "admin_web.role.permissions.description",
        },
    }


class BoughtGoodsAdmin(LocalizedModelView, model=BoughtGoods):
    column_list = [BoughtGoods.id, BoughtGoods.item_name, BoughtGoods.value,
                   BoughtGoods.price, BoughtGoods.buyer_id, BoughtGoods.bought_datetime,
                   BoughtGoods.unique_id]
    column_searchable_list = [BoughtGoods.item_name, BoughtGoods.buyer_id, BoughtGoods.unique_id]
    column_sortable_list = [BoughtGoods.id, BoughtGoods.bought_datetime, BoughtGoods.price]
    column_default_sort = (BoughtGoods.id, True)
    can_create = False
    can_edit = False
    can_delete = False
    name_key = "admin_web.model.purchase"
    name_plural_key = "admin_web.model.purchases"
    column_label_keys = COMMON_LABEL_KEYS
    icon = "fa-solid fa-cart-shopping"


class OperationsAdmin(LocalizedModelView, model=Operations):
    column_list = [Operations.id, Operations.user_id, Operations.operation_value,
                   Operations.operation_time]
    column_searchable_list = [Operations.user_id]
    column_sortable_list = [Operations.id, Operations.operation_time, Operations.operation_value]
    column_default_sort = (Operations.id, True)
    can_create = False
    can_edit = False
    can_delete = False
    name_key = "admin_web.model.operation"
    name_plural_key = "admin_web.model.operations"
    column_label_keys = COMMON_LABEL_KEYS
    icon = "fa-solid fa-money-bill-transfer"


class PaymentsAdmin(LocalizedModelView, model=Payments):
    column_list = [Payments.id, Payments.provider, Payments.external_id, Payments.user_id,
                   Payments.amount, Payments.currency, Payments.status, Payments.created_at]
    column_searchable_list = [Payments.user_id, Payments.external_id, Payments.provider]
    column_sortable_list = [Payments.id, Payments.created_at, Payments.amount, Payments.status]
    column_default_sort = (Payments.id, True)
    can_create = False
    can_edit = False
    can_delete = False
    name_key = "admin_web.model.payment"
    name_plural_key = "admin_web.model.payments"
    column_label_keys = COMMON_LABEL_KEYS
    icon = "fa-solid fa-credit-card"


class ReferralEarningsAdmin(LocalizedModelView, model=ReferralEarnings):
    column_list = [ReferralEarnings.id, ReferralEarnings.referrer_id,
                   ReferralEarnings.referral_id, ReferralEarnings.amount,
                   ReferralEarnings.original_amount, ReferralEarnings.created_at]
    column_searchable_list = [ReferralEarnings.referrer_id, ReferralEarnings.referral_id]
    column_sortable_list = [ReferralEarnings.id, ReferralEarnings.created_at, ReferralEarnings.amount]
    column_default_sort = (ReferralEarnings.id, True)
    can_create = False
    can_edit = False
    can_delete = False
    name_key = "admin_web.model.referral_earning"
    name_plural_key = "admin_web.model.referral_earnings"
    column_label_keys = COMMON_LABEL_KEYS
    icon = "fa-solid fa-handshake"


class AuditLogAdmin(LocalizedModelView, model=AuditLog):
    column_list = [AuditLog.id, AuditLog.timestamp, AuditLog.level, AuditLog.user_id,
                   AuditLog.action, AuditLog.resource_type, AuditLog.resource_id,
                   AuditLog.details, AuditLog.ip_address]
    column_searchable_list = [AuditLog.action, AuditLog.resource_type, AuditLog.details]
    column_sortable_list = [AuditLog.id, AuditLog.timestamp, AuditLog.level, AuditLog.action]
    column_default_sort = (AuditLog.id, True)
    can_create = False
    can_edit = False
    can_delete = False
    name_key = "admin_web.model.audit_log"
    name_plural_key = "admin_web.model.audit_logs"
    column_label_keys = COMMON_LABEL_KEYS
    icon = "fa-solid fa-clipboard-list"


class CartItemsAdmin(LocalizedModelView, model=CartItems):
    column_list = [CartItems.id, CartItems.user_id, CartItems.item_name, CartItems.added_at]
    column_searchable_list = [CartItems.user_id, CartItems.item_name]
    column_sortable_list = [CartItems.id, CartItems.added_at]
    column_default_sort = (CartItems.id, True)
    can_create = False
    can_edit = False
    can_delete = False
    name_key = "admin_web.model.cart_item"
    name_plural_key = "admin_web.model.cart_items"
    column_label_keys = COMMON_LABEL_KEYS
    icon = "fa-solid fa-cart-plus"



class ReviewsAdmin(LocalizedAuditModelView, model=Reviews):
    column_list = [Reviews.id, Reviews.user_id, Reviews.item_name,
                   Reviews.rating, Reviews.text, Reviews.created_at]
    column_searchable_list = [Reviews.user_id, Reviews.item_name]
    column_sortable_list = [Reviews.id, Reviews.rating, Reviews.created_at]
    column_default_sort = (Reviews.id, True)
    name_key = "admin_web.model.review"
    name_plural_key = "admin_web.model.reviews"
    column_label_keys = COMMON_LABEL_KEYS
    icon = "fa-solid fa-star"


class CheckInsAdmin(LocalizedModelView, model=CheckIns):
    column_list = [
        CheckIns.id,
        CheckIns.user_id,
        CheckIns.checkin_date,
        CheckIns.points_awarded,
        CheckIns.tickets_awarded,
        CheckIns.streak,
        CheckIns.created_at,
    ]
    column_searchable_list = [CheckIns.user_id]
    column_sortable_list = [CheckIns.id, CheckIns.user_id, CheckIns.checkin_date, CheckIns.streak]
    column_default_sort = (CheckIns.id, True)
    can_create = False
    can_edit = False
    can_delete = False
    name_key = "admin_web.model.checkin"
    name_plural_key = "admin_web.model.checkins"
    column_label_keys = COMMON_LABEL_KEYS
    icon = "fa-solid fa-calendar-check"


class LotteryEventsAdmin(LocalizedAuditModelView, model=LotteryEvents):
    column_list = [
        LotteryEvents.id,
        LotteryEvents.title,
        LotteryEvents.status,
        LotteryEvents.draw_at,
        LotteryEvents.min_entries,
        LotteryEvents.min_users,
        LotteryEvents.auto_draw_enabled,
        LotteryEvents.created_by,
        LotteryEvents.winner_user_id,
        LotteryEvents.created_at,
        LotteryEvents.ended_at,
    ]
    column_searchable_list = [LotteryEvents.title, LotteryEvents.status]
    column_sortable_list = [LotteryEvents.id, LotteryEvents.status, LotteryEvents.draw_at, LotteryEvents.created_at]
    column_default_sort = (LotteryEvents.id, True)
    name_key = "admin_web.model.lottery_event"
    name_plural_key = "admin_web.model.lottery_events"
    column_label_keys = COMMON_LABEL_KEYS
    column_formatters = {"auto_draw_enabled": _format_bool_html}
    column_formatters_detail = {"auto_draw_enabled": _format_bool_html}
    form_args = {
        "status": {
            "description_key": "admin_web.lottery_event.status.description",
        },
        "draw_at": {
            "description_key": "admin_web.lottery_event.draw_at.description",
        },
        "min_entries": {
            "description_key": "admin_web.lottery_event.min_entries.description",
        },
        "min_users": {
            "description_key": "admin_web.lottery_event.min_users.description",
        },
    }
    icon = "fa-solid fa-gift"


class LotteryEntriesAdmin(LocalizedModelView, model=LotteryEntries):
    column_list = [
        LotteryEntries.id,
        LotteryEntries.event_id,
        LotteryEntries.user_id,
        LotteryEntries.source,
        LotteryEntries.created_at,
    ]
    column_searchable_list = [LotteryEntries.user_id, LotteryEntries.source]
    column_sortable_list = [LotteryEntries.id, LotteryEntries.event_id, LotteryEntries.user_id, LotteryEntries.created_at]
    column_default_sort = (LotteryEntries.id, True)
    can_create = False
    can_edit = False
    can_delete = False
    name_key = "admin_web.model.lottery_entry"
    name_plural_key = "admin_web.model.lottery_entries"
    column_label_keys = COMMON_LABEL_KEYS
    icon = "fa-solid fa-ticket"


class LotteryWinnersAdmin(LocalizedModelView, model=LotteryWinners):
    column_list = [
        LotteryWinners.id,
        LotteryWinners.event_id,
        LotteryWinners.user_id,
        LotteryWinners.goods_name,
        LotteryWinners.prize_level,
        LotteryWinners.ticket_count,
        LotteryWinners.created_at,
    ]
    column_searchable_list = [LotteryWinners.user_id, LotteryWinners.goods_name, LotteryWinners.prize_level]
    column_sortable_list = [LotteryWinners.id, LotteryWinners.event_id, LotteryWinners.created_at]
    column_default_sort = (LotteryWinners.id, True)
    can_create = False
    can_edit = False
    can_delete = False
    name_key = "admin_web.model.lottery_winner"
    name_plural_key = "admin_web.model.lottery_winners"
    column_label_keys = COMMON_LABEL_KEYS
    icon = "fa-solid fa-trophy"


class BotSettingsAdmin(LocalizedAuditModelView, model=BotSettings):
    column_list = [BotSettings.key, BotSettings.value, BotSettings.description, BotSettings.updated_at]
    column_searchable_list = [BotSettings.key, BotSettings.value, BotSettings.description]
    column_sortable_list = [BotSettings.key, BotSettings.updated_at]
    can_create = True
    can_edit = True
    can_delete = False
    name_key = "admin_web.model.bot_setting"
    name_plural_key = "admin_web.model.bot_settings"
    column_label_keys = COMMON_LABEL_KEYS
    form_args = {
        "value": {
            "description_key": "admin_web.bot_setting.value.description",
        },
    }
    icon = "fa-solid fa-sliders"


class OperationsAdminView(BaseView):
    name = "admin_web.operations"
    identity = "operations"
    icon = "fa-solid fa-store"

    @expose("/operations", methods=["GET"], identity="operations")
    async def operations(self, request: Request):
        return await self.templates.TemplateResponse(
            request,
            "sqladmin/operations.html",
            {
                "title": admin_t("admin_web.operations"),
                "subtitle": admin_t("admin_web.operations.subtitle"),
            },
        )


class PlatformReviewAdminView(BaseView):
    name = "admin_web.platform_review"
    identity = "platform_review"
    icon = "fa-solid fa-layer-group"

    @expose("/platform/review", methods=["GET"], identity="platform_review")
    async def platform_review(self, request: Request):
        return await self.templates.TemplateResponse(
            request,
            "sqladmin/platform_review.html",
            {
                "title": admin_t("admin_web.platform_review"),
                "subtitle": admin_t("admin_web.platform_review.subtitle"),
            },
        )


# Health & Metrics Endpoints
async def health_check(request: Request) -> JSONResponse:
    health_status = {
        "status": "healthy",
        "checks": {},
    }

    try:
        async with Database().session() as s:
            await s.execute(text("SELECT 1"))
        health_status["checks"]["database"] = "ok"
    except Exception as e:
        logger.error(f"Health check database error: {e}")
        health_status["checks"]["database"] = "error"
        health_status["status"] = "unhealthy"

    cache = get_cache_manager()
    if cache:
        health_status["checks"]["redis"] = "ok" if cache._healthy else "degraded"
    else:
        health_status["checks"]["redis"] = "not configured"

    metrics = get_metrics()
    if metrics:
        health_status["checks"]["metrics"] = "ok"
        health_status["uptime"] = metrics.get_metrics_summary()["uptime_seconds"]

    status_code = 200 if health_status["status"] == "healthy" else 503
    return JSONResponse(health_status, status_code=status_code)


async def prometheus_metrics(request: Request) -> PlainTextResponse:
    if not request.session.get("authenticated"):
        return PlainTextResponse("Unauthorized", status_code=401)
    metrics = get_metrics()
    if not metrics:
        return PlainTextResponse("# Metrics not initialized\n", status_code=503)
    return PlainTextResponse(metrics.export_to_prometheus(), media_type="text/plain")


async def metrics_json(request: Request) -> JSONResponse:
    if not request.session.get("authenticated"):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    metrics = get_metrics()
    if not metrics:
        return JSONResponse({"error": "Metrics not initialized"}, status_code=503)
    return JSONResponse(metrics.get_metrics_summary(), status_code=200)


# App Factory
def create_admin_app() -> Starlette:

    from bot.web.export import export_routes
    from bot.web.client import client_routes
    from bot.web.platform import platform_routes
    session_max_age = max(int(getattr(EnvKeys, "ADMIN_SESSION_MAX_AGE_DAYS", 30)), 1) * 24 * 60 * 60

    routes = [
        Route("/health", health_check),
        Route("/metrics", metrics_json),
        Route("/metrics/prometheus", prometheus_metrics),
        Route("/admin/lang", set_admin_language, name="admin_lang"),
        Route("/admin/font-size", set_admin_font_size, name="admin_font_size"),
    ] + export_routes + client_routes + platform_routes

    app = Starlette(routes=routes)
    app.add_middleware(SessionMiddleware, secret_key=EnvKeys.SECRET_KEY, max_age=session_max_age)

    auth_backend = AdminAuth(secret_key=EnvKeys.SECRET_KEY, max_age=session_max_age)
    admin = Admin(
        app,
        engine=Database().engine,
        authentication_backend=auth_backend,
        title=admin_t("admin_web.title"),
        templates_dir="templates",
        middlewares=[Middleware(AdminLocaleMiddleware)],
    )
    admin.templates.env.globals["admin_t"] = admin_t
    admin.templates.env.globals["admin_locale"] = get_admin_locale
    admin.templates.env.globals["admin_language_url"] = admin_set_language_url
    admin.templates.env.globals["admin_font_size"] = get_admin_font_size
    admin.templates.env.globals["admin_font_size_url"] = admin_set_font_size_url

    admin.add_view(OperationsAdminView)
    admin.add_view(PlatformReviewAdminView)
    admin.add_view(UserAdmin)
    admin.add_view(RoleAdmin)
    admin.add_view(BoughtGoodsAdmin)
    admin.add_view(OperationsAdmin)
    admin.add_view(PaymentsAdmin)
    admin.add_view(ReferralEarningsAdmin)
    admin.add_view(AuditLogAdmin)
    admin.add_view(CartItemsAdmin)
    admin.add_view(CheckInsAdmin)
    admin.add_view(LotteryEventsAdmin)
    admin.add_view(LotteryEntriesAdmin)
    admin.add_view(LotteryWinnersAdmin)
    admin.add_view(BotSettingsAdmin)
    if EnvKeys.REVIEWS_ENABLED == "1":
        admin.add_view(ReviewsAdmin)

    return app
