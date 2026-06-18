import json

from starlette.middleware.sessions import SessionMiddleware

from bot.web.platform_runtime import create_platform_app, platform_health_check


def test_platform_app_exposes_platform_routes_without_sqladmin_routes():
    app = create_platform_app()
    paths = {getattr(route, "path", "") for route in app.routes}

    assert "/health" in paths
    assert "/platform/app" in paths
    assert "/platform/api/channels/discover" in paths
    assert "/platform/api/public/reports" in paths
    assert "/admin/login" not in paths
    assert "/export/users" not in paths
    assert any(middleware.cls is SessionMiddleware for middleware in app.user_middleware)


async def test_platform_health_check_reports_database_ok():
    response = await platform_health_check(None)
    payload = json.loads(response.body.decode("utf-8"))

    assert response.status_code == 200
    assert payload["status"] == "healthy"
    assert payload["checks"]["database"] == "ok"
