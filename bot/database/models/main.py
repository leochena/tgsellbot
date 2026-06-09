import datetime
import hashlib
from typing import Any

from sqlalchemy import (
    Column, Integer, String, BigInteger, ForeignKey, Text, Boolean,
    DateTime, Numeric, Index, UniqueConstraint, CheckConstraint, func, select, text
)
from bot.database.main import Database
from sqlalchemy.orm import relationship


class Permission:
    USE             = 1 << 0   #   1 — basic access
    BROADCAST       = 1 << 1   #   2 — mass messaging
    SETTINGS_MANAGE = 1 << 2   #   4 — bot settings (maintenance, etc.)
    USERS_MANAGE    = 1 << 3   #   8 — view/block/unblock users, referrals, purchases
    CATALOG_MANAGE  = 1 << 4   #  16 — categories, positions, items/goods CRUD
    ADMINS_MANAGE   = 1 << 5   #  32 — role CRUD, role assignment
    OWN             = 1 << 6   #  64 — owner-only operations
    STATS_VIEW      = 1 << 7   # 128 — statistics, logs, bought-item search
    BALANCE_MANAGE  = 1 << 8   # 256 — top-up / deduct user balance
    PROMO_MANAGE    = 1 << 9   # 512 — promo code CRUD

    @staticmethod
    def is_subset(perms: int, of: int) -> bool:
        """True if every bit in `perms` is also set in `of`."""
        return (perms & ~of) == 0

    @staticmethod
    def has_any_admin_perm(perms: int) -> bool:
        """True if `perms` has any permission beyond USE."""
        return (perms & ~Permission.USE) != 0


class Role(Database.BASE):
    __tablename__ = 'roles'
    id = Column(Integer, primary_key=True)
    name = Column(String(64), unique=True)
    default = Column(Boolean, default=False, index=True)
    permissions = Column(Integer)
    users = relationship('User', backref='role', lazy='raise')

    def __init__(self, name: str, permissions=None, **kwargs):
        super(Role, self).__init__(**kwargs)
        if self.permissions is None:
            self.permissions = 0
        self.name = name
        self.permissions = permissions

    @staticmethod
    async def insert_roles():
        roles = {
            'USER': [Permission.USE],
            'ADMIN': [Permission.USE, Permission.BROADCAST,
                      Permission.SETTINGS_MANAGE, Permission.USERS_MANAGE,
                      Permission.CATALOG_MANAGE, Permission.STATS_VIEW,
                      Permission.BALANCE_MANAGE, Permission.PROMO_MANAGE],
            'OWNER': [Permission.USE, Permission.BROADCAST,
                      Permission.SETTINGS_MANAGE, Permission.USERS_MANAGE,
                      Permission.CATALOG_MANAGE, Permission.ADMINS_MANAGE,
                      Permission.OWN, Permission.STATS_VIEW,
                      Permission.BALANCE_MANAGE, Permission.PROMO_MANAGE],
        }
        default_role = 'USER'
        async with Database().session() as s:
            for r, perms in roles.items():
                result = await s.execute(select(Role).filter_by(name=r))
                role = result.scalars().first()
                if role is None:
                    role = Role(name=r)
                    s.add(role)
                role.reset_permissions()
                for perm in perms:
                    role.add_permission(perm)
                role.default = (role.name == default_role)

    def add_permission(self, perm):
        self.permissions |= perm

    def remove_permission(self, perm):
        self.permissions &= ~perm

    def reset_permissions(self):
        self.permissions = 0

    def has_permission(self, perm):
        return self.permissions & perm == perm

    def __repr__(self):
        return '<Role %r>' % self.name


