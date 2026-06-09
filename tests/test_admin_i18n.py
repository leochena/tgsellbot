import pytest
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
from starlette.requests import Request

import bot.database.models.main  # noqa: F401


def make_request(path: str = "/admin/login", query: bytes = b"", session: dict | None = None) -> Request:
    return Request({
        "type": "http",
        "method": "GET",
        "path": path,
        "query_string": query,
        "headers": [(b"host", b"testserver")],
        "scheme": "http",
        "server": ("testserver", 80),
        "client": ("127.0.0.1", 12345),
        "session": session or {},
    })


class TestAdminI18n:
    def test_session_and_query_locale_selection(self):
        from bot.web.admin_i18n import get_admin_locale

        assert get_admin_locale(make_request(session={"admin_locale": "en"})) == "en"
        assert get_admin_locale(make_request(query=b"lang=zh", session={"admin_locale": "en"})) == "zh"
        assert get_admin_locale(make_request(session={"admin_locale": "xx"})) == "zh"

    def test_language_switch_url_is_local_admin_route(self):
        from bot.web.admin_i18n import admin_set_language_url

        url = admin_set_language_url(make_request("/admin/login"), "en")
        assert url.startswith("/admin/lang?lang=en&next=")
        assert "testserver" in url

    def test_font_size_selection_defaults_and_session(self):
        from bot.web.admin_i18n import get_admin_font_size

        assert get_admin_font_size(make_request()) == 12
        assert get_admin_font_size(make_request(session={"admin_font_size": 16})) == 16
        assert get_admin_font_size(make_request(query=b"size=18", session={"admin_font_size": 16})) == 18
        assert get_admin_font_size(make_request(session={"admin_font_size": 10})) == 12
        assert get_admin_font_size(make_request(query=b"size=xx")) == 12

    def test_font_size_switch_url_is_local_admin_route(self):
        from bot.web.admin_i18n import admin_set_font_size_url

        url = admin_set_font_size_url(make_request("/admin/login"), 16)
        assert url.startswith("/admin/font-size?size=16&next=")
        assert "testserver" in url

    def test_model_names_and_labels_follow_context_locale(self):
        from bot.web.admin import OperationsAdminView, RoleAdmin
        from bot.web.admin_i18n import admin_t, reset_current_admin_locale, set_current_admin_locale

        token = set_current_admin_locale("zh")
        try:
            assert admin_t(OperationsAdminView.name) == "商品运营"
            assert RoleAdmin().column_label("permissions") == "权限"
        finally:
            reset_current_admin_locale(token)

        token = set_current_admin_locale("en")
        try:
            assert admin_t(OperationsAdminView.name) == "Product Operations"
            assert RoleAdmin().column_label("permissions") == "Permissions"
        finally:
            reset_current_admin_locale(token)

    @pytest.mark.asyncio
    async def test_login_template_renders_chinese_and_english(self):
        from bot.web.admin_i18n import (
            admin_set_language_url,
            admin_set_font_size_url,
            admin_t,
            get_admin_font_size,
            get_admin_locale,
            reset_current_admin_locale,
            set_current_admin_locale,
        )

        env = Environment(loader=FileSystemLoader("templates"), enable_async=True)
        env.globals["admin_t"] = admin_t
        env.globals["admin_locale"] = get_admin_locale
        env.globals["admin_language_url"] = admin_set_language_url
        env.globals["admin_font_size"] = get_admin_font_size
        env.globals["admin_font_size_url"] = admin_set_font_size_url
        env.globals["url_for"] = lambda name, **kwargs: f"/{name}"

        class DummyAdmin:
            favicon_url = None
            title = "Telegram Shop Admin"

        template = env.get_template("sqladmin/login.html")

        token = set_current_admin_locale("zh")
        try:
            zh_html = await template.render_async(request=make_request(), admin=DummyAdmin(), error=None)
            assert "Telegram 商店后台" in zh_html
            assert "用户名" in zh_html
            assert "密码" in zh_html
            assert "在本机记住登录" in zh_html
            assert "font-size: 12pt !important;" in zh_html
            assert "字号" in zh_html
            assert "16号" in zh_html
        finally:
            reset_current_admin_locale(token)

        token = set_current_admin_locale("en")
        try:
            en_html = await template.render_async(
                request=make_request(session={"admin_locale": "en", "admin_font_size": 16}),
                admin=DummyAdmin(),
                error=None,
            )
            assert "Telegram Shop Admin" in en_html
            assert "Username" in en_html
            assert "Password" in en_html
            assert "Remember login on this computer" in en_html
            assert "font-size: 16pt !important;" in en_html
            assert "Font size" in en_html
            assert "16pt" in en_html
        finally:
            reset_current_admin_locale(token)

    def test_admin_session_max_age_uses_configured_days(self):
        from unittest.mock import patch

        with patch("bot.web.admin.EnvKeys.ADMIN_SESSION_MAX_AGE_DAYS", 30):
            from bot.web.admin import AdminAuth

            auth = AdminAuth(secret_key="test", max_age=30 * 24 * 60 * 60)

        session_middleware = auth.middlewares[0]
        assert session_middleware.kwargs["max_age"] == 30 * 24 * 60 * 60

    def test_operations_page_replaces_client_switch(self):
        layout = Path("templates/sqladmin/layout.html").read_text(encoding="utf-8")
        operations = Path("templates/sqladmin/operations_embed.html").read_text(encoding="utf-8")

        assert "/client" not in layout
        assert "admin_web.client" not in layout
        assert "/admin/operations/app" in operations
