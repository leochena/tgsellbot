import logging
import os
import re
from abc import ABC
from typing import Final
from urllib.parse import quote_plus

_env_logger = logging.getLogger(__name__)


class EnvKeys(ABC):
    """Secure environment configuration with validation"""

    @staticmethod
    def _get_required(key: str) -> str:
        val = os.getenv(key)
        if not val:
            raise ValueError(f"Missing required environment variable: {key}")
        return val

    @staticmethod
    def _get_optional(key: str, default: str = "") -> str:
        return os.getenv(key, default)

    # Telegram
    TOKEN: Final = _get_required('TOKEN')
    OWNER_ID: Final = int(_get_required('OWNER_ID'))
    BOT_PROXY_URL: Final = _get_optional("BOT_PROXY_URL", "")

    # Database
    POSTGRES_DB: Final = _get_required("POSTGRES_DB")
    POSTGRES_USER: Final = _get_required("POSTGRES_USER")
    POSTGRES_PASSWORD: Final = _get_required("POSTGRES_PASSWORD")
    DB_PORT: Final = int(_get_optional("DB_PORT", "5432"))
    DB_DRIVER: Final = _get_optional("DB_DRIVER", "postgresql+asyncpg")
    POSTGRES_HOST: Final = _get_optional("POSTGRES_HOST", "localhost")
    POSTGRES_SCHEMA: Final = _get_optional("POSTGRES_SCHEMA", "public")

    # Redis
    REDIS_ENABLED: Final = _get_optional("REDIS_ENABLED", "1")
    REDIS_HOST: Final = _get_optional("REDIS_HOST", "localhost")
    REDIS_PORT: Final = int(_get_optional("REDIS_PORT", "6379"))
    REDIS_DB: Final = int(_get_optional("REDIS_DB", "0"))
    REDIS_PASSWORD: Final = _get_optional("REDIS_PASSWORD", "")

    # Payments
    TELEGRAM_PROVIDER_TOKEN: Final = _get_optional("TELEGRAM_PROVIDER_TOKEN", "")
    CRYPTO_PAY_TOKEN: Final = _get_optional("CRYPTO_PAY_TOKEN", "")
    STARS_PER_VALUE: Final = float(_get_optional("STARS_PER_VALUE", "0.91"))
    REFERRAL_PERCENT: Final = int(_get_optional("REFERRAL_PERCENT", "0"))
    PAY_CURRENCY: Final = _get_optional("PAY_CURRENCY", "RUB")
    BALANCE_CURRENCY: Final = _get_optional("BALANCE_CURRENCY", PAY_CURRENCY)
    PAYMENT_TIME: Final = int(_get_optional("PAYMENT_TIME", "1800"))
    MIN_AMOUNT: Final = int(_get_optional("MIN_AMOUNT", "20"))
    MAX_AMOUNT: Final = int(_get_optional("MAX_AMOUNT", "10000"))

    # Links / UI
    CHANNEL_URL: Final = _get_optional("CHANNEL_URL", "")
    CHANNEL_ID: Final = _get_optional("CHANNEL_ID", "")
    ANNOUNCEMENT_CHAT_ID: Final = _get_optional("ANNOUNCEMENT_CHAT_ID", CHANNEL_ID)
    HELPER_ID: Final = _get_optional("HELPER_ID", "")
    RULES: Final = _get_optional("RULES", "")

    # Locale & logs
    BOT_LOCALE: Final = _get_optional("BOT_LOCALE", "ru")
    BOT_LOGFILE: Final = _get_optional("BOT_LOGFILE", "logs/bot.log")
    BOT_AUDITFILE: Final = _get_optional("BOT_AUDITFILE", "logs/audit.log")
    LOG_TO_STDOUT: Final = _get_optional("LOG_TO_STDOUT", "1")
    LOG_TO_FILE: Final = _get_optional("LOG_TO_FILE", "1")
    DEBUG: Final = _get_optional("DEBUG", "0")
    REVIEWS_ENABLED: Final = _get_optional("REVIEWS_ENABLED", "1")

    # Engagement
    CHECKIN_POINTS_REWARD: Final = int(_get_optional("CHECKIN_POINTS_REWARD", _get_optional("CHECKIN_REWARD_AMOUNT", "1")))
    CHECKIN_REWARD_AMOUNT: Final = _get_optional("CHECKIN_REWARD_AMOUNT", str(CHECKIN_POINTS_REWARD))
    CHECKIN_TICKETS_PER_DAY: Final = int(_get_optional("CHECKIN_TICKETS_PER_DAY", "1"))
    GROUP_INVITE_REWARD_POINTS: Final = int(_get_optional("GROUP_INVITE_REWARD_POINTS", "1"))

    # Web admin panel
    WEB_ADMIN_ENABLED: Final = _get_optional("WEB_ADMIN_ENABLED", "1")
    ADMIN_HOST: Final = _get_optional("ADMIN_HOST", _get_optional("MONITORING_HOST", "localhost"))
    ADMIN_PORT: Final = int(_get_optional("ADMIN_PORT", _get_optional("MONITORING_PORT", "9090")))
    ADMIN_USERNAME: Final = _get_optional("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD: Final = _get_optional("ADMIN_PASSWORD", "admin")
    SECRET_KEY: Final = _get_optional("SECRET_KEY", "change-me-in-production")
    ADMIN_SESSION_MAX_AGE_DAYS: Final = int(_get_optional("ADMIN_SESSION_MAX_AGE_DAYS", "30"))

    # Webhook
    WEBHOOK_ENABLED: Final = _get_optional("WEBHOOK_ENABLED", "0")
    WEBHOOK_URL: Final = _get_optional("WEBHOOK_URL", "")
    WEBHOOK_PATH: Final = _get_optional("WEBHOOK_PATH", "/webhook")
    WEBHOOK_SECRET: Final = _get_optional("WEBHOOK_SECRET", "")

    # Cleanup
    AUDIT_RETENTION_DAYS: Final = int(_get_optional("AUDIT_RETENTION_DAYS", "90"))
    PAYMENTS_RETENTION_DAYS: Final = int(_get_optional("PAYMENTS_RETENTION_DAYS", "90"))

    DATABASE_URL: Final = f"postgresql+asyncpg://{POSTGRES_USER}:{quote_plus(POSTGRES_PASSWORD)}@{POSTGRES_HOST}:{DB_PORT}/{POSTGRES_DB}"

    if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", POSTGRES_SCHEMA):
        raise ValueError("POSTGRES_SCHEMA must be a valid PostgreSQL identifier.")

    # Startup validation
    if ADMIN_PASSWORD == "admin":
        _env_logger.warning(
            "SECURITY: ADMIN_PASSWORD is set to the default value 'admin'. "
            "Change it immediately via the ADMIN_PASSWORD env variable."
        )
    if SECRET_KEY == "change-me-in-production":
        _env_logger.warning(
            "SECURITY: SECRET_KEY is set to the default value. "
            "Set a strong random SECRET_KEY env variable for session security."
        )
    if int(MIN_AMOUNT) >= int(MAX_AMOUNT):
        _env_logger.warning(
            "CONFIG: MIN_AMOUNT (%s) >= MAX_AMOUNT (%s). "
            "Payment amounts will always be rejected.", MIN_AMOUNT, MAX_AMOUNT
        )
    if int(REFERRAL_PERCENT) < 0 or int(REFERRAL_PERCENT) > 99:
        _env_logger.warning(
            "CONFIG: REFERRAL_PERCENT=%s is outside the valid range [0, 99].",
            REFERRAL_PERCENT,
        )
