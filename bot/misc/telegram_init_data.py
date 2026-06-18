from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl


class InitDataError(ValueError):
    """Raised when Telegram Mini App initData cannot be trusted."""


@dataclass(frozen=True)
class MiniAppAuth:
    user_id: int
    auth_date: int
    user: dict[str, Any]
    fields: dict[str, str]


def validate_telegram_init_data(
        init_data: str,
        bot_token: str,
        *,
        max_age_seconds: int = 24 * 60 * 60,
        now: int | None = None,
) -> MiniAppAuth:
    fields = _parse_init_data(init_data)
    received_hash = fields.get("hash", "")
    if not received_hash:
        raise InitDataError("Telegram initData hash is required.")
    if not bot_token:
        raise InitDataError("Bot token is not configured.")

    data_check_string = "\n".join(
        f"{key}={value}"
        for key, value in sorted(fields.items())
        if key != "hash"
    )
    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    expected_hash = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected_hash, received_hash):
        raise InitDataError("Telegram initData signature is invalid.")

    auth_date = _parse_auth_date(fields)
    now = int(time.time()) if now is None else int(now)
    if max_age_seconds > 0 and auth_date + int(max_age_seconds) < now:
        raise InitDataError("Telegram initData is expired.")

    user = _parse_user(fields)
    return MiniAppAuth(
        user_id=int(user["id"]),
        auth_date=auth_date,
        user=user,
        fields=fields,
    )


def _parse_init_data(init_data: str) -> dict[str, str]:
    text = (init_data or "").strip()
    if not text:
        raise InitDataError("Telegram initData is required.")
    pairs = parse_qsl(text, keep_blank_values=True, strict_parsing=False)
    fields = {str(key): str(value) for key, value in pairs}
    if not fields:
        raise InitDataError("Telegram initData is required.")
    return fields


def _parse_auth_date(fields: dict[str, str]) -> int:
    try:
        auth_date = int(fields.get("auth_date", ""))
    except ValueError as exc:
        raise InitDataError("Telegram initData auth_date is invalid.") from exc
    if auth_date <= 0:
        raise InitDataError("Telegram initData auth_date is invalid.")
    return auth_date


def _parse_user(fields: dict[str, str]) -> dict[str, Any]:
    try:
        user = json.loads(fields.get("user", ""))
    except json.JSONDecodeError as exc:
        raise InitDataError("Telegram initData user is invalid.") from exc
    if not isinstance(user, dict):
        raise InitDataError("Telegram initData user is invalid.")
    try:
        user_id = int(user.get("id"))
    except (TypeError, ValueError) as exc:
        raise InitDataError("Telegram initData user id is invalid.") from exc
    if user_id <= 0:
        raise InitDataError("Telegram initData user id is invalid.")
    user["id"] = user_id
    return user