class User(Database.BASE):
    __tablename__ = 'users'
    telegram_id = Column(BigInteger, primary_key=True)
    role_id = Column(Integer, ForeignKey('roles.id', ondelete="RESTRICT"), default=1, index=True)
    balance = Column(Numeric(12, 2), nullable=False, default=0)
    points_balance = Column(Integer, nullable=False, default=0)
    locale = Column(String(8), nullable=True, index=True)
    referral_id = Column(BigInteger, ForeignKey('users.telegram_id', ondelete="SET NULL"), nullable=True, index=True)
    registration_date = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    is_blocked = Column(Boolean, default=False, index=True)
    user_operations = relationship("Operations", back_populates="user_telegram_id", lazy='raise')
    user_goods = relationship("BoughtGoods", back_populates="user_telegram_id", lazy='raise')

    __table_args__ = (
        CheckConstraint('referral_id != telegram_id', name='ck_users_no_self_referral'),
        Index('ix_users_registration_date', 'registration_date'),
    )

    referral_earnings_received = relationship(
        "ReferralEarnings",
        foreign_keys="ReferralEarnings.referrer_id",
        back_populates="referrer",
        lazy='raise',
    )
    referral_earnings_generated = relationship(
        "ReferralEarnings",
        foreign_keys="ReferralEarnings.referral_id",
        back_populates="referral",
        lazy='raise',
    )

    def __init__(self, telegram_id: int, registration_date: datetime.datetime, balance=0, referral_id=None,
                 role_id: int = 1, locale: str | None = None, points_balance: int = 0, **kw: Any):
        super().__init__(**kw)
        self.telegram_id = telegram_id
        self.role_id = role_id
        self.balance = balance
        self.points_balance = points_balance
        self.locale = locale
        self.referral_id = referral_id
        self.registration_date = registration_date


class Categories(Database.BASE):
    __tablename__ = 'categories'
    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True, nullable=False)
    items = relationship("Goods", back_populates="category", lazy='raise')

    def __init__(self, name: str, **kw: Any):
        super().__init__(**kw)
        self.name = name


class Goods(Database.BASE):
    __tablename__ = 'goods'
    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True, nullable=False)
    price = Column(Numeric(12, 2), nullable=False)
    points_price = Column(Integer, nullable=False, default=0)
    points_max_per_redeem = Column(Integer, nullable=False, default=1)
    lottery_enabled = Column(Boolean, nullable=False, default=False, index=True)
    lottery_level = Column(String(64), nullable=False, default='')
    lottery_winners_count = Column(Integer, nullable=False, default=1)
    description = Column(Text, nullable=False)
    category_id = Column(Integer, ForeignKey('categories.id', ondelete="CASCADE"), nullable=False, index=True)
    category = relationship("Categories", back_populates="items", lazy='raise')
    values = relationship("ItemValues", back_populates="item", lazy='raise')

    def __init__(
            self,
            name: str,
            price,
            description: str,
            category_id: int,
            points_price: int = 0,
            points_max_per_redeem: int = 1,
            lottery_enabled: bool = False,
            lottery_level: str = '',
            lottery_winners_count: int = 1,
            **kw: Any,
    ):
        super().__init__(**kw)
        self.name = name
        self.price = price
        self.points_price = points_price
        self.points_max_per_redeem = points_max_per_redeem
        self.lottery_enabled = lottery_enabled
        self.lottery_level = lottery_level
        self.lottery_winners_count = lottery_winners_count
        self.description = description
        self.category_id = category_id


class ItemValues(Database.BASE):
    __tablename__ = 'item_values'
    id = Column(Integer, primary_key=True)
    item_id = Column(Integer, ForeignKey('goods.id', ondelete="CASCADE"), nullable=False, index=True)
    value = Column(Text, nullable=True)
    value_hash = Column(String(64), nullable=False)
    is_infinity = Column(Boolean, nullable=False)
    item = relationship("Goods", back_populates="values", lazy='raise')

    __table_args__ = (
        UniqueConstraint('item_id', 'value_hash', name='uq_item_value_hash_per_item'),
        Index('ix_item_values_item_inf', 'item_id', 'is_infinity'),
    )

    def __init__(self, item_id: int, value: str, is_infinity: bool, **kw: Any):
        super().__init__(**kw)
        self.item_id = item_id
        self.value = value
        self.value_hash = stock_value_hash(value)
        self.is_infinity = is_infinity


def stock_value_hash(value: str | None) -> str:
    return hashlib.sha256((value or "").encode("utf-8")).hexdigest()


class BoughtGoods(Database.BASE):
    __tablename__ = 'bought_goods'
    id = Column(Integer, primary_key=True)
    item_name = Column(String(100), nullable=False, index=True)
    value = Column(Text, nullable=False)
    price = Column(Numeric(12, 2), nullable=False)
    buyer_id = Column(BigInteger, ForeignKey('users.telegram_id', ondelete="SET NULL"), nullable=True, index=True)
    bought_datetime = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    unique_id = Column(BigInteger, nullable=False, unique=True)
    user_telegram_id = relationship("User", back_populates="user_goods", lazy='raise')

    __table_args__ = (
        Index('ix_bought_goods_datetime', 'bought_datetime'),
        Index('ix_bought_goods_buyer_datetime', 'buyer_id', 'bought_datetime'),
    )

    def __init__(self, name: str, value: str, price, bought_datetime, unique_id, buyer_id: int = 0, **kw: Any):
        super().__init__(**kw)
        self.item_name = name
        self.value = value
        self.price = price
        self.buyer_id = buyer_id
        self.bought_datetime = bought_datetime
        self.unique_id = unique_id


