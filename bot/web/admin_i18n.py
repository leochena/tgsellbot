from __future__ import annotations

from contextvars import ContextVar, Token
from typing import Any
from urllib.parse import urlencode

from starlette.datastructures import URL
from starlette.requests import Request
from starlette.responses import RedirectResponse

ADMIN_DEFAULT_LOCALE = "zh"
ADMIN_SUPPORTED_LOCALES = ("zh", "en")
ADMIN_DEFAULT_FONT_SIZE = 12
ADMIN_SUPPORTED_FONT_SIZES = (12, 14, 16, 18)

_current_admin_locale: ContextVar[str] = ContextVar(
    "current_admin_locale",
    default=ADMIN_DEFAULT_LOCALE,
)
_current_admin_font_size: ContextVar[int] = ContextVar(
    "current_admin_font_size",
    default=ADMIN_DEFAULT_FONT_SIZE,
)


ADMIN_TRANSLATIONS: dict[str, dict[str, str]] = {
    "en": {
        "admin_web.title": "Telegram Shop Admin",
        "admin_web.login.title": "Login to {title}",
        "admin_web.login.username": "Username",
        "admin_web.login.username_placeholder": "Enter username",
        "admin_web.login.password": "Password",
        "admin_web.login.password_placeholder": "Password",
        "admin_web.login.remember": "Remember login on this computer",
        "admin_web.login.remember_hint": "The admin session is kept in this browser for the configured session lifetime.",
        "admin_web.login.submit": "Login",
        "admin_web.login.invalid_credentials": "Invalid credentials.",
        "admin_web.logout": "Logout",
        "admin_web.language": "Language",
        "admin_web.language.zh": "中文",
        "admin_web.language.en": "English",
        "admin_web.font_size": "Font size",
        "admin_web.font_size.option": "{size}pt",
        "admin_web.operations": "Product Operations",
        "admin_web.operations.subtitle": "Manage categories, products, stock, JSON delivery files and promo codes in one place.",
        "admin_web.platform_review": "Platform Review",
        "admin_web.platform_review.subtitle": "Review channel submissions, channel reports, ownership claims, relay providers, relay claims, and relay feedback.",
        "admin_web.actions": "Actions",
        "admin_web.export": "Export",
        "admin_web.new": "New {name}",
        "admin_web.create_title": "New {name}",
        "admin_web.edit_title": "Edit {name}",
        "admin_web.delete_selected": "Delete selected items",
        "admin_web.search_placeholder": "Search: {fields}",
        "admin_web.search": "Search",
        "admin_web.view": "View",
        "admin_web.edit": "Edit",
        "admin_web.delete": "Delete",
        "admin_web.showing": "Showing",
        "admin_web.to": "to",
        "admin_web.of": "of",
        "admin_web.items": "items",
        "admin_web.prev": "prev",
        "admin_web.next": "next",
        "admin_web.show": "Show",
        "admin_web.page": "Page",
        "admin_web.filters": "Filters",
        "admin_web.cancel": "Cancel",
        "admin_web.yes": "Yes",
        "admin_web.no": "No",
        "admin_web.save": "Save",
        "admin_web.save_continue": "Save and continue editing",
        "admin_web.save_add_another": "Save and add another",
        "admin_web.save_as_new": "Save as new",
        "admin_web.column": "Column",
        "admin_web.value": "Value",
        "admin_web.go_back": "Go Back",
        "admin_web.confirm": "Please confirm",
        "admin_web.close": "Close",
        "admin_web.toggle_navigation": "Toggle navigation",
        "admin_web.select_all": "Select all",
        "admin_web.select_item": "Select item",
        "admin_web.required_field": "This is a required field",
        "admin_web.delete_confirm": "This will permanently delete {name} {pk}?",
        "admin_web.clear_filter": "Clear filter",
        "admin_web.current": "Current",
        "admin_web.clear": "Clear",
        "admin_web.select_operation": "Select operation...",
        "admin_web.enter_value": "Enter value",
        "admin_web.apply_filter": "Apply Filter",
        "admin_web.copy": "Copy",
        "admin_web.done": "Done",
        "admin_web.bool.true": "Yes",
        "admin_web.bool.false": "No",
        "admin_web.empty": "-",
        "admin_web.role.permissions.description": (
            "Bitmask value - sum the flags you need: USE=1, BROADCAST=2, "
            "SETTINGS=4, USERS=8, CATALOG=16, ADMINS=32, OWNER=64, "
            "STATS=128, BALANCE=256, PROMOS=512. Example: 927 = full Admin, "
            "1023 = all (Owner)."
        ),
        "admin_web.model.user": "User",
        "admin_web.model.users": "Users",
        "admin_web.model.role": "Role",
        "admin_web.model.roles": "Roles",
        "admin_web.model.category": "Category",
        "admin_web.model.categories": "Categories",
        "admin_web.model.product": "Product",
        "admin_web.model.products": "Products",
        "admin_web.model.stock_item": "Stock Item",
        "admin_web.model.stock_items": "Stock Items",
        "admin_web.model.purchase": "Purchase",
        "admin_web.model.purchases": "Purchases",
        "admin_web.model.operation": "Operation",
        "admin_web.model.operations": "Operations",
        "admin_web.model.payment": "Payment",
        "admin_web.model.payments": "Payments",
        "admin_web.model.referral_earning": "Referral Earning",
        "admin_web.model.referral_earnings": "Referral Earnings",
        "admin_web.model.audit_log": "Audit Log",
        "admin_web.model.audit_logs": "Audit Logs",
        "admin_web.model.promo_code": "Promo Code",
        "admin_web.model.promo_codes": "Promo Codes",
        "admin_web.model.cart_item": "Cart Item",
        "admin_web.model.cart_items": "Cart Items",
        "admin_web.model.review": "Review",
        "admin_web.model.reviews": "Reviews",
        "admin_web.model.checkin": "Check-in",
        "admin_web.model.checkins": "Check-ins",
        "admin_web.model.lottery_event": "Lottery Event",
        "admin_web.model.lottery_events": "Lottery Events",
        "admin_web.model.lottery_entry": "Lottery Entry",
        "admin_web.model.lottery_entries": "Lottery Entries",
        "admin_web.model.lottery_winner": "Lottery Winner",
        "admin_web.model.lottery_winners": "Lottery Winners",
        "admin_web.model.bot_setting": "Bot Setting",
        "admin_web.model.bot_settings": "Bot Settings",
        "admin_web.field.id": "ID",
        "admin_web.field.telegram_id": "Telegram ID",
        "admin_web.field.balance": "Internal Balance",
        "admin_web.field.points_balance": "Points",
        "admin_web.field.locale": "Locale",
        "admin_web.field.role_id": "Role ID",
        "admin_web.field.referral_id": "Referral ID",
        "admin_web.field.registration_date": "Registration Date",
        "admin_web.field.is_blocked": "Blocked",
        "admin_web.field.name": "Name",
        "admin_web.field.default": "Default",
        "admin_web.field.permissions": "Permissions",
        "admin_web.field.price": "Balance Price",
        "admin_web.field.points_price": "Points Redeem Price",
        "admin_web.field.points_max_per_redeem": "Max Points Redeem Qty",
        "admin_web.field.lottery_enabled": "In Prize Pool",
        "admin_web.field.lottery_level": "Prize Level",
        "admin_web.field.lottery_winners_count": "Prize Winners Count",
        "admin_web.field.description": "Description",
        "admin_web.field.category_id": "Category ID",
        "admin_web.field.item_id": "Product ID",
        "admin_web.field.value": "Value",
        "admin_web.field.is_infinity": "Infinite",
        "admin_web.field.item_name": "Product Name",
        "admin_web.field.buyer_id": "Buyer ID",
        "admin_web.field.bought_datetime": "Purchase Time",
        "admin_web.field.unique_id": "Unique ID",
        "admin_web.field.user_id": "User ID",
        "admin_web.field.operation_value": "Operation Value",
        "admin_web.field.operation_time": "Operation Time",
        "admin_web.field.provider": "Provider",
        "admin_web.field.external_id": "External ID",
        "admin_web.field.amount": "Amount",
        "admin_web.field.currency": "Currency",
        "admin_web.field.status": "Status",
        "admin_web.field.created_at": "Created At",
        "admin_web.field.updated_at": "Updated At",
        "admin_web.field.referrer_id": "Referrer ID",
        "admin_web.field.original_amount": "Original Amount",
        "admin_web.field.timestamp": "Timestamp",
        "admin_web.field.level": "Level",
        "admin_web.field.action": "Action",
        "admin_web.field.resource_type": "Resource Type",
        "admin_web.field.resource_id": "Resource ID",
        "admin_web.field.details": "Details",
        "admin_web.field.ip_address": "IP Address",
        "admin_web.field.code": "Code",
        "admin_web.field.discount_type": "Discount Type",
        "admin_web.field.discount_value": "Discount Value",
        "admin_web.field.max_uses": "Max Uses",
        "admin_web.field.current_uses": "Current Uses",
        "admin_web.field.expires_at": "Expires At",
        "admin_web.field.is_active": "Active",
        "admin_web.field.promo_code": "Promo Code",
        "admin_web.field.added_at": "Added At",
        "admin_web.field.rating": "Rating",
        "admin_web.field.text": "Text",
        "admin_web.field.checkin_date": "Check-in Date",
        "admin_web.field.reward_amount": "Legacy Reward",
        "admin_web.field.points_awarded": "Points Awarded",
        "admin_web.field.tickets_awarded": "Tickets Awarded",
        "admin_web.field.streak": "Streak",
        "admin_web.field.title": "Title",
        "admin_web.field.prize": "Prize",
        "admin_web.field.winner_user_id": "Winner User ID",
        "admin_web.field.created_by": "Created By",
        "admin_web.field.draw_at": "Draw Time",
        "admin_web.field.min_entries": "Min Entries",
        "admin_web.field.min_users": "Min Users",
        "admin_web.field.auto_draw_enabled": "Auto Draw",
        "admin_web.field.ended_at": "Ended At",
        "admin_web.field.source": "Source",
        "admin_web.field.event_id": "Event ID",
        "admin_web.field.goods_id": "Product ID",
        "admin_web.field.goods_name": "Product Name",
        "admin_web.field.prize_level": "Prize Level",
        "admin_web.field.ticket_count": "Ticket Count",
        "admin_web.field.key": "Key",
        "admin_web.bot_setting.value.description": "For group_invite_share_template, keep {link}. For group_invite_reward_tiers, use 1=1,10=2,30=3.",
        "admin_web.lottery_event.status.description": "Use active for an open lottery; drawn and closed are terminal states.",
        "admin_web.lottery_event.draw_at.description": "Optional scheduled draw time. Auto draw must also be enabled.",
        "admin_web.lottery_event.min_entries.description": "Optional minimum total entries required before auto draw.",
        "admin_web.lottery_event.min_users.description": "Optional minimum unique users required before auto draw.",
    },
    "zh": {
        "admin_web.title": "Telegram 商店后台",
        "admin_web.login.title": "登录 {title}",
        "admin_web.login.username": "用户名",
        "admin_web.login.username_placeholder": "请输入用户名",
        "admin_web.login.password": "密码",
        "admin_web.login.password_placeholder": "请输入密码",
        "admin_web.login.remember": "在本机记住登录",
        "admin_web.login.remember_hint": "会在当前浏览器保存后台登录状态，保存时长由后台配置控制。",
        "admin_web.login.submit": "登录",
        "admin_web.login.invalid_credentials": "用户名或密码错误。",
        "admin_web.logout": "退出登录",
        "admin_web.language": "语言",
        "admin_web.language.zh": "中文",
        "admin_web.language.en": "English",
        "admin_web.font_size": "字号",
        "admin_web.font_size.option": "{size}号",
        "admin_web.operations": "商品运营",
        "admin_web.operations.subtitle": "在一个后台页面管理分类、商品、库存、JSON 交付文件和兑换码。",
        "admin_web.platform_review": "平台审核",
        "admin_web.platform_review.subtitle": "审核频道提交、频道举报、频道认领、中转站、站长认领和社区反馈。",
        "admin_web.actions": "操作",
        "admin_web.export": "导出",
        "admin_web.new": "新建{name}",
        "admin_web.create_title": "新建{name}",
        "admin_web.edit_title": "编辑{name}",
        "admin_web.delete_selected": "删除选中项",
        "admin_web.search_placeholder": "搜索：{fields}",
        "admin_web.search": "搜索",
        "admin_web.view": "查看",
        "admin_web.edit": "编辑",
        "admin_web.delete": "删除",
        "admin_web.showing": "显示",
        "admin_web.to": "到",
        "admin_web.of": "共",
        "admin_web.items": "条",
        "admin_web.prev": "上一页",
        "admin_web.next": "下一页",
        "admin_web.show": "每页显示",
        "admin_web.page": "页",
        "admin_web.filters": "筛选",
        "admin_web.cancel": "取消",
        "admin_web.yes": "是",
        "admin_web.no": "否",
        "admin_web.save": "保存",
        "admin_web.save_continue": "保存并继续编辑",
        "admin_web.save_add_another": "保存并继续新建",
        "admin_web.save_as_new": "另存为新记录",
        "admin_web.column": "字段",
        "admin_web.value": "值",
        "admin_web.go_back": "返回",
        "admin_web.confirm": "请确认",
        "admin_web.close": "关闭",
        "admin_web.toggle_navigation": "展开/收起导航",
        "admin_web.select_all": "全选",
        "admin_web.select_item": "选择项目",
        "admin_web.required_field": "这是必填字段",
        "admin_web.delete_confirm": "确定要永久删除 {name} {pk} 吗？",
        "admin_web.clear_filter": "清除筛选",
        "admin_web.current": "当前",
        "admin_web.clear": "清除",
        "admin_web.select_operation": "选择条件...",
        "admin_web.enter_value": "请输入值",
        "admin_web.apply_filter": "应用筛选",
        "admin_web.copy": "复制",
        "admin_web.done": "完成",
        "admin_web.bool.true": "是",
        "admin_web.bool.false": "否",
        "admin_web.empty": "-",
        "admin_web.role.permissions.description": (
            "权限位掩码，把需要的权限值相加：USE=1，BROADCAST=2，SETTINGS=4，"
            "USERS=8，CATALOG=16，ADMINS=32，OWNER=64，STATS=128，"
            "BALANCE=256，PROMOS=512。例：927 = 完整管理员，1023 = 全部权限（Owner）。"
        ),
        "admin_web.model.user": "用户",
        "admin_web.model.users": "用户",
        "admin_web.model.role": "角色",
        "admin_web.model.roles": "角色",
        "admin_web.model.category": "分类",
        "admin_web.model.categories": "分类",
        "admin_web.model.product": "商品",
        "admin_web.model.products": "商品",
        "admin_web.model.stock_item": "库存项",
        "admin_web.model.stock_items": "库存项",
        "admin_web.model.purchase": "购买记录",
        "admin_web.model.purchases": "购买记录",
        "admin_web.model.operation": "余额流水",
        "admin_web.model.operations": "余额流水",
        "admin_web.model.payment": "支付记录",
        "admin_web.model.payments": "支付记录",
        "admin_web.model.referral_earning": "返佣记录",
        "admin_web.model.referral_earnings": "返佣记录",
        "admin_web.model.audit_log": "审计日志",
        "admin_web.model.audit_logs": "审计日志",
        "admin_web.model.promo_code": "优惠码",
        "admin_web.model.promo_codes": "优惠码",
        "admin_web.model.cart_item": "购物车项",
        "admin_web.model.cart_items": "购物车项",
        "admin_web.model.review": "评价",
        "admin_web.model.reviews": "评价",
        "admin_web.model.checkin": "签到记录",
        "admin_web.model.checkins": "签到记录",
        "admin_web.model.lottery_event": "抽奖活动",
        "admin_web.model.lottery_events": "抽奖活动",
        "admin_web.model.lottery_entry": "抽奖报名",
        "admin_web.model.lottery_entries": "抽奖报名",
        "admin_web.model.lottery_winner": "中奖记录",
        "admin_web.model.lottery_winners": "中奖记录",
        "admin_web.model.bot_setting": "机器人设置",
        "admin_web.model.bot_settings": "机器人设置",
        "admin_web.field.id": "ID",
        "admin_web.field.telegram_id": "Telegram ID",
        "admin_web.field.balance": "内部余额",
        "admin_web.field.points_balance": "积分",
        "admin_web.field.locale": "语言",
        "admin_web.field.role_id": "角色 ID",
        "admin_web.field.referral_id": "推荐人 ID",
        "admin_web.field.registration_date": "注册时间",
        "admin_web.field.is_blocked": "已封禁",
        "admin_web.field.name": "名称",
        "admin_web.field.default": "默认",
        "admin_web.field.permissions": "权限",
        "admin_web.field.price": "余额价格",
        "admin_web.field.points_price": "积分兑换价",
        "admin_web.field.points_max_per_redeem": "单次兑换上限",
        "admin_web.field.lottery_enabled": "加入奖品池",
        "admin_web.field.lottery_level": "获奖等级",
        "admin_web.field.lottery_winners_count": "该奖项中奖人数",
        "admin_web.field.description": "描述",
        "admin_web.field.category_id": "分类 ID",
        "admin_web.field.item_id": "商品 ID",
        "admin_web.field.value": "内容",
        "admin_web.field.is_infinity": "无限库存",
        "admin_web.field.item_name": "商品名称",
        "admin_web.field.buyer_id": "购买用户 ID",
        "admin_web.field.bought_datetime": "购买时间",
        "admin_web.field.unique_id": "唯一编号",
        "admin_web.field.user_id": "用户 ID",
        "admin_web.field.operation_value": "变动金额",
        "admin_web.field.operation_time": "流水时间",
        "admin_web.field.provider": "支付供应商",
        "admin_web.field.external_id": "外部订单 ID",
        "admin_web.field.amount": "金额",
        "admin_web.field.currency": "币种",
        "admin_web.field.status": "状态",
        "admin_web.field.created_at": "创建时间",
        "admin_web.field.updated_at": "更新时间",
        "admin_web.field.referrer_id": "推荐人 ID",
        "admin_web.field.original_amount": "原始金额",
        "admin_web.field.timestamp": "时间",
        "admin_web.field.level": "级别",
        "admin_web.field.action": "动作",
        "admin_web.field.resource_type": "资源类型",
        "admin_web.field.resource_id": "资源 ID",
        "admin_web.field.details": "详情",
        "admin_web.field.ip_address": "IP 地址",
        "admin_web.field.code": "优惠码",
        "admin_web.field.discount_type": "折扣类型",
        "admin_web.field.discount_value": "折扣值",
        "admin_web.field.max_uses": "最大使用次数",
        "admin_web.field.current_uses": "已使用次数",
        "admin_web.field.expires_at": "过期时间",
        "admin_web.field.is_active": "启用",
        "admin_web.field.promo_code": "优惠码",
        "admin_web.field.added_at": "加入时间",
        "admin_web.field.rating": "评分",
        "admin_web.field.text": "内容",
        "admin_web.field.checkin_date": "签到日期",
        "admin_web.field.reward_amount": "旧奖励金额",
        "admin_web.field.points_awarded": "获得积分",
        "admin_web.field.tickets_awarded": "获得抽奖券",
        "admin_web.field.streak": "连续天数",
        "admin_web.field.title": "标题",
        "admin_web.field.prize": "奖品说明",
        "admin_web.field.winner_user_id": "中奖用户 ID",
        "admin_web.field.created_by": "创建人",
        "admin_web.field.draw_at": "开奖时间",
        "admin_web.field.min_entries": "最少报名数",
        "admin_web.field.min_users": "最少用户数",
        "admin_web.field.auto_draw_enabled": "自动开奖",
        "admin_web.field.ended_at": "结束时间",
        "admin_web.field.source": "来源",
        "admin_web.field.event_id": "抽奖 ID",
        "admin_web.field.goods_id": "商品 ID",
        "admin_web.field.goods_name": "商品名称",
        "admin_web.field.prize_level": "获奖等级",
        "admin_web.field.ticket_count": "抽奖券数",
        "admin_web.field.key": "配置键",
        "admin_web.bot_setting.value.description": "邀请文案模板请保留 {link}；邀请阶梯奖励 group_invite_reward_tiers 格式为 1=1,10=2,30=3。",
        "admin_web.lottery_event.status.description": "active 表示进行中；drawn/closed 表示已开奖或已关闭。",
        "admin_web.lottery_event.draw_at.description": "可选的自动开奖时间；同时需要启用自动开奖。",
        "admin_web.lottery_event.min_entries.description": "自动开奖前要求的最少报名总数，可为 0。",
        "admin_web.lottery_event.min_users.description": "自动开奖前要求的最少参与用户数，可为 0。",
    },
}


