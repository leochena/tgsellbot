import hashlib
import hmac
import json
from urllib.parse import urlencode

import pytest

from bot.misc.telegram_init_data import InitDataError, validate_telegram_init_data


def make_init_data(user_id: int, token: str = "123:abc", auth_date: int = 1_800_000_000) -> str:
    fields = {
        "auth_date": str(auth_date),
        "query_id": "AAE-test",
        "user": json.dumps({"id": user_id, "first_name": "Test"}, separators=(",", ":")),
    }
    data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(fields.items()))
    secret_key = hmac.new(b"WebAppData", token.encode("utf-8"), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    return urlencode(fields)


class TestTelegramInitData:
    def test_validates_signed_init_data(self):
        auth = validate_telegram_init_data(make_init_data(250001), "123:abc", now=1_800_000_100)

        assert auth.user_id == 250001
        assert auth.user["first_name"] == "Test"

    def test_rejects_tampered_init_data(self):
        init_data = make_init_data(250002).replace("250002", "250003")

        with pytest.raises(InitDataError):
            validate_telegram_init_data(init_data, "123:abc", now=1_800_000_100)

    def test_rejects_expired_init_data(self):
        with pytest.raises(InitDataError):
            validate_telegram_init_data(make_init_data(250004, auth_date=100), "123:abc", now=100_000)