class Operations(Database.BASE):
    __tablename__ = 'operations'
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey('users.telegram_id', ondelete="SET NULL"), nullable=True, index=True)
    operation_value = Column(Numeric(12, 2), nullable=False)
    operation_time = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    user_telegram_id = relationship("User", back_populates="user_operations", lazy='raise')

    __table_args__ = (
        Index('ix_operations_time', 'operation_time'),
    )

    def __init__(self, user_id: int, operation_value, operation_time, **kw: Any):
        super().__init__(**kw)
        self.user_id = user_id
        self.operation_value = operation_value
        self.operation_time = operation_time


class Payments(Database.BASE):
    __tablename__ = "payments"
    id = Column(Integer, primary_key=True)
    provider = Column(String(32), nullable=False, index=True)
    external_id = Column(String(128), nullable=False)
    user_id = Column(BigInteger, ForeignKey('users.telegram_id', ondelete="SET NULL"), nullable=True, index=True)
    amount = Column(Numeric(12, 2), nullable=False)
    currency = Column(String(8), nullable=False)
    status = Column(String(16), nullable=False, default="pending")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint('provider', 'external_id', name='uq_payment_provider_ext'),
        Index('ix_payments_status_created', 'status', 'created_at'),
    )


class ReferralEarnings(Database.BASE):
    __tablename__ = 'referral_earnings'

    id = Column(Integer, primary_key=True)
    referrer_id = Column(BigInteger, ForeignKey('users.telegram_id', ondelete="CASCADE"), nullable=False, index=True)
    referral_id = Column(BigInteger, ForeignKey('users.telegram_id', ondelete="CASCADE"), nullable=False, index=True)
    amount = Column(Numeric(12, 2), nullable=False)
    original_amount = Column(Numeric(12, 2), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    referrer = relationship(
        "User",
        foreign_keys="ReferralEarnings.referrer_id",
        back_populates="referral_earnings_received",
        lazy='raise',
    )
    referral = relationship(
        "User",
        foreign_keys="ReferralEarnings.referral_id",
        back_populates="referral_earnings_generated",
        lazy='raise',
    )

    __table_args__ = (
        CheckConstraint('referrer_id != referral_id', name='ck_referral_earnings_no_self_referral'),
        Index('ix_referral_earnings_referrer_created', 'referrer_id', 'created_at'),
        Index('ix_referral_earnings_referral_created', 'referral_id', 'created_at'),
    )

    def __init__(self, referrer_id: int, referral_id: int, amount, original_amount, **kw: Any):
        super().__init__(**kw)
        self.referrer_id = referrer_id
        self.referral_id = referral_id
        self.amount = amount
        self.original_amount = original_amount


class AuditLog(Database.BASE):
    __tablename__ = 'audit_log'
    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    level = Column(String(8), nullable=False, default="INFO")
    user_id = Column(BigInteger, nullable=True)
    action = Column(String(64), nullable=False)
    resource_type = Column(String(32), nullable=True)
    resource_id = Column(String(128), nullable=True)
    details = Column(Text, nullable=True)
    ip_address = Column(String(45), nullable=True)

    __table_args__ = (
        Index('ix_audit_log_timestamp', 'timestamp'),
        Index('ix_audit_log_user_id', 'user_id'),
        Index('ix_audit_log_action', 'action'),
    )

    def __repr__(self):
        return f'<AuditLog {self.action} user={self.user_id} @ {self.timestamp}>'


class PromoCodes(Database.BASE):
    __tablename__ = 'promo_codes'
    id = Column(Integer, primary_key=True)
    code = Column(String(50), unique=True, nullable=False, index=True)
    discount_type = Column(String(10), nullable=False)  # 'percent' | 'fixed'
    discount_value = Column(Numeric(12, 2), nullable=False)
    max_uses = Column(Integer, nullable=False, default=0)  # 0 = unlimited
    current_uses = Column(Integer, nullable=False, default=0)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    category_id = Column(Integer, ForeignKey('categories.id', ondelete='SET NULL'), nullable=True)
    item_id = Column(Integer, ForeignKey('goods.id', ondelete='SET NULL'), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class PromoCodeUsages(Database.BASE):
    __tablename__ = 'promo_code_usages'
    id = Column(Integer, primary_key=True)
    promo_id = Column(Integer, ForeignKey('promo_codes.id', ondelete='CASCADE'), nullable=False)
    user_id = Column(BigInteger, ForeignKey('users.telegram_id', ondelete='CASCADE'), nullable=False)
    used_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    __table_args__ = (UniqueConstraint('promo_id', 'user_id', name='uq_promo_usage_per_user'),)


class CartItems(Database.BASE):
    __tablename__ = 'cart_items'
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey('users.telegram_id', ondelete='CASCADE'), nullable=False, index=True)
    item_name = Column(String(100), nullable=False)
    promo_code = Column(String(50), nullable=True)
    added_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class GroupInviteLinks(Database.BASE):
    __tablename__ = 'group_invite_links'
    id = Column(Integer, primary_key=True)
    inviter_id = Column(BigInteger, ForeignKey('users.telegram_id', ondelete='CASCADE'), nullable=False, index=True)
    chat_id = Column(String(64), nullable=False, index=True)
    invite_link = Column(String(512), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint('inviter_id', 'chat_id', name='uq_group_invite_link_inviter_chat'),
        UniqueConstraint('invite_link', name='uq_group_invite_link_url'),
        Index('ix_group_invite_links_chat_inviter', 'chat_id', 'inviter_id'),
    )


class GroupInviteRewards(Database.BASE):
    __tablename__ = 'group_invite_rewards'
    id = Column(Integer, primary_key=True)
    inviter_id = Column(BigInteger, ForeignKey('users.telegram_id', ondelete='CASCADE'), nullable=False, index=True)
    invited_id = Column(BigInteger, ForeignKey('users.telegram_id', ondelete='CASCADE'), nullable=False, index=True)
    chat_id = Column(String(64), nullable=False, index=True)
    invite_link = Column(String(512), nullable=True)
    joined_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    rewarded_at = Column(DateTime(timezone=True), nullable=True)
    points_awarded = Column(Integer, nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint('invited_id', 'chat_id', name='uq_group_invite_reward_invited_chat'),
        CheckConstraint('inviter_id != invited_id', name='ck_group_invite_reward_no_self'),
        Index('ix_group_invite_rewards_pending', 'chat_id', 'invited_id', 'rewarded_at'),
        Index('ix_group_invite_rewards_inviter_joined', 'inviter_id', 'joined_at'),
    )


class BotSettings(Database.BASE):
    __tablename__ = 'bot_settings'
    key = Column(String(128), primary_key=True)
    value = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    @staticmethod
    async def insert_defaults():
        defaults = {
            "group_invite_share_template": {
                "value": "点击加入 AI 公益分享频道：{link}\n每日签到免费领取积分，积分可抽奖、兑换商品。分享 GPT Plus、接码、邮箱等资源。",
                "description": "邀请文案模板；{link} 会由系统替换为用户专属邀请链接。",
            },
            "group_invite_share_template_zh": {
                "value": "点击加入 AI 公益分享频道：{link}\n每日签到免费领取积分，积分可抽奖、兑换商品。分享 GPT Plus、接码、邮箱等资源。",
                "description": "中文邀请文案模板；{link} 会由系统替换为用户专属邀请链接。",
            },
            "group_invite_share_template_en": {
                "value": "Join the AI public-benefit sharing group: {link}\nCheck in daily to earn free points. Points can be used for lotteries and product redemption, including GPT Plus, SMS verification, email and related resources.",
                "description": "English invite copy template; {link} is replaced with the user's personal invite link.",
            },
            "group_invite_share_template_ru": {
                "value": "Присоединяйтесь к группе AI public-benefit: {link}\nЕжедневно отмечайтесь и получайте баллы. Баллы можно использовать в розыгрышах и для обмена на товары: GPT Plus, SMS-верификация, email и другие ресурсы.",
                "description": "Russian invite copy template; {link} is replaced with the user's personal invite link.",
            },
            "rules_text": {
                "value": "",
                "description": "Optional generic rules text shown above the built-in user trading guide.",
            },
            "rules_text_zh": {
                "value": "",
                "description": "可选中文规则文案；会显示在内置交易说明上方。",
            },
            "rules_text_en": {
                "value": "",
                "description": "Optional English rules text shown above the built-in user trading guide.",
            },
            "rules_text_ru": {
                "value": "",
                "description": "Optional Russian rules text shown above the built-in user trading guide.",
            },
        }
        async with Database().session() as s:
            for key, data in defaults.items():
                setting = (await s.execute(select(BotSettings).where(BotSettings.key == key))).scalars().first()
                if setting is None:
                    s.add(BotSettings(key=key, value=data["value"], description=data["description"]))
                elif not setting.description:
                    setting.description = data["description"]


class Reviews(Database.BASE):
    __tablename__ = 'reviews'
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey('users.telegram_id', ondelete='CASCADE'), nullable=False, index=True)
    item_name = Column(String(100), nullable=False, index=True)
    rating = Column(Integer, nullable=False)  # 1-5
    text = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    __table_args__ = (
        UniqueConstraint('user_id', 'item_name', name='uq_review_per_user_item'),
        CheckConstraint('rating >= 1 AND rating <= 5', name='ck_review_rating_range'),
    )


