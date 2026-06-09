import pytest
from unittest.mock import patch


class TestGetLocale:

    def test_valid_locale(self):
        from bot.i18n.main import get_locale, set_current_locale, reset_current_locale
        get_locale.cache_clear()
        token = set_current_locale(None)

        with patch('bot.i18n.main.EnvKeys') as env:
            env.BOT_LOCALE = "ru"
            result = get_locale()
        reset_current_locale(token)
        assert result == "ru"
        get_locale.cache_clear()

    def test_invalid_locale_falls_back(self):
        from bot.i18n.main import get_locale, set_current_locale, reset_current_locale
        get_locale.cache_clear()
        token = set_current_locale(None)

        with patch('bot.i18n.main.EnvKeys') as env:
            env.BOT_LOCALE = "xx"
            result = get_locale()
        reset_current_locale(token)

        from bot.i18n.strings import DEFAULT_LOCALE
        assert result == DEFAULT_LOCALE
        get_locale.cache_clear()

    def test_locale_stripped_and_lowered(self):
        from bot.i18n.main import get_locale, set_current_locale, reset_current_locale
        get_locale.cache_clear()
        token = set_current_locale(None)

        with patch('bot.i18n.main.EnvKeys') as env:
            env.BOT_LOCALE = "  RU  "
            result = get_locale()
        reset_current_locale(token)
        assert result == "ru"
        get_locale.cache_clear()

    def test_current_locale_overrides_default(self):
        from bot.i18n.main import get_locale, reset_current_locale, set_current_locale
        get_locale.cache_clear()

        with patch('bot.i18n.main.EnvKeys') as env:
            env.BOT_LOCALE = "ru"
            token = set_current_locale("en")
            try:
                assert get_locale() == "en"
            finally:
                reset_current_locale(token)
        get_locale.cache_clear()


class TestLocalize:

    def test_existing_key(self):
        from bot.i18n.main import localize, get_locale, set_current_locale, reset_current_locale
        get_locale.cache_clear()
        token = set_current_locale(None)

        with patch('bot.i18n.main.EnvKeys') as env:
            env.BOT_LOCALE = "ru"
            result = localize("btn.shop")

        reset_current_locale(token)
        assert result != "btn.shop"  # Should return the translation, not the key
        get_locale.cache_clear()

    def test_missing_key_returns_key(self):
        from bot.i18n.main import localize, get_locale, set_current_locale, reset_current_locale
        get_locale.cache_clear()
        token = set_current_locale(None)

        with patch('bot.i18n.main.EnvKeys') as env:
            env.BOT_LOCALE = "ru"
            result = localize("nonexistent.key.that.does.not.exist")

        reset_current_locale(token)
        assert result == "nonexistent.key.that.does.not.exist"
        get_locale.cache_clear()

    def test_format_with_kwargs(self):
        from bot.i18n.main import localize, get_locale, set_current_locale, reset_current_locale
        from bot.i18n.strings import TRANSLATIONS
        get_locale.cache_clear()
        token = set_current_locale(None)

        # Find a key that uses format placeholders
        # profile.caption uses {id} and {name}
        with patch('bot.i18n.main.EnvKeys') as env:
            env.BOT_LOCALE = "ru"
            result = localize("profile.caption", id=12345, name="TestUser")

        reset_current_locale(token)
        assert "12345" in result
        assert "TestUser" in result
        get_locale.cache_clear()

    def test_format_error_returns_unformatted(self):
        from bot.i18n.main import localize, get_locale, set_current_locale, reset_current_locale
        get_locale.cache_clear()
        token = set_current_locale(None)

        # profile.caption expects {id} and {name} — pass wrong kwargs
        with patch('bot.i18n.main.EnvKeys') as env:
            env.BOT_LOCALE = "ru"
            result = localize("profile.caption", wrong_key="value")

        reset_current_locale(token)
        # Should return the unformatted template (not crash)
        assert isinstance(result, str)
        get_locale.cache_clear()

    def test_localize_returns_string(self):
        from bot.i18n.main import localize, get_locale, set_current_locale, reset_current_locale
        get_locale.cache_clear()
        token = set_current_locale(None)

        with patch('bot.i18n.main.EnvKeys') as env:
            env.BOT_LOCALE = "ru"
            result = localize("btn.back")

        reset_current_locale(token)
        assert isinstance(result, str)
        assert len(result) > 0
        get_locale.cache_clear()

    def test_localize_uses_current_locale(self):
        from bot.i18n.main import get_locale, localize, reset_current_locale, set_current_locale
        get_locale.cache_clear()

        with patch('bot.i18n.main.EnvKeys') as env:
            env.BOT_LOCALE = "ru"
            token = set_current_locale("en")
            try:
                assert localize("btn.shop") == "🏪 Shop"
            finally:
                reset_current_locale(token)
        get_locale.cache_clear()

    def test_chinese_locale(self):
        from bot.i18n.main import get_locale, localize, reset_current_locale, set_current_locale
        get_locale.cache_clear()

        with patch('bot.i18n.main.EnvKeys') as env:
            env.BOT_LOCALE = "ru"
            token = set_current_locale("zh")
            try:
                assert get_locale() == "zh"
                assert localize("btn.shop") == "🏪 商店"
                assert localize("language.name.zh") == "中文"
            finally:
                reset_current_locale(token)
        get_locale.cache_clear()

    def test_group_welcome_usage_is_localized(self):
        from bot.i18n.main import get_locale, localize, reset_current_locale, set_current_locale
        get_locale.cache_clear()

        with patch('bot.i18n.main.EnvKeys') as env:
            env.BOT_LOCALE = "ru"
            token = set_current_locale("zh")
            try:
                text = localize("group_invite.welcome_usage", name="新用户")
                assert "/签到" in text
                assert "/邀请" in text
                assert "新用户" in text
            finally:
                reset_current_locale(token)
        get_locale.cache_clear()