def normalize_admin_locale(locale: str | None) -> str | None:
    if not locale:
        return None
    value = locale.strip().lower()
    return value if value in ADMIN_SUPPORTED_LOCALES else None


def get_admin_locale(request: Request | None = None) -> str:
    if request is not None:
        request_locale = normalize_admin_locale(request.query_params.get("lang"))
        if request_locale:
            return request_locale

        try:
            session_locale = normalize_admin_locale(request.session.get("admin_locale"))
        except AssertionError:
            session_locale = None
        if session_locale:
            return session_locale
    return _current_admin_locale.get()


def set_current_admin_locale(locale: str | None) -> Token:
    return _current_admin_locale.set(normalize_admin_locale(locale) or ADMIN_DEFAULT_LOCALE)


def reset_current_admin_locale(token: Token) -> None:
    _current_admin_locale.reset(token)


def normalize_admin_font_size(value: Any | None) -> int | None:
    if value is None:
        return None
    try:
        size = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return size if size in ADMIN_SUPPORTED_FONT_SIZES else None


def get_admin_font_size(request: Request | None = None) -> int:
    if request is not None:
        request_size = normalize_admin_font_size(request.query_params.get("size"))
        if request_size is not None:
            return request_size

        try:
            session_size = normalize_admin_font_size(request.session.get("admin_font_size"))
        except AssertionError:
            session_size = None
        if session_size is not None:
            return session_size
    return _current_admin_font_size.get()