class CheckIns(Database.BASE):
    __tablename__ = 'checkins'
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey('users.telegram_id', ondelete='CASCADE'), nullable=False, index=True)
    checkin_date = Column(DateTime(timezone=True), nullable=False)
    reward_amount = Column(Numeric(12, 2), nullable=False, default=0)
    points_awarded = Column(Integer, nullable=False, default=0)
    tickets_awarded = Column(Integer, nullable=False, default=0)
    streak = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint('user_id', 'checkin_date', name='uq_checkins_user_date'),
        Index('ix_checkins_date', 'checkin_date'),
    )


class LotteryEvents(Database.BASE):
    __tablename__ = 'lottery_events'
    id = Column(Integer, primary_key=True)
    title = Column(String(128), nullable=False)
    prize = Column(Text, nullable=False)
    status = Column(String(16), nullable=False, default='active', index=True)
    winner_user_id = Column(BigInteger, ForeignKey('users.telegram_id', ondelete='SET NULL'), nullable=True, index=True)
    created_by = Column(BigInteger, ForeignKey('users.telegram_id', ondelete='SET NULL'), nullable=True, index=True)
    draw_at = Column(DateTime(timezone=True), nullable=True, index=True)
    min_entries = Column(Integer, nullable=False, default=0)
    min_users = Column(Integer, nullable=False, default=0)
    auto_draw_enabled = Column(Boolean, nullable=False, default=False, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    ended_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index('ix_lottery_events_status_created', 'status', 'created_at'),
    )


