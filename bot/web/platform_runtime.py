from starlette.applications import Starlette
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import JSONResponse
from starlette.routing import Route
from sqlalchemy import text

from bot.database import Database
from bot.misc import EnvKeys
from bot.misc.caching import get_cache_manager
from bot.misc.metrics import get_metrics
from bot.web.platform import platform_routes


async def platform_health_check(request) -> JSONResponse:
    health_status = {
        "status": "healthy",
        "checks": {},
    }

    try:
        async with Database().session() as session:
            await session.execute(text("SELECT 1"))
        health_status["checks"]["database"] = "ok"
    except Exception:
        health_status["checks"]["database"] = "error"
        health_status["status"] = "unhealthy"

    cache = get_cache_manager()
    if cache:
        health_status["checks"]["redis"] = "ok" if getattr(cache, "_healthy", True) else "degraded"
    else:
        health_status["checks"]["redis"] = "not configured"

    metrics = get_metrics()
    if metrics:
        health_status["checks"]["metrics"] = "ok"
        health_status["uptime"] = metrics.get_metrics_summary()["uptime_seconds"]

    status_code = 200 if health_status["status"] == "healthy" else 503
    return JSONResponse(health_status, status_code=status_code)


def create_platform_app() -> Starlette:
    app = Starlette(routes=[Route("/health", platform_health_check)] + platform_routes)
    app.add_middleware(
        SessionMiddleware,
        secret_key=EnvKeys.SECRET_KEY,
        max_age=max(int(getattr(EnvKeys, "ADMIN_SESSION_MAX_AGE_DAYS", 30)), 1) * 24 * 60 * 60,
    )
    return app
