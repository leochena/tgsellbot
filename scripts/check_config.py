from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
from pathlib import Path
from urllib.parse import quote_plus

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"


def _get(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _is_placeholder(value: str) -> bool:
    lowered = value.lower()
    return (
        not value
        or "your_" in lowered
        or "change_me" in lowered
        or "change-me" in lowered
        or lowered in {"admin", "password", "token", "secret"}
    )


def validate_env() -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    if not ENV_PATH.exists():
        errors.append(".env is missing. Copy .env.example to .env and fill it in.")
        return errors, warnings

    load_dotenv(ENV_PATH, encoding="utf-8", override=True)

    required = [
        "TOKEN",
        "OWNER_ID",
        "POSTGRES_DB",
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "POSTGRES_HOST",
        "DB_PORT",
        "ADMIN_USERNAME",
        "ADMIN_PASSWORD",
        "SECRET_KEY",
    ]

    for name in required:
        if _is_placeholder(_get(name)):
            errors.append(f"{name} is missing or still uses a placeholder value.")

    owner_id = _get("OWNER_ID")
    if owner_id and not owner_id.isdigit():
        errors.append("OWNER_ID must be a numeric Telegram user ID.")

    db_port = _get("DB_PORT")
    if db_port and not db_port.isdigit():
        errors.append("DB_PORT must be numeric.")

    postgres_schema = _get("POSTGRES_SCHEMA", "public")
    if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", postgres_schema):
        errors.append("POSTGRES_SCHEMA must be a valid PostgreSQL identifier.")

    admin_password = _get("ADMIN_PASSWORD")
    if admin_password and len(admin_password) < 12:
        warnings.append("ADMIN_PASSWORD should be at least 12 characters.")

    secret_key = _get("SECRET_KEY")
    if secret_key and len(secret_key) < 32:
        warnings.append("SECRET_KEY should be at least 32 characters.")

    stars_enabled = False
    try:
        stars_enabled = float(_get("STARS_PER_VALUE", "0")) > 0
    except ValueError:
        errors.append("STARS_PER_VALUE must be numeric.")

    payment_enabled = bool(_get("CRYPTO_PAY_TOKEN")) or bool(_get("TELEGRAM_PROVIDER_TOKEN")) or stars_enabled
    if not payment_enabled:
        errors.append("No payment method is enabled. Set CRYPTO_PAY_TOKEN, TELEGRAM_PROVIDER_TOKEN, or STARS_PER_VALUE > 0.")
    if _get("TELEGRAM_PROVIDER_TOKEN"):
        warnings.append("TELEGRAM_PROVIDER_TOKEN enables the Stripe/card provider through Telegram Payments. Keep Stars enabled for digital goods sold inside Telegram.")

    try:
        min_amount = int(_get("MIN_AMOUNT", "0"))
        max_amount = int(_get("MAX_AMOUNT", "0"))
        if min_amount >= max_amount:
            errors.append("MIN_AMOUNT must be lower than MAX_AMOUNT.")
    except ValueError:
        errors.append("MIN_AMOUNT and MAX_AMOUNT must be numeric integers.")

    try:
        if float(_get("CHECKIN_REWARD_AMOUNT", "0")) < 0:
            errors.append("CHECKIN_REWARD_AMOUNT must be >= 0.")
    except ValueError:
        errors.append("CHECKIN_REWARD_AMOUNT must be numeric.")

    try:
        if int(_get("CHECKIN_TICKETS_PER_DAY", "0")) < 0:
            errors.append("CHECKIN_TICKETS_PER_DAY must be >= 0.")
    except ValueError:
        errors.append("CHECKIN_TICKETS_PER_DAY must be a numeric integer.")

    if _get("WEBHOOK_ENABLED", "0") == "1":
        if not _get("WEBHOOK_URL").startswith("https://"):
            errors.append("WEBHOOK_URL must be HTTPS when WEBHOOK_ENABLED=1.")
        if not _get("WEBHOOK_SECRET"):
            warnings.append("WEBHOOK_SECRET is recommended when webhook mode is enabled.")

    if _get("REDIS_ENABLED", "1") == "1" and not _get("REDIS_HOST"):
        errors.append("REDIS_HOST is required when REDIS_ENABLED=1.")

    return errors, warnings


async def check_database() -> tuple[bool, str]:
    try:
        import asyncpg
    except ImportError:
        return False, "asyncpg is not installed. Run pip install -r requirements.txt first."

    dsn = (
        f"postgresql://{_get('POSTGRES_USER')}:{quote_plus(_get('POSTGRES_PASSWORD'))}"
        f"@{_get('POSTGRES_HOST')}:{_get('DB_PORT', '5432')}/{_get('POSTGRES_DB')}"
    )
    try:
        conn = await asyncpg.connect(dsn, timeout=10)
        try:
            await conn.execute("select 1")
        finally:
            await conn.close()
        return True, "database connection OK."
    except Exception as exc:
        return False, f"database connection failed: {exc}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Telegram shop bot configuration.")
    parser.add_argument("--check-db", action="store_true", help="Also test PostgreSQL connectivity.")
    args = parser.parse_args()

    errors, warnings = validate_env()

    if args.check_db and not errors:
        ok, message = asyncio.run(check_database())
        if ok:
            print(f"OK: {message}")
        else:
            errors.append(message)

    for warning in warnings:
        print(f"WARNING: {warning}")

    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1

    print("OK: configuration is ready for deployment checks.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