class LotteryEntries(Database.BASE):
    __tablename__ = 'lottery_entries'
    id = Column(Integer, primary_key=True)
    event_id = Column(Integer, ForeignKey('lottery_events.id', ondelete='CASCADE'), nullable=False, index=True)
    user_id = Column(BigInteger, ForeignKey('users.telegram_id', ondelete='CASCADE'), nullable=False, index=True)
    source = Column(String(32), nullable=False, default='checkin')
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        Index('ix_lottery_entries_event_user', 'event_id', 'user_id'),
    )


class LotteryWinners(Database.BASE):
    __tablename__ = 'lottery_winners'
    id = Column(Integer, primary_key=True)
    event_id = Column(Integer, ForeignKey('lottery_events.id', ondelete='CASCADE'), nullable=False, index=True)
    user_id = Column(BigInteger, ForeignKey('users.telegram_id', ondelete='CASCADE'), nullable=False, index=True)
    goods_id = Column(Integer, ForeignKey('goods.id', ondelete='SET NULL'), nullable=True, index=True)
    goods_name = Column(String(100), nullable=False)
    prize_level = Column(String(64), nullable=False)
    ticket_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint('event_id', 'user_id', 'goods_id', name='uq_lottery_winner_event_user_goods'),
        Index('ix_lottery_winners_event_level', 'event_id', 'prize_level'),
    )


async def register_models():
    from bot.misc import EnvKeys

    async with Database().engine.begin() as conn:
        if EnvKeys.POSTGRES_SCHEMA != "public":
            await conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{EnvKeys.POSTGRES_SCHEMA}"'))
            await conn.execute(text(f'SET search_path TO "{EnvKeys.POSTGRES_SCHEMA}"'))
        await conn.run_sync(Database.BASE.metadata.create_all)
    await Role.insert_roles()
    await BotSettings.insert_defaults()