def set_current_admin_font_size(value: Any | None) -> Token:
    return _current_admin_font_size.set(
        normalize_admin_font_size(value) or ADMIN_DEFAULT_FONT_SIZE
    )


def reset_current_admin_font_size(token: Token) -> None:
    _current_admin_font_size.reset(token)


def admin_t(key: str, /, **kwargs: Any) -> str:
    locale = get_admin_locale()
    text = ADMIN_TRANSLATIONS.get(locale, {}).get(key)
    if text is None:
        text = ADMIN_TRANSLATIONS["en"].get(key, key)
    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, ValueError, TypeError):
            return str(text)
    return str(text)


def admin_t_for(locale: str | None, key: str, /, **kwargs: Any) -> str:
    token = set_current_admin_locale(locale)
    try:
        return admin_t(key, **kwargs)
    finally:
        reset_current_admin_locale(token)


def admin_bool(value: Any) -> str:
    if value is True:
        return admin_t("admin_web.bool.true")
    if value is False:
        return admin_t("admin_web.bool.false")
    if value is None:
        return admin_t("admin_web.empty")
    return str(value)


def admin_template_context(request: Request) -> dict[str, Any]:
    locale = get_admin_locale(request)
    return {
        "admin_locale": locale,
        "admin_supported_locales": ADMIN_SUPPORTED_LOCALES,
        "admin_font_size": get_admin_font_size(request),
        "admin_supported_font_sizes": ADMIN_SUPPORTED_FONT_SIZES,
        "admin_t": admin_t,
        "admin_t_for": admin_t_for,
    }


def _admin_default_url(request: Request) -> str:
    try:
        return str(request.url_for("admin:index"))
    except Exception:
        return "/admin"


def _safe_admin_next_url(request: Request, default_url: str) -> str:
    next_url = request.query_params.get("next") or default_url
    try:
        parsed = URL(next_url)
        if parsed.netloc and parsed.netloc != request.url.netloc:
            return default_url
    except Exception:
        return default_url
    return next_url


def admin_set_language_url(request: Request, locale: str) -> str:
    query = urlencode({"lang": locale, "next": str(request.url)})
    return f"/admin/lang?{query}"


def admin_set_font_size_url(request: Request, size: int) -> str:
    normalized_size = normalize_admin_font_size(size) or ADMIN_DEFAULT_FONT_SIZE
    query = urlencode({"size": str(normalized_size), "next": str(request.url)})
    return f"/admin/font-size?{query}"


async def set_admin_language(request: Request) -> RedirectResponse:
    locale = normalize_admin_locale(request.query_params.get("lang"))
    if locale:
        request.session["admin_locale"] = locale

    default_url = _admin_default_url(request)
    next_url = _safe_admin_next_url(request, default_url)

    return RedirectResponse(next_url, status_code=302)


async def set_admin_font_size(request: Request) -> RedirectResponse:
    size = normalize_admin_font_size(request.query_params.get("size"))
    if size is not None:
        request.session["admin_font_size"] = size

    default_url = _admin_default_url(request)
    next_url = _safe_admin_next_url(request, default_url)

    return RedirectResponse(next_url, status_code=302)


class AdminLocaleMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive=receive)
        locale_token = set_current_admin_locale(get_admin_locale(request))
        font_size_token = set_current_admin_font_size(get_admin_font_size(request))
        try:
            await self.app(scope, receive, send)
        finally:
            reset_current_admin_font_size(font_size_token)
            reset_current_admin_locale(locale_token)
