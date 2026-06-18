import logging
import os
from html import escape
from typing import Any

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNotFound,
)
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.routing import Route

from bot.database.methods.group_invites import (
    get_bot_setting,
    list_group_invite_rewards,
    review_group_invite_reward,
)
from bot.database.methods.read import check_role_name_by_id, check_user
from bot.database.methods.update import record_user_appeal
from bot.database.methods.platform import (
    add_relay_feedback,
    admin_owner_dashboards,
    admin_review_workload_metrics,
    create_channel_claim,
    create_model_test_job,
    create_model_test_report,
    create_relay_claim,
    discover_channels,
    discover_relay_providers,
    get_channel_admin_detail,
    get_channel_claim_review_context,
    get_channel_detail,
    get_model_test_job,
    get_model_test_report,
    get_public_model_test_report,
    get_relay_provider_detail,
    list_channel_claims,
    list_channel_reports,
    list_channel_submissions,
    list_ledger_entries,
    list_fraud_events,
    list_invite_retention_snapshots,
    list_model_test_jobs,
    list_model_test_reports,
    list_platform_audit_logs,
    list_public_model_test_reports,
    list_relay_claims,
    list_relay_feedback,
    list_relay_providers,
    model_test_report_share_token,
    owner_dashboard,
    platform_dashboard_metrics,
    record_channel_interaction,
    review_channel_report,
    review_channel_submission,
    review_fraud_event,
    review_relay_feedback,
    review_relay_provider,
    set_report_visibility,
    submit_channel,
    submit_relay_provider,
    update_channel_owner_profile,
    update_relay_owner_profile,
    verify_channel_claim,
    verify_relay_claim,
)
from bot.misc import EnvKeys
from bot.misc.telegram_init_data import InitDataError, validate_telegram_init_data
from bot.misc.url_safety import UnsafeURL
from bot.model_lab.dispatcher import run_model_test_job_once
from bot.web.admin_i18n import get_admin_font_size

logger = logging.getLogger(__name__)

PLATFORM_REVIEWER_ROLES = {"REVIEWER", "RISK_OPERATOR", "OPERATOR", "ADMIN", "OWNER"}
PLATFORM_RISK_REVIEWER_ROLES = {"RISK_OPERATOR", "OPERATOR", "ADMIN", "OWNER"}
PLATFORM_RISK_STATUSES = {"risk_blocked", "rejected"}
PLATFORM_RISK_ESCALATIONS = {"risk", "urgent"}
MODEL_LAB_WORKER_RUNNER_ENV = "MODEL_LAB_WORKER_RUNNER"


class PlatformAPIError(Exception):
    def __init__(self, message: str, status_code: int = 400, code: str = "bad_request"):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code


def _json_ok(data: dict[str, Any] | None = None, status_code: int = 200) -> JSONResponse:
    return JSONResponse({"ok": True, **(data or {})}, status_code=status_code)


def _json_error(message: str, status_code: int = 400, code: str = "bad_request") -> JSONResponse:
    return JSONResponse({"ok": False, "error": message, "code": code}, status_code=status_code)


def _model_lab_worker_runner() -> str | None:
    value = os.getenv(MODEL_LAB_WORKER_RUNNER_ENV, "").strip()
    return value or None


def _is_authenticated(request: Request) -> bool:
    return bool(request.session.get("authenticated"))


def _request_user_id(request: Request) -> int | None:
    value = request.scope.get("platform_user_id")
    return int(value) if value else None


async def _platform_enabled() -> bool:
    value = (await get_bot_setting("platform_api_enabled", "0")).strip().lower()
    return value in {"1", "true", "yes", "on"}


async def _request_json(request: Request) -> dict[str, Any]:
    try:
        data = await request.json()
    except Exception as exc:
        raise PlatformAPIError("JSON body required.") from exc
    if not isinstance(data, dict):
        raise PlatformAPIError("JSON body must be an object.")
    return data


async def _guard(
        request: Request,
        handler,
        *args,
        admin_only: bool = False,
        reviewer_only: bool = False,
        risk_reviewer_only: bool = False,
):
    try:
        if not await _platform_enabled():
            return _json_error("Platform API disabled", 404, "platform_disabled")
        if not _is_authenticated(request):
            if admin_only and not reviewer_only and not risk_reviewer_only:
                return _json_error("Unauthorized", 401, "unauthorized")
            try:
                auth = validate_telegram_init_data(
                    request.headers.get("x-telegram-init-data", ""),
                    EnvKeys.TOKEN,
                )
            except InitDataError as exc:
                return _json_error(str(exc), 401, "telegram_init_data_invalid")
            request.scope["platform_user_id"] = auth.user_id
            if risk_reviewer_only:
                await _require_platform_role(
                    auth.user_id,
                    PLATFORM_RISK_REVIEWER_ROLES,
                    code="risk_role_required",
                    message="Risk operator role required.",
                )
            elif reviewer_only:
                await _require_platform_role(
                    auth.user_id,
                    PLATFORM_REVIEWER_ROLES,
                    code="reviewer_role_required",
                    message="Reviewer role required.",
                )
        return await handler(request, *args)
    except PermissionError as exc:
        return _json_error(str(exc), 403, "forbidden")
    except (PlatformAPIError, ValueError, UnsafeURL) as exc:
        return _json_error(str(exc), getattr(exc, "status_code", 400), getattr(exc, "code", "bad_request"))
    except Exception:
        logger.exception("Platform API request failed")
        return _json_error("Server error", 500, "server_error")


async def _public_guard(request: Request, handler, *args):
    if not await _platform_enabled():
        return _json_error("Platform API disabled", 404, "platform_disabled")
    try:
        return await handler(request, *args)
    except (PlatformAPIError, ValueError, UnsafeURL) as exc:
        return _json_error(str(exc), getattr(exc, "status_code", 400), getattr(exc, "code", "bad_request"))
    except Exception:
        logger.exception("Platform public API request failed")
        return _json_error("Server error", 500, "server_error")


def _actor_id(request: Request, data: dict[str, Any] | None = None) -> int:
    request_user_id = _request_user_id(request)
    if request_user_id is not None:
        value = (data or {}).get("user_id") or request.query_params.get("user_id") or request.path_params.get("user_id")
        if value in (None, "", 0):
            return request_user_id
        try:
            parsed = int(value)
        except (TypeError, ValueError) as exc:
            raise PlatformAPIError("user_id is required.", 400, "user_id_required") from exc
        if parsed != request_user_id:
            raise PlatformAPIError("Forbidden", 403, "forbidden")
        return parsed

    value = (data or {}).get("user_id") or request.query_params.get("user_id") or request.path_params.get("user_id") or 0
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise PlatformAPIError("user_id is required.", 400, "user_id_required") from exc
    if parsed <= 0:
        raise PlatformAPIError("user_id is required.", 400, "user_id_required")
    return parsed


async def _require_platform_role(actor_id: int, allowed_roles: set[str], *, code: str, message: str) -> int:
    user = await check_user(int(actor_id))
    if not user:
        raise PlatformAPIError(message, 403, code)
    try:
        role_name = await check_role_name_by_id(int(user.get("role_id") or 0))
    except Exception as exc:
        raise PlatformAPIError(message, 403, code) from exc
    if str(role_name or "").upper() not in allowed_roles:
        raise PlatformAPIError(message, 403, code)
    return int(actor_id)


async def _reviewer_actor_id(request: Request, data: dict[str, Any] | None = None) -> int:
    actor_id = _actor_id(request, data)
    return await _require_platform_role(
        actor_id,
        PLATFORM_REVIEWER_ROLES,
        code="reviewer_role_required",
        message="Reviewer role required.",
    )


async def _risk_reviewer_actor_id(request: Request, data: dict[str, Any] | None = None) -> int:
    actor_id = _actor_id(request, data)
    return await _require_platform_role(
        actor_id,
        PLATFORM_RISK_REVIEWER_ROLES,
        code="risk_role_required",
        message="Risk operator role required.",
    )


def _requires_risk_role(*values: Any) -> bool:
    normalized = {str(value or "").strip().lower() for value in values}
    return bool(normalized & (PLATFORM_RISK_STATUSES | PLATFORM_RISK_ESCALATIONS))


def _viewer_id(request: Request) -> int | None:
    request_user_id = _request_user_id(request)
    if request_user_id is not None:
        return request_user_id
    value = request.query_params.get("user_id")
    if value in (None, ""):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise PlatformAPIError("user_id is invalid.", 400, "user_id_invalid") from exc
    return parsed if parsed > 0 else None


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "approved", "approve"}


def _channel_chat_ref(channel: dict[str, Any]) -> int | str:
    chat_id = channel.get("telegram_chat_id")
    if chat_id not in (None, ""):
        return int(chat_id)
    username = str(channel.get("username") or "").strip().lstrip("@")
    if not username:
        raise PlatformAPIError(
            "Channel username or Telegram chat id is required for Bot-admin verification.",
            400,
            "channel_identifier_required",
        )
    return f"@{username}"


def _chat_member_status(member: Any) -> str:
    status = getattr(member, "status", "")
    return str(getattr(status, "value", status) or "").strip().lower()


async def _verify_channel_bot_admin_claim(context: dict[str, Any]) -> dict[str, Any]:
    claim = context["claim"]
    channel = context["channel"]
    claimant_id = int(claim["claimant_id"])
    chat_ref = _channel_chat_ref(channel)
    session = AiohttpSession(proxy=EnvKeys.BOT_PROXY_URL or None)
    try:
        async with Bot(
            token=EnvKeys.TOKEN,
            default=DefaultBotProperties(parse_mode="HTML"),
            session=session,
        ) as bot:
            member = await bot.get_chat_member(chat_id=chat_ref, user_id=claimant_id)
    except (TelegramBadRequest, TelegramForbiddenError, TelegramNotFound) as exc:
        raise PlatformAPIError(
            "Bot-admin verification failed. Confirm the bot can access the channel and the claimant is an admin.",
            409,
            "bot_admin_verification_failed",
        ) from exc
    except TelegramAPIError as exc:
        raise PlatformAPIError(
            "Telegram Bot API verification is unavailable.",
            502,
            "telegram_verification_unavailable",
        ) from exc

    status = _chat_member_status(member)
    if status not in {"administrator", "creator"}:
        raise PlatformAPIError(
            "Claimant is not a Telegram channel administrator.",
            409,
            "bot_admin_verification_failed",
        )
    return {
        "verified": True,
        "channel_id": int(claim["channel_id"]),
        "claimant_id": claimant_id,
        "telegram_chat": str(chat_ref),
        "telegram_status": status,
        "can_post_messages": bool(getattr(member, "can_post_messages", False)),
    }


def _report_share_secret() -> str:
    return str(getattr(EnvKeys, "SECRET_KEY", "") or getattr(EnvKeys, "TOKEN", ""))


def _attach_report_share_token(report: dict[str, Any] | None) -> dict[str, Any] | None:
    if not report:
        return report
    if report.get("visibility") == "unlisted":
        report["share_token"] = model_test_report_share_token(
            int(report["id"]),
            int(report["user_id"]),
            int(report["job_id"]),
            _report_share_secret(),
        )
    else:
        report["share_token"] = ""
    return report


async def api_ledger_impl(request: Request):
    user_id = _actor_id(request)
    rows = await list_ledger_entries(
        user_id=user_id,
        account_type=request.query_params.get("account_type", ""),
        limit=int(request.query_params.get("limit", "50")),
        offset=int(request.query_params.get("offset", "0")),
    )
    return _json_ok({"ledger": rows})


async def api_owner_dashboard_impl(request: Request):
    return _json_ok({"dashboard": await owner_dashboard(_actor_id(request))})


async def api_submit_channel_impl(request: Request):
    data = await _request_json(request)
    result = await submit_channel(data, _actor_id(request, data))
    return _json_ok({"result": result}, 201)


async def api_discover_channels_impl(request: Request):
    result = await discover_channels(
        query=request.query_params.get("q", ""),
        category=request.query_params.get("category", ""),
        language=request.query_params.get("language", ""),
        limit=int(request.query_params.get("limit", "20")),
        offset=int(request.query_params.get("offset", "0")),
    )
    return _json_ok(result)


async def api_channel_detail_impl(request: Request):
    result = await get_channel_detail(
        int(request.path_params["channel_id"]),
        user_id=_viewer_id(request),
    )
    if not result:
        return _json_error("Channel not found", 404, "channel_not_found")
    return _json_ok({"result": result})


async def api_admin_channel_submissions_impl(request: Request):
    rows = await list_channel_submissions(
        status=request.query_params.get("status", ""),
        limit=int(request.query_params.get("limit", "50")),
        offset=int(request.query_params.get("offset", "0")),
    )
    return _json_ok(rows)


async def api_admin_channel_detail_impl(request: Request):
    result = await get_channel_admin_detail(int(request.path_params["channel_id"]))
    if not result:
        return _json_error("Channel not found", 404, "channel_not_found")
    return _json_ok({"result": result})


async def api_admin_channel_review_impl(request: Request):
    data = await _request_json(request)
    actor_id = await (
        _risk_reviewer_actor_id(request, data)
        if _requires_risk_role(data.get("status"))
        else _reviewer_actor_id(request, data)
    )
    ok = await review_channel_submission(
        int(request.path_params["submission_id"]),
        reviewer_id=actor_id,
        status=str(data.get("status") or ""),
        notes=str(data.get("notes") or ""),
    )
    if not ok:
        return _json_error("Channel submission not found", 404, "submission_not_found")
    return _json_ok()


async def api_channel_interaction_impl(request: Request):
    data = await _request_json(request)
    result = await record_channel_interaction(
        user_id=_actor_id(request, data),
        channel_id=int(request.path_params["channel_id"]),
        action=str(data.get("action") or ""),
        source=str(data.get("source") or ""),
    )
    return _json_ok({"result": result}, 201)


async def api_channel_claim_impl(request: Request):
    data = await _request_json(request)
    result = await create_channel_claim(
        int(request.path_params["channel_id"]),
        _actor_id(request, data),
        method=str(data.get("method") or "challenge"),
    )
    return _json_ok({"result": result}, 201)


async def api_channel_claim_review_impl(request: Request):
    data = await _request_json(request)
    actor_id = await _reviewer_actor_id(request, data)
    claim_id = int(request.path_params["claim_id"])
    approved = _as_bool(data.get("approved"))
    bot_admin_verification = None
    if approved:
        context = await get_channel_claim_review_context(claim_id)
        if not context:
            return _json_error("Channel claim not found", 404, "claim_not_found")
        if context["claim"]["method"] == "bot_admin":
            bot_admin_verification = await _verify_channel_bot_admin_claim(context)
    ok = await verify_channel_claim(
        claim_id,
        reviewer_id=actor_id,
        approved=approved,
        notes=str(data.get("notes") or ""),
        bot_admin_verification=bot_admin_verification,
    )
    if not ok:
        return _json_error("Channel claim not found", 404, "claim_not_found")
    return _json_ok()


async def api_admin_channel_claims_impl(request: Request):
    rows = await list_channel_claims(
        status=request.query_params.get("status", ""),
        limit=int(request.query_params.get("limit", "50")),
        offset=int(request.query_params.get("offset", "0")),
    )
    return _json_ok(rows)


async def api_admin_channel_reports_impl(request: Request):
    rows = await list_channel_reports(
        status=request.query_params.get("status", ""),
        assigned_to=request.query_params.get("assigned_to", ""),
        reviewed_by=request.query_params.get("reviewed_by", ""),
        escalation=request.query_params.get("escalation", ""),
        limit=int(request.query_params.get("limit", "50")),
        offset=int(request.query_params.get("offset", "0")),
    )
    return _json_ok(rows)


async def api_admin_channel_report_review_impl(request: Request):
    data = await _request_json(request)
    actor_id = await (
        _risk_reviewer_actor_id(request, data)
        if _requires_risk_role(data.get("risk_status") or data.get("status"), data.get("escalation"))
        else _reviewer_actor_id(request, data)
    )
    ok = await review_channel_report(
        int(request.path_params["channel_id"]),
        reviewer_id=actor_id,
        risk_status=str(data.get("risk_status") or data.get("status") or ""),
        notes=str(data.get("notes") or ""),
        assigned_to=data.get("assigned_to"),
        escalation=str(data.get("escalation") or "none"),
    )
    if not ok:
        return _json_error("Channel report not found", 404, "channel_report_not_found")
    return _json_ok()


async def api_channel_owner_profile_impl(request: Request):
    data = await _request_json(request)
    result = await update_channel_owner_profile(
        int(request.path_params["channel_id"]),
        owner_id=_actor_id(request, data),
        data=data,
    )
    if not result:
        return _json_error("Channel not found", 404, "channel_not_found")
    return _json_ok({"result": result})


async def api_submit_relay_impl(request: Request):
    data = await _request_json(request)
    result = await submit_relay_provider(data, _actor_id(request, data))
    return _json_ok({"result": result}, 201)


async def api_discover_relays_impl(request: Request):
    result = await discover_relay_providers(
        query=request.query_params.get("q", ""),
        protocol=request.query_params.get("protocol", ""),
        region=request.query_params.get("region", ""),
        limit=int(request.query_params.get("limit", "20")),
        offset=int(request.query_params.get("offset", "0")),
    )
    return _json_ok(result)


async def api_relay_detail_impl(request: Request):
    result = await get_relay_provider_detail(
        int(request.path_params["provider_id"]),
        user_id=_viewer_id(request),
    )
    if not result:
        return _json_error("Relay provider not found", 404, "provider_not_found")
    return _json_ok({"result": result})


async def api_admin_relays_impl(request: Request):
    rows = await list_relay_providers(
        status=request.query_params.get("status", ""),
        limit=int(request.query_params.get("limit", "50")),
        offset=int(request.query_params.get("offset", "0")),
    )
    return _json_ok(rows)


async def api_admin_relay_detail_impl(request: Request):
    result = await get_relay_provider_detail(int(request.path_params["provider_id"]))
    if not result:
        return _json_error("Relay provider not found", 404, "provider_not_found")
    return _json_ok({"result": result})


async def api_admin_relay_review_impl(request: Request):
    data = await _request_json(request)
    actor_id = await (
        _risk_reviewer_actor_id(request, data)
        if _requires_risk_role(data.get("status"), data.get("risk_status"))
        else _reviewer_actor_id(request, data)
    )
    ok = await review_relay_provider(
        int(request.path_params["provider_id"]),
        reviewer_id=actor_id,
        status=str(data.get("status") or ""),
        risk_status=str(data.get("risk_status") or ""),
        notes=str(data.get("notes") or ""),
    )
    if not ok:
        return _json_error("Relay provider not found", 404, "provider_not_found")
    return _json_ok()


async def api_relay_owner_profile_impl(request: Request):
    data = await _request_json(request)
    result = await update_relay_owner_profile(
        int(request.path_params["provider_id"]),
        owner_id=_actor_id(request, data),
        data=data,
    )
    if not result:
        return _json_error("Relay provider not found", 404, "provider_not_found")
    return _json_ok({"result": result})


async def api_relay_claim_impl(request: Request):
    data = await _request_json(request)
    result = await create_relay_claim(
        int(request.path_params["provider_id"]),
        _actor_id(request, data),
        method=str(data.get("method") or "challenge"),
    )
    return _json_ok({"result": result}, 201)


async def api_relay_claim_review_impl(request: Request):
    data = await _request_json(request)
    actor_id = await _reviewer_actor_id(request, data)
    ok = await verify_relay_claim(
        int(request.path_params["claim_id"]),
        reviewer_id=actor_id,
        approved=_as_bool(data.get("approved")),
        notes=str(data.get("notes") or ""),
    )
    if not ok:
        return _json_error("Relay claim not found", 404, "claim_not_found")
    return _json_ok()


async def api_admin_relay_claims_impl(request: Request):
    rows = await list_relay_claims(
        status=request.query_params.get("status", ""),
        limit=int(request.query_params.get("limit", "50")),
        offset=int(request.query_params.get("offset", "0")),
    )
    return _json_ok(rows)


async def api_relay_feedback_impl(request: Request):
    data = await _request_json(request)
    result = await add_relay_feedback(
        provider_id=int(request.path_params["provider_id"]),
        user_id=_actor_id(request, data),
        feedback_type=str(data.get("feedback_type") or "rating"),
        text=str(data.get("text") or ""),
        rating=data.get("rating"),
    )
    return _json_ok({"result": result}, 201)


async def api_admin_relay_feedback_impl(request: Request):
    rows = await list_relay_feedback(
        status=request.query_params.get("status", ""),
        feedback_type=request.query_params.get("feedback_type", ""),
        outcome=request.query_params.get("outcome", ""),
        assigned_to=request.query_params.get("assigned_to", ""),
        reviewed_by=request.query_params.get("reviewed_by", ""),
        escalation=request.query_params.get("escalation", ""),
        followup_state=request.query_params.get("followup_state", ""),
        limit=int(request.query_params.get("limit", "50")),
        offset=int(request.query_params.get("offset", "0")),
    )
    return _json_ok(rows)


async def api_admin_relay_feedback_review_impl(request: Request):
    data = await _request_json(request)
    actor_id = await (
        _risk_reviewer_actor_id(request, data)
        if _requires_risk_role(data.get("status"), data.get("escalation"), data.get("outcome"))
        else _reviewer_actor_id(request, data)
    )
    ok = await review_relay_feedback(
        int(request.path_params["feedback_id"]),
        reviewer_id=actor_id,
        status=str(data.get("status") or ""),
        notes=str(data.get("notes") or ""),
        assigned_to=data.get("assigned_to"),
        escalation=str(data.get("escalation") or "none"),
        outcome=str(data.get("outcome") or "none"),
        followup_notes=str(data.get("followup_notes") or ""),
    )
    if not ok:
        return _json_error("Relay feedback not found", 404, "feedback_not_found")
    return _json_ok()


async def api_admin_dashboard_impl(request: Request):
    return _json_ok({"dashboard": await platform_dashboard_metrics()})


async def api_admin_owner_dashboards_impl(request: Request):
    return _json_ok(await admin_owner_dashboards(
        limit=int(request.query_params.get("limit", "50")),
        offset=int(request.query_params.get("offset", "0")),
    ))


async def api_admin_review_workload_impl(request: Request):
    return _json_ok({"workload": await admin_review_workload_metrics()})


async def api_admin_audit_logs_impl(request: Request):
    rows = await list_platform_audit_logs(
        action=request.query_params.get("action", ""),
        resource_type=request.query_params.get("resource_type", ""),
        resource_id=request.query_params.get("resource_id", ""),
        user_id=request.query_params.get("user_id"),
        level=request.query_params.get("level", ""),
        query=request.query_params.get("q", ""),
        limit=int(request.query_params.get("limit", "50")),
        offset=int(request.query_params.get("offset", "0")),
    )
    return _json_ok(rows)


async def api_user_appeal_impl(request: Request):
    data = await _request_json(request)
    user_id = _actor_id(request, data)
    reason = str(data.get("reason") or "").strip()
    if not reason:
        raise PlatformAPIError("reason is required.", 400, "reason_required")
    result = await record_user_appeal(
        user_id,
        reason=reason,
        source=str(data.get("source") or "mini_app"),
        evidence=data.get("evidence") if isinstance(data.get("evidence"), dict) else None,
        dedupe_key=str(data.get("dedupe_key") or ""),
    )
    return _json_ok({"result": result}, 200 if result.get("duplicate") else 201)


async def api_admin_fraud_events_impl(request: Request):
    rows = await list_fraud_events(
        event_type=request.query_params.get("event_type", ""),
        status=request.query_params.get("status", ""),
        limit=int(request.query_params.get("limit", "50")),
        offset=int(request.query_params.get("offset", "0")),
    )
    return _json_ok(rows)


async def api_admin_invite_retention_impl(request: Request):
    rows = await list_invite_retention_snapshots(
        limit=int(request.query_params.get("limit", "50")),
        offset=int(request.query_params.get("offset", "0")),
    )
    return _json_ok(rows)


async def api_admin_invite_rewards_impl(request: Request):
    rows = await list_group_invite_rewards(
        status=request.query_params.get("status", ""),
        chat_id=request.query_params.get("chat_id", ""),
        limit=int(request.query_params.get("limit", "50")),
        offset=int(request.query_params.get("offset", "0")),
    )
    return _json_ok(rows)


async def api_admin_invite_reward_review_impl(request: Request):
    data = await _request_json(request)
    actor_id = await (
        _risk_reviewer_actor_id(request, data)
        if _requires_risk_role(data.get("status"))
        else _reviewer_actor_id(request, data)
    )
    ok = await review_group_invite_reward(
        int(request.path_params["reward_id"]),
        reviewer_id=actor_id,
        status=str(data.get("status") or ""),
        risk_score=data.get("risk_score"),
        risk_reason=str(data.get("risk_reason") or ""),
        notes=str(data.get("notes") or ""),
    )
    if not ok:
        return _json_error("Invite reward not found", 404, "invite_reward_not_found")
    return _json_ok()


async def api_admin_fraud_event_review_impl(request: Request):
    data = await _request_json(request)
    actor_id = await _risk_reviewer_actor_id(request, data)
    ok = await review_fraud_event(
        int(request.path_params["event_id"]),
        reviewer_id=actor_id,
        status=str(data.get("status") or ""),
        notes=str(data.get("notes") or ""),
    )
    if not ok:
        return _json_error("Fraud event not found", 404, "fraud_event_not_found")
    return _json_ok()


async def api_create_model_test_impl(request: Request):
    data = await _request_json(request)
    if data.get("run_now") is True:
        api_key = str(data.get("api_key") or "")
        if not api_key:
            raise PlatformAPIError("api_key is required for run_now.", 400, "api_key_required")
        worker_runner = _model_lab_worker_runner()
        if not worker_runner:
            raise PlatformAPIError(
                "Isolated model worker runner is required for run_now.",
                503,
                "model_worker_runner_required",
            )
    else:
        worker_runner = None

    result = await create_model_test_job(data, _actor_id(request, data))
    if data.get("run_now") is True:
        await run_model_test_job_once(
            int(result["id"]),
            api_key,
            worker_id=f"miniapp:{result['id']}",
            worker_runner=worker_runner,
        )
        loaded = await get_model_test_job(int(result["id"]), user_id=int(result["user_id"]))
        result = loaded or result
    return _json_ok({"result": result}, 201)


async def api_get_model_test_impl(request: Request):
    result = await get_model_test_job(
        int(request.path_params["job_id"]),
        user_id=_actor_id(request),
    )
    if not result:
        return _json_error("Test job not found", 404, "job_not_found")
    return _json_ok({"result": result})


async def api_list_model_tests_impl(request: Request):
    result = await list_model_test_jobs(
        user_id=_actor_id(request),
        status=request.query_params.get("status", ""),
        limit=int(request.query_params.get("limit", "20")),
        offset=int(request.query_params.get("offset", "0")),
    )
    return _json_ok(result)


async def api_create_report_impl(request: Request):
    data = await _request_json(request)
    user_id = _request_user_id(request)
    if user_id is not None:
        job = await get_model_test_job(int(request.path_params["job_id"]), user_id=user_id)
        if not job:
            return _json_error("Test job not found", 404, "job_not_found")
    result = await create_model_test_report(int(request.path_params["job_id"]), data)
    return _json_ok({"result": result}, 201)


async def api_get_report_impl(request: Request):
    result = await get_model_test_report(
        int(request.path_params["report_id"]),
        user_id=_actor_id(request),
    )
    if not result:
        return _json_error("Report not found", 404, "report_not_found")
    _attach_report_share_token(result)
    return _json_ok({"result": result})


async def api_list_reports_impl(request: Request):
    result = await list_model_test_reports(
        user_id=_actor_id(request),
        visibility=request.query_params.get("visibility", ""),
        limit=int(request.query_params.get("limit", "20")),
        offset=int(request.query_params.get("offset", "0")),
    )
    for report in result.get("reports", []):
        _attach_report_share_token(report)
    return _json_ok(result)


async def api_public_report_impl(request: Request):
    result = await get_public_model_test_report(
        int(request.path_params["report_id"]),
        share_token=request.query_params.get("token", ""),
        token_secret=_report_share_secret(),
    )
    if not result:
        return _json_error("Report not found", 404, "report_not_found")
    return _json_ok({"result": result})


async def api_public_reports_impl(request: Request):
    result = await list_public_model_test_reports(
        limit=int(request.query_params.get("limit", "20")),
        offset=int(request.query_params.get("offset", "0")),
        token_secret=_report_share_secret(),
    )
    return _json_ok(result)


async def api_report_visibility_impl(request: Request):
    data = await _request_json(request)
    user_id = _actor_id(request, data)
    if _request_user_id(request) is not None:
        report = await get_model_test_report(int(request.path_params["report_id"]), user_id=user_id)
        if not report:
            return _json_error("Report not found", 404, "report_not_found")
    ok = await set_report_visibility(
        int(request.path_params["report_id"]),
        str(data.get("visibility") or ""),
        user_id=user_id,
    )
    if not ok:
        return _json_error("Report not found", 404, "report_not_found")
    return _json_ok()


async def api_submit_channel(request: Request):
    return await _guard(request, api_submit_channel_impl)


async def api_ledger(request: Request):
    return await _guard(request, api_ledger_impl)


async def api_owner_dashboard(request: Request):
    return await _guard(request, api_owner_dashboard_impl)


async def api_discover_channels(request: Request):
    return await _guard(request, api_discover_channels_impl)


async def api_channel_detail(request: Request):
    return await _guard(request, api_channel_detail_impl)


async def api_admin_channel_submissions(request: Request):
    return await _guard(request, api_admin_channel_submissions_impl, admin_only=True, reviewer_only=True)


async def api_admin_channel_detail(request: Request):
    return await _guard(request, api_admin_channel_detail_impl, admin_only=True, reviewer_only=True)


async def api_admin_channel_review(request: Request):
    return await _guard(request, api_admin_channel_review_impl, admin_only=True, reviewer_only=True)


async def api_channel_interaction(request: Request):
    return await _guard(request, api_channel_interaction_impl)


async def api_channel_claim(request: Request):
    return await _guard(request, api_channel_claim_impl)


async def api_channel_claim_review(request: Request):
    return await _guard(request, api_channel_claim_review_impl, admin_only=True, reviewer_only=True)


async def api_admin_channel_claims(request: Request):
    return await _guard(request, api_admin_channel_claims_impl, admin_only=True, reviewer_only=True)


async def api_admin_channel_reports(request: Request):
    return await _guard(request, api_admin_channel_reports_impl, admin_only=True, reviewer_only=True)


async def api_admin_channel_report_review(request: Request):
    return await _guard(request, api_admin_channel_report_review_impl, admin_only=True, reviewer_only=True)


async def api_channel_owner_profile(request: Request):
    return await _guard(request, api_channel_owner_profile_impl)


async def api_submit_relay(request: Request):
    return await _guard(request, api_submit_relay_impl)


async def api_discover_relays(request: Request):
    return await _guard(request, api_discover_relays_impl)


async def api_relay_detail(request: Request):
    return await _guard(request, api_relay_detail_impl)


async def api_admin_relays(request: Request):
    return await _guard(request, api_admin_relays_impl, admin_only=True, reviewer_only=True)


async def api_admin_relay_detail(request: Request):
    return await _guard(request, api_admin_relay_detail_impl, admin_only=True, reviewer_only=True)


async def api_admin_relay_review(request: Request):
    return await _guard(request, api_admin_relay_review_impl, admin_only=True, reviewer_only=True)


async def api_relay_owner_profile(request: Request):
    return await _guard(request, api_relay_owner_profile_impl)


async def api_relay_claim(request: Request):
    return await _guard(request, api_relay_claim_impl)


async def api_relay_claim_review(request: Request):
    return await _guard(request, api_relay_claim_review_impl, admin_only=True, reviewer_only=True)


async def api_admin_relay_claims(request: Request):
    return await _guard(request, api_admin_relay_claims_impl, admin_only=True, reviewer_only=True)


async def api_relay_feedback(request: Request):
    return await _guard(request, api_relay_feedback_impl)


async def api_admin_relay_feedback(request: Request):
    return await _guard(request, api_admin_relay_feedback_impl, admin_only=True, reviewer_only=True)


async def api_admin_relay_feedback_review(request: Request):
    return await _guard(request, api_admin_relay_feedback_review_impl, admin_only=True, reviewer_only=True)


async def api_admin_dashboard(request: Request):
    return await _guard(request, api_admin_dashboard_impl, admin_only=True)


async def api_admin_owner_dashboards(request: Request):
    return await _guard(request, api_admin_owner_dashboards_impl, admin_only=True)


async def api_admin_review_workload(request: Request):
    return await _guard(request, api_admin_review_workload_impl, admin_only=True, reviewer_only=True)


async def api_admin_audit_logs(request: Request):
    return await _guard(request, api_admin_audit_logs_impl, admin_only=True)


async def api_user_appeal(request: Request):
    return await _guard(request, api_user_appeal_impl)


async def api_admin_fraud_events(request: Request):
    return await _guard(request, api_admin_fraud_events_impl, admin_only=True)


async def api_admin_invite_retention(request: Request):
    return await _guard(request, api_admin_invite_retention_impl, admin_only=True)


async def api_admin_invite_rewards(request: Request):
    return await _guard(request, api_admin_invite_rewards_impl, admin_only=True)


async def api_admin_invite_reward_review(request: Request):
    return await _guard(request, api_admin_invite_reward_review_impl, admin_only=True)


async def api_admin_fraud_event_review(request: Request):
    return await _guard(request, api_admin_fraud_event_review_impl, admin_only=True)


async def api_create_model_test(request: Request):
    return await _guard(request, api_create_model_test_impl)


async def api_get_model_test(request: Request):
    return await _guard(request, api_get_model_test_impl)


async def api_list_model_tests(request: Request):
    return await _guard(request, api_list_model_tests_impl)


async def api_create_report(request: Request):
    return await _guard(request, api_create_report_impl)


async def api_get_report(request: Request):
    return await _guard(request, api_get_report_impl)


async def api_list_reports(request: Request):
    return await _guard(request, api_list_reports_impl)


async def api_public_report(request: Request):
    return await _public_guard(request, api_public_report_impl)


async def api_public_reports(request: Request):
    return await _public_guard(request, api_public_reports_impl)


async def api_report_visibility(request: Request):
    return await _guard(request, api_report_visibility_impl)


async def platform_review_app_page(request: Request):
    if not _is_authenticated(request):
        return RedirectResponse("/admin/login", status_code=302)
    return HTMLResponse(_platform_review_html(font_size=get_admin_font_size(request)))


def _platform_review_html(font_size: int | None = None) -> str:
    return PLATFORM_REVIEW_HTML.replace("__ADMIN_FONT_SIZE__", escape(str(font_size or 12)))


async def platform_mini_app_page(request: Request):
    return HTMLResponse(PLATFORM_MINI_APP_HTML)


async def platform_public_report_page(request: Request):
    return HTMLResponse(PLATFORM_PUBLIC_REPORT_HTML)


platform_routes = [
    Route("/admin/platform/review/app", platform_review_app_page, methods=["GET"]),
    Route("/platform/app", platform_mini_app_page, methods=["GET"]),
    Route("/platform/api/users/{user_id:int}/ledger", api_ledger, methods=["GET"]),
    Route("/platform/api/owner/dashboard", api_owner_dashboard, methods=["GET"]),
    Route("/platform/api/channels/submissions", api_submit_channel, methods=["POST"]),
    Route("/platform/api/channels/discover", api_discover_channels, methods=["GET"]),
    Route("/platform/api/channels/{channel_id:int}", api_channel_detail, methods=["GET"]),
    Route("/platform/api/admin/channels/submissions", api_admin_channel_submissions, methods=["GET"]),
    Route("/platform/api/admin/channels/{channel_id:int}", api_admin_channel_detail, methods=["GET"]),
    Route("/platform/api/admin/channels/submissions/{submission_id:int}/review", api_admin_channel_review, methods=["POST"]),
    Route("/platform/api/channels/{channel_id:int}/interactions", api_channel_interaction, methods=["POST"]),
    Route("/platform/api/channels/{channel_id:int}/claim", api_channel_claim, methods=["POST"]),
    Route("/platform/api/admin/channel-claims", api_admin_channel_claims, methods=["GET"]),
    Route("/platform/api/channel-claims/{claim_id:int}/review", api_channel_claim_review, methods=["POST"]),
    Route("/platform/api/admin/channel-reports", api_admin_channel_reports, methods=["GET"]),
    Route("/platform/api/admin/channels/{channel_id:int}/report-review", api_admin_channel_report_review, methods=["POST"]),
    Route("/platform/api/channels/{channel_id:int}/owner-profile", api_channel_owner_profile, methods=["POST"]),
    Route("/platform/api/relays", api_submit_relay, methods=["POST"]),
    Route("/platform/api/relays/discover", api_discover_relays, methods=["GET"]),
    Route("/platform/api/relays/{provider_id:int}", api_relay_detail, methods=["GET"]),
    Route("/platform/api/admin/relays", api_admin_relays, methods=["GET"]),
    Route("/platform/api/admin/relays/{provider_id:int}", api_admin_relay_detail, methods=["GET"]),
    Route("/platform/api/admin/relays/{provider_id:int}/review", api_admin_relay_review, methods=["POST"]),
    Route("/platform/api/relays/{provider_id:int}/owner-profile", api_relay_owner_profile, methods=["POST"]),
    Route("/platform/api/relays/{provider_id:int}/claim", api_relay_claim, methods=["POST"]),
    Route("/platform/api/admin/relay-claims", api_admin_relay_claims, methods=["GET"]),
    Route("/platform/api/relay-claims/{claim_id:int}/review", api_relay_claim_review, methods=["POST"]),
    Route("/platform/api/relays/{provider_id:int}/feedback", api_relay_feedback, methods=["POST"]),
    Route("/platform/api/admin/relay-feedback", api_admin_relay_feedback, methods=["GET"]),
    Route("/platform/api/admin/relay-feedback/{feedback_id:int}/review", api_admin_relay_feedback_review, methods=["POST"]),
    Route("/platform/api/admin/dashboard", api_admin_dashboard, methods=["GET"]),
    Route("/platform/api/admin/owners/dashboard", api_admin_owner_dashboards, methods=["GET"]),
    Route("/platform/api/admin/review-workload", api_admin_review_workload, methods=["GET"]),
    Route("/platform/api/admin/audit-logs", api_admin_audit_logs, methods=["GET"]),
    Route("/platform/api/users/{user_id:int}/appeals", api_user_appeal, methods=["POST"]),
    Route("/platform/api/admin/fraud-events", api_admin_fraud_events, methods=["GET"]),
    Route("/platform/api/admin/invite-retention", api_admin_invite_retention, methods=["GET"]),
    Route("/platform/api/admin/invite-rewards", api_admin_invite_rewards, methods=["GET"]),
    Route("/platform/api/admin/invite-rewards/{reward_id:int}/review", api_admin_invite_reward_review, methods=["POST"]),
    Route("/platform/api/admin/fraud-events/{event_id:int}/review", api_admin_fraud_event_review, methods=["POST"]),
    Route("/platform/api/relay-tests", api_create_model_test, methods=["POST"]),
    Route("/platform/api/relay-tests", api_list_model_tests, methods=["GET"]),
    Route("/platform/api/relay-tests/{job_id:int}", api_get_model_test, methods=["GET"]),
    Route("/platform/api/relay-tests/{job_id:int}/reports", api_create_report, methods=["POST"]),
    Route("/platform/api/reports/{report_id:int}", api_get_report, methods=["GET"]),
    Route("/platform/api/reports", api_list_reports, methods=["GET"]),
    Route("/platform/api/reports/{report_id:int}/visibility", api_report_visibility, methods=["POST"]),
    Route("/platform/api/public/reports/{report_id:int}", api_public_report, methods=["GET"]),
    Route("/platform/api/public/reports", api_public_reports, methods=["GET"]),
    Route("/platform/reports", platform_public_report_page, methods=["GET"]),
    Route("/platform/reports/{report_id:int}", platform_public_report_page, methods=["GET"]),
]


PLATFORM_REVIEW_HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>TGSellBot Platform Review</title>
  <style>
    :root {
      color-scheme: light;
      font-size: __ADMIN_FONT_SIZE__pt;
      --bg: #f6f7f8;
      --panel: #ffffff;
      --line: #d7dde5;
      --text: #17202a;
      --muted: #657184;
      --accent: #00796b;
      --danger: #b42318;
      --warn: #9a6700;
      --ok: #1a7f37;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font: 1rem/1.45 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    button,
    input,
    select,
    textarea {
      font: inherit;
    }
    button {
      border: 1px solid var(--line);
      background: #fff;
      color: var(--text);
      min-height: 2rem;
      padding: .3rem .6rem;
      border-radius: 6px;
      cursor: pointer;
    }
    button.primary { background: var(--accent); border-color: var(--accent); color: #fff; }
    button.danger { border-color: #f3b6ad; color: var(--danger); }
    button.warn { border-color: #e7c66d; color: var(--warn); }
    button:disabled { cursor: wait; opacity: .55; }
    input,
    select,
    textarea {
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
      color: var(--text);
      min-height: 2rem;
      padding: .3rem .5rem;
    }
    textarea {
      width: 100%;
      min-width: 12rem;
      min-height: 4.4rem;
      resize: vertical;
    }
    .shell {
      max-width: 1280px;
      margin: 0 auto;
      padding: 1rem;
    }
    .topbar {
      display: flex;
      align-items: end;
      justify-content: space-between;
      gap: 1rem;
      margin-bottom: 1rem;
    }
    h1 {
      margin: 0;
      font-size: 1.35rem;
      line-height: 1.2;
      letter-spacing: 0;
    }
    .toolbar {
      display: flex;
      align-items: end;
      gap: .75rem;
      flex-wrap: wrap;
    }
    label {
      display: grid;
      gap: .25rem;
      color: var(--muted);
      font-size: .82rem;
      font-weight: 600;
    }
    .tabs {
      display: flex;
      flex-wrap: wrap;
      gap: .4rem;
      border-bottom: 1px solid var(--line);
      margin-bottom: 1rem;
    }
    .tab {
      border-bottom-left-radius: 0;
      border-bottom-right-radius: 0;
      border-bottom-color: transparent;
    }
    .tab.active {
      background: #eaf4f2;
      border-color: var(--accent);
      color: #035c52;
    }
    .section {
      display: none;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      overflow: hidden;
    }
    .section.active { display: block; }
    .section-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 1rem;
      padding: .8rem;
      border-bottom: 1px solid var(--line);
      background: #fbfcfd;
    }
    .section-title {
      font-size: 1rem;
      font-weight: 700;
    }
    .section-tools {
      display: flex;
      align-items: end;
      flex-wrap: wrap;
      gap: .5rem;
    }
    .state {
      color: var(--muted);
      font-size: .9rem;
      padding: .65rem .8rem;
      border-bottom: 1px solid var(--line);
    }
    .state.error { color: var(--danger); }
    .detail-panel {
      display: none;
      padding: .8rem;
      border-bottom: 1px solid var(--line);
      background: #fbfcfd;
    }
    .detail-panel.active { display: block; }
    .detail-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(16rem, 1fr));
      gap: .75rem;
    }
    .detail-block {
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
      padding: .7rem;
    }
    .detail-block h3 {
      margin: 0 0 .45rem;
      font-size: .9rem;
    }
    .table-wrap { overflow-x: auto; }
    table {
      width: 100%;
      min-width: 960px;
      border-collapse: collapse;
    }
    th,
    td {
      vertical-align: top;
      padding: .65rem .7rem;
      border-bottom: 1px solid var(--line);
      text-align: left;
    }
    th {
      background: #f4f6f8;
      color: var(--muted);
      font-size: .78rem;
      text-transform: uppercase;
      letter-spacing: 0;
    }
    tr:last-child td { border-bottom: 0; }
    .mono { font-family: ui-monospace, SFMono-Regular, Consolas, "Liberation Mono", monospace; }
    .muted { color: var(--muted); }
    .status {
      display: inline-block;
      min-width: 5.8rem;
      padding: .12rem .45rem;
      border-radius: 999px;
      border: 1px solid var(--line);
      background: #fff;
      text-align: center;
      font-size: .78rem;
      white-space: nowrap;
    }
    .status.approved { color: var(--ok); border-color: #9bd6aa; background: #eef9f1; }
    .status.rejected,
    .status.risk_blocked { color: var(--danger); border-color: #f3b6ad; background: #fff5f4; }
    .row-title {
      font-weight: 700;
      word-break: break-word;
    }
    .row-meta {
      color: var(--muted);
      font-size: .82rem;
      margin-top: .15rem;
      word-break: break-word;
    }
    .actions {
      display: flex;
      flex-wrap: wrap;
      gap: .35rem;
      min-width: 13rem;
    }
    .note-cell { width: 18rem; }
    @media (max-width: 760px) {
      .shell { padding: .75rem; }
      .topbar,
      .section-header {
        align-items: stretch;
        flex-direction: column;
      }
      .toolbar,
      .section-tools {
        align-items: stretch;
      }
      label,
      .toolbar button,
      .section-tools button {
        width: 100%;
      }
      input,
      select {
        width: 100%;
      }
    }
  </style>
</head>
<body>
  <main class="shell">
    <header class="topbar">
      <h1>Platform Review</h1>
      <div class="toolbar">
        <label>Reviewer ID
          <input id="reviewerId" class="mono" inputmode="numeric" autocomplete="off">
        </label>
        <button id="reloadAll" class="primary" type="button">Reload</button>
      </div>
    </header>

    <nav class="tabs" id="tabs" aria-label="Review queues"></nav>
    <div id="sections"></div>
  </main>

  <script>
    const queues = [
      {
        id: "dashboard",
        label: "Dashboard",
        endpoint: "/platform/api/admin/dashboard",
        itemKey: "dashboard",
        statuses: [],
        columns: ["Metric", "Value", "Detail"],
        dashboard: true,
        renderDashboard(dashboard) {
          const rows = [
            metricRow("Channel submissions", dashboard.channels?.submission_total, dashboard.channels?.submissions),
            metricRow("Channel approval rate", percent(dashboard.channels?.approval_rate), dashboard.channels?.risk),
            metricRow("Channel interactions", sumObject(dashboard.channels?.interactions), dashboard.channels?.interactions),
            metricRow("Relay providers", dashboard.relays?.provider_total, dashboard.relays?.providers),
            metricRow("Relay approval rate", percent(dashboard.relays?.approval_rate), dashboard.relays?.risk),
            metricRow("Relay feedback", sumObject(dashboard.relays?.feedback?.types), dashboard.relays?.feedback),
            metricRow("Model test jobs", sumObject(dashboard.model_lab?.jobs), dashboard.model_lab?.jobs),
            metricRow("Model success rate", percent(dashboard.model_lab?.success_rate), dashboard.model_lab?.reports),
            metricRow("Model ops", dashboard.model_lab?.operations?.healthy_count || 0, dashboard.model_lab?.operations),
            metricRow("Ledger entries", sumObject(dashboard.growth?.ledger_entries), dashboard.growth?.ledger_totals),
            metricRow("Invite retention", dashboard.growth?.invite_retention?.snapshot_total || 0, dashboard.growth?.invite_retention),
            metricRow("Risk events", sumObject(dashboard.risk?.fraud_events?.event_type), dashboard.risk?.fraud_events),
            metricRow("Operating alerts", (dashboard.operating?.alerts || []).length, dashboard.operating || {}),
            metricRow("Unavailable metrics", (dashboard.coverage?.unavailable || []).length, dashboard.coverage?.unavailable),
          ];
          return rows.map(row => `<tr>${row.map(cell => `<td>${cell}</td>`).join("")}</tr>`).join("");
        },
      },
      {
        id: "reviewWorkload",
        label: "Review workload",
        endpoint: "/platform/api/admin/review-workload",
        itemKey: "workload",
        statuses: [],
        columns: ["Metric", "Value", "Detail"],
        workload: true,
        renderWorkload(workload) {
          const summary = workload.summary || {};
          const rows = [
            metricRow("Open review items", summary.open_total || 0, workload.queues || {}),
            metricRow("Unassigned items", summary.unassigned_total || 0, workload.alerts || []),
            metricRow("Urgent escalations", summary.urgent_total || 0, workload.alerts || []),
            metricRow("Reviewer count", summary.reviewer_count || 0, workload.reviewers || []),
            metricRow("Thresholds", "", workload.thresholds || {}),
            metricRow("Coverage", "", workload.coverage || {}),
          ];
          return rows.map(row => `<tr>${row.map(cell => `<td>${cell}</td>`).join("")}</tr>`).join("");
        },
      },
      {
        id: "auditLogs",
        label: "Audit logs",
        endpoint: "/platform/api/admin/audit-logs",
        itemKey: "logs",
        statuses: [],
        columns: ["Time", "Level", "Action", "Resource", "Details"],
        auditFilters: true,
        render(item) {
          return [
            entityCell(item.timestamp || "-", "user " + (item.user_id || "-")),
            statusCell(item.level),
            entityCell(item.action || "-", ""),
            entityCell((item.resource_type || "-") + ":" + (item.resource_id || "-"), ""),
            textCell(item.details || "-"),
          ];
        },
      },
      {
        id: "ownerDashboards",
        label: "Owner dashboards",
        endpoint: "/platform/api/admin/owners/dashboard",
        itemKey: "owners",
        statuses: [""],
        columns: ["Owner", "Channels", "Relays", "Recent resources"],
        render(owner) {
          const channels = owner.channels || {};
          const relays = owner.relays || {};
          const recentChannels = (channels.recent || []).map(item => "@" + (item.username || "-")).join(" / ");
          const recentRelays = (relays.recent || []).map(item => item.name || "-").join(" / ");
          return [
            entityCell("owner " + (owner.owner_id || "-"), "resources " + (owner.resource_total || 0)),
            textCell([
              "total " + (channels.total || 0),
              "statuses " + formatMetricDetail(channels.statuses || {}),
              "risk " + formatMetricDetail(channels.risk || {}),
              "interactions " + formatMetricDetail(channels.interactions || {}),
            ].join(" / ")),
            textCell([
              "total " + (relays.total || 0),
              "statuses " + formatMetricDetail(relays.statuses || {}),
              "risk " + formatMetricDetail(relays.risk || {}),
              "feedback " + formatMetricDetail(relays.feedback || {}),
            ].join(" / ")),
            textCell([recentChannels, recentRelays].filter(Boolean).join(" / ") || "-"),
          ];
        },
      },
      {
        id: "channelSubmissions",
        label: "Channel submissions",
        endpoint: "/platform/api/admin/channels/submissions",
        itemKey: "submissions",
        statuses: ["", "submitted", "auto_checked", "human_review", "approved", "needs_changes", "rejected", "risk_blocked"],
        columns: ["Channel", "Status", "Reason", "Note", "Actions"],
        render(item) {
          const submission = item.submission || {};
          const channel = item.channel || {};
          return [
            entityCell(channel.title || channel.username, "@" + (channel.username || "-") + " / " + (channel.category || "-") + " / " + (channel.language || "-")),
            statusCell(submission.status),
            textCell([submission.reason, submission.commercial_content, submission.submitter_relation, "submitter " + (submission.submitter_id || "-")].filter(Boolean).join(" / ")),
            noteCell("channel_submission_" + submission.id),
            actionsCell([
              actionButton("Approve", "primary", () => reviewStatus(`/platform/api/admin/channels/submissions/${submission.id}/review`, "approved", "channel_submission_" + submission.id)),
              actionButton("Needs changes", "", () => reviewStatus(`/platform/api/admin/channels/submissions/${submission.id}/review`, "needs_changes", "channel_submission_" + submission.id)),
              actionButton("Reject", "danger", () => reviewStatus(`/platform/api/admin/channels/submissions/${submission.id}/review`, "rejected", "channel_submission_" + submission.id)),
              actionButton("Risk block", "warn", () => reviewStatus(`/platform/api/admin/channels/submissions/${submission.id}/review`, "risk_blocked", "channel_submission_" + submission.id)),
            ]),
          ];
        },
      },
      {
        id: "channelClaims",
        label: "Channel claims",
        endpoint: "/platform/api/admin/channel-claims",
        itemKey: "claims",
        statuses: ["", "pending", "approved", "rejected"],
        columns: ["Channel", "Status", "Verification", "Note", "Actions"],
        render(item) {
          const claim = item.claim || {};
          const channel = item.channel || {};
          const verification = claim.verification || {};
          return [
            entityCell(channel.title || channel.username, "@" + (channel.username || "-") + " / method " + (claim.method || "-")),
            statusCell(claim.status),
            textCell([
              "claimant " + (claim.claimant_id || "-"),
              verification.admin_rights_required ? "Bot admin check" : "",
              verification.expected_text ? "expected: " + verification.expected_text : "",
              verification.challenge ? "challenge: " + verification.challenge : "",
              verification.instruction || "",
            ].filter(Boolean).join(" / ")),
            noteCell("channel_claim_" + claim.id),
            actionsCell([
              actionButton("Approve", "primary", () => reviewClaim(`/platform/api/channel-claims/${claim.id}/review`, true, "channel_claim_" + claim.id)),
              actionButton("Reject", "danger", () => reviewClaim(`/platform/api/channel-claims/${claim.id}/review`, false, "channel_claim_" + claim.id)),
            ]),
          ];
        },
      },
      {
        id: "channelReports",
        label: "Channel reports",
        endpoint: "/platform/api/admin/channel-reports",
        itemKey: "reports",
        statuses: ["", "reported", "under_review", "dismissed", "risk_blocked"],
        reviewFilters: true,
        columns: ["Channel", "Risk", "Reports", "Assignment", "Note", "Actions"],
        render(item) {
          const report = item.report || {};
          const channel = item.channel || {};
          return [
            entityCell(channel.title || channel.username, "@" + (channel.username || "-") + " / " + (channel.category || "-") + " / " + (channel.language || "-")),
            statusCell(report.status || channel.risk_status),
            textCell([`count ${report.report_count || 0}`, report.first_reported_at, report.last_reported_at].filter(Boolean).join(" / ")),
            assignmentCell("channel_report_" + channel.id, report.assigned_to, report.escalation, report.reviewed_by, report.reviewed_at),
            noteCell("channel_report_" + channel.id),
            actionsCell([
              actionButton("Detail", "", () => loadChannelAdminDetail(channel.id)),
              actionButton("Review", "", () => reviewChannelReport(channel.id, "under_review", "channel_report_" + channel.id)),
              actionButton("Dismiss", "primary", () => reviewChannelReport(channel.id, "dismissed", "channel_report_" + channel.id)),
              actionButton("Risk block", "warn", () => reviewChannelReport(channel.id, "risk_blocked", "channel_report_" + channel.id)),
            ]),
          ];
        },
      },
      {
        id: "relayProviders",
        label: "Relay providers",
        endpoint: "/platform/api/admin/relays",
        itemKey: "providers",
        statuses: ["", "submitted", "auto_checked", "human_review", "approved", "needs_changes", "rejected", "risk_blocked"],
        columns: ["Provider", "Status", "Risk", "Note", "Actions"],
        render(provider) {
          return [
            entityCell(provider.name, [provider.base_url, provider.protocol].filter(Boolean).join(" / ")),
            statusCell(provider.status),
            textCell(provider.risk_status || "-"),
            noteCell("relay_provider_" + provider.id),
            actionsCell([
              actionButton("Detail", "", () => loadRelayAdminDetail(provider.id)),
              actionButton("Approve", "primary", () => reviewRelayProvider(provider.id, "approved", "normal", "relay_provider_" + provider.id)),
              actionButton("Needs changes", "", () => reviewRelayProvider(provider.id, "needs_changes", "review", "relay_provider_" + provider.id)),
              actionButton("Reject", "danger", () => reviewRelayProvider(provider.id, "rejected", "rejected", "relay_provider_" + provider.id)),
              actionButton("Risk block", "warn", () => reviewRelayProvider(provider.id, "risk_blocked", "blocked", "relay_provider_" + provider.id)),
            ]),
          ];
        },
      },
      {
        id: "relayClaims",
        label: "Relay claims",
        endpoint: "/platform/api/admin/relay-claims",
        itemKey: "claims",
        statuses: ["", "pending", "approved", "rejected"],
        columns: ["Provider", "Status", "Verification", "Note", "Actions"],
        render(item) {
          const claim = item.claim || {};
          const provider = item.provider || {};
          const verification = claim.verification || {};
          return [
            entityCell(provider.name, [provider.base_url, claim.method].filter(Boolean).join(" / ")),
            statusCell(claim.status),
            textCell([
              "claimant " + (claim.claimant_id || "-"),
              verification.domain_control_required ? "Domain check" : "",
              verification.expected_text ? "expected: " + verification.expected_text : "",
              verification.challenge ? "challenge: " + verification.challenge : "",
              verification.instruction || "",
            ].filter(Boolean).join(" / ")),
            noteCell("relay_claim_" + claim.id),
            actionsCell([
              actionButton("Approve", "primary", () => reviewClaim(`/platform/api/relay-claims/${claim.id}/review`, true, "relay_claim_" + claim.id)),
              actionButton("Reject", "danger", () => reviewClaim(`/platform/api/relay-claims/${claim.id}/review`, false, "relay_claim_" + claim.id)),
            ]),
          ];
        },
      },
      {
        id: "relayFeedback",
        label: "Relay feedback",
        endpoint: "/platform/api/admin/relay-feedback",
        itemKey: "feedback",
        statuses: ["", "submitted", "under_review", "approved", "rejected", "risk_blocked"],
        reviewFilters: true,
        columns: ["Provider", "Status", "Feedback", "Assignment", "Outcome", "Note", "Actions"],
        render(item) {
          const feedback = item.feedback || {};
          const provider = item.provider || {};
          const noteId = "relay_feedback_" + feedback.id;
          return [
            entityCell(provider.name, provider.base_url || "-"),
            statusCell(feedback.status),
            textCell([feedback.feedback_type, feedback.rating ? "rating " + feedback.rating : "", feedback.text].filter(Boolean).join(" / ")),
            assignmentCell(noteId, feedback.assigned_to, feedback.escalation, feedback.reviewed_by, feedback.reviewed_at),
            outcomeCell(noteId, feedback.outcome, feedback.followup_notes, feedback.resolved_by, feedback.resolved_at, feedback.followup_state),
            noteCell(noteId),
            actionsCell([
              actionButton("Approve", "primary", () => reviewStatus(`/platform/api/admin/relay-feedback/${feedback.id}/review`, "approved", noteId, { includeOutcome: true })),
              actionButton("Review", "", () => reviewStatus(`/platform/api/admin/relay-feedback/${feedback.id}/review`, "under_review", noteId, { includeOutcome: true })),
              actionButton("Reject", "danger", () => reviewStatus(`/platform/api/admin/relay-feedback/${feedback.id}/review`, "rejected", noteId, { includeOutcome: true })),
              actionButton("Risk block", "warn", () => reviewStatus(`/platform/api/admin/relay-feedback/${feedback.id}/review`, "risk_blocked", noteId, { includeOutcome: true })),
            ]),
          ];
        },
      },
      {
        id: "relayComplaints",
        label: "Relay complaints",
        endpoint: "/platform/api/admin/relay-feedback?feedback_type=complaint",
        itemKey: "feedback",
        statuses: ["", "submitted", "under_review", "approved", "rejected", "risk_blocked"],
        reviewFilters: true,
        followupFilters: true,
        columns: ["Provider", "Status", "Complaint", "Assignment", "Follow-up", "Note", "Actions"],
        render(item) {
          const feedback = item.feedback || {};
          const provider = item.provider || {};
          const noteId = "relay_complaint_" + feedback.id;
          return [
            entityCell(provider.name, [provider.base_url, provider.protocol].filter(Boolean).join(" / ")),
            statusCell(feedback.status),
            textCell(feedback.text || "-"),
            assignmentCell(noteId, feedback.assigned_to, feedback.escalation, feedback.reviewed_by, feedback.reviewed_at),
            outcomeCell(noteId, feedback.outcome, feedback.followup_notes, feedback.resolved_by, feedback.resolved_at, feedback.followup_state),
            noteCell(noteId),
            actionsCell([
              actionButton("Acknowledge", "", () => followupReview(feedback.id, noteId, "under_review", "acknowledged")),
              actionButton("Monitor", "", () => followupReview(feedback.id, noteId, "under_review", "monitoring")),
              actionButton("Resolve", "primary", () => followupReview(feedback.id, noteId, "approved", "resolved")),
              actionButton("Approve", "primary", () => reviewStatus(`/platform/api/admin/relay-feedback/${feedback.id}/review`, "approved", noteId, { includeOutcome: true })),
              actionButton("Review", "", () => reviewStatus(`/platform/api/admin/relay-feedback/${feedback.id}/review`, "under_review", noteId, { includeOutcome: true })),
              actionButton("Reject", "danger", () => reviewStatus(`/platform/api/admin/relay-feedback/${feedback.id}/review`, "rejected", noteId, { includeOutcome: true })),
              actionButton("Risk block", "warn", () => reviewStatus(`/platform/api/admin/relay-feedback/${feedback.id}/review`, "risk_blocked", noteId, { includeOutcome: true })),
            ]),
          ];
        },
      },
      {
        id: "appeals",
        label: "Appeals",
        endpoint: "/platform/api/admin/fraud-events?event_type=appeal",
        itemKey: "events",
        statuses: ["", "open", "under_review", "approved", "rejected", "resolved", "dismissed"],
        columns: ["Subject", "Status", "Evidence", "Note", "Actions"],
        render(event) {
          const evidence = event.evidence || {};
          return [
            entityCell(event.subject_type + ":" + event.subject_id, "event " + (event.id || "-") + " / score " + (event.score_delta || 0)),
            statusCell(event.status),
            textCell([event.event_type, evidence.reason, evidence.source, event.created_at].filter(Boolean).join(" / ")),
            noteCell("fraud_event_" + event.id),
            actionsCell([
              actionButton("Review", "", () => reviewStatus(`/platform/api/admin/fraud-events/${event.id}/review`, "under_review", "fraud_event_" + event.id)),
              actionButton("Resolve", "primary", () => reviewStatus(`/platform/api/admin/fraud-events/${event.id}/review`, "resolved", "fraud_event_" + event.id)),
              actionButton("Reject", "danger", () => reviewStatus(`/platform/api/admin/fraud-events/${event.id}/review`, "rejected", "fraud_event_" + event.id)),
              actionButton("Dismiss", "", () => reviewStatus(`/platform/api/admin/fraud-events/${event.id}/review`, "dismissed", "fraud_event_" + event.id)),
            ]),
          ];
        },
      },
      {
        id: "inviteRewards",
        label: "Invite rewards",
        endpoint: "/platform/api/admin/invite-rewards",
        itemKey: "rewards",
        statuses: ["", "pending", "qualified", "rewarded", "risk_blocked", "rejected"],
        columns: ["Reward", "Status", "Risk", "Note", "Actions"],
        render(reward) {
          return [
            entityCell("reward " + (reward.id || "-"), "inviter " + (reward.inviter_id || "-") + " / invited " + (reward.invited_id || "-") + " / chat " + (reward.chat_id || "-")),
            statusCell(reward.status),
            textCell(["points " + (reward.points_awarded || 0), "risk " + (reward.risk_score || 0), reward.risk_reason].filter(Boolean).join(" / ")),
            noteCell("invite_reward_" + reward.id),
            actionsCell([
              actionButton("Qualify", "primary", () => reviewInviteReward(reward.id, "qualified", 0, "invite_reward_" + reward.id)),
              actionButton("Risk block", "warn", () => reviewInviteReward(reward.id, "risk_blocked", 10, "invite_reward_" + reward.id)),
              actionButton("Reject", "danger", () => reviewInviteReward(reward.id, "rejected", 10, "invite_reward_" + reward.id)),
            ]),
          ];
        },
      },
    ];

    const reviewerInput = document.getElementById("reviewerId");
    reviewerInput.value = localStorage.getItem("platformReviewerId") || "";
    reviewerInput.addEventListener("change", () => localStorage.setItem("platformReviewerId", reviewerInput.value.trim()));
    document.getElementById("reloadAll").addEventListener("click", () => loadQueue(activeQueueId()));

    function activeQueueId() {
      return document.querySelector(".tab.active")?.dataset.queue || queues[0].id;
    }

    function reviewerId() {
      const value = reviewerInput.value.trim();
      if (!value) throw new Error("Reviewer ID is required.");
      return Number(value);
    }

    function h(value) {
      return String(value ?? "").replace(/[&<>"']/g, char => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
      }[char]));
    }

    function entityCell(title, meta) {
      return `<div class="row-title">${h(title || "-")}</div><div class="row-meta">${h(meta || "")}</div>`;
    }

    function statusCell(status) {
      const value = status || "-";
      return `<span class="status ${h(value)}">${h(value)}</span>`;
    }

    function textCell(value) {
      return `<div>${h(value || "-")}</div>`;
    }

    function metricRow(label, value, detail) {
      return [entityCell(label, ""), textCell(value ?? 0), textCell(formatMetricDetail(detail))];
    }

    function sumObject(value) {
      if (!value || typeof value !== "object" || Array.isArray(value)) return 0;
      return Object.values(value).reduce((sum, item) => sum + Number(item || 0), 0);
    }

    function percent(value) {
      return `${Math.round(Number(value || 0) * 10000) / 100}%`;
    }

    function formatMetricDetail(value) {
      if (value === null || value === undefined || value === "") return "-";
      if (Array.isArray(value)) return value.map(item => typeof item === "object" ? JSON.stringify(item) : String(item)).join(" / ");
      if (typeof value === "object") return Object.entries(value).map(([key, item]) => `${key}: ${typeof item === "object" ? JSON.stringify(item) : item}`).join(" / ");
      return String(value);
    }

    function noteCell(id) {
      return `<textarea id="${h(id)}" placeholder="Review note"></textarea>`;
    }

    function assignmentCell(id, assignedTo, escalation, reviewedBy, reviewedAt) {
      return `<div class="assignment">
        <input id="${h(id)}_assigned" inputmode="numeric" placeholder="Assigned user" value="${h(assignedTo || "")}">
        <select id="${h(id)}_escalation">
          ${["none", "watch", "operator", "risk", "urgent"].map(level => `<option value="${level}" ${level === (escalation || "none") ? "selected" : ""}>${level}</option>`).join("")}
        </select>
        <div class="row-meta">${reviewedBy ? `reviewed by ${h(reviewedBy)} ${h(reviewedAt || "")}` : "unreviewed"}</div>
      </div>`;
    }

    function outcomeCell(id, outcome, followupNotes, resolvedBy, resolvedAt, followupState) {
      const outcomes = ["none", "acknowledged", "resolved", "provider_fixed", "user_error", "duplicate", "invalid", "escalated", "monitoring"];
      const state = followupState || (resolvedBy ? "resolved" : "unresolved");
      return `<div class="assignment">
        <select id="${h(id)}_outcome">
          ${outcomes.map(item => `<option value="${item}" ${item === (outcome || "none") ? "selected" : ""}>${item}</option>`).join("")}
        </select>
        <textarea id="${h(id)}_followup" placeholder="Follow-up notes">${h(followupNotes || "")}</textarea>
        <div class="row-meta">${h(state)}${resolvedBy ? ` / updated by ${h(resolvedBy)} ${h(resolvedAt || "")}` : ""}</div>
      </div>`;
    }

    function reviewContext(noteId) {
      const assignedRaw = document.getElementById(noteId + "_assigned")?.value.trim() || "";
      return {
        assigned_to: assignedRaw ? Number(assignedRaw) : null,
        escalation: document.getElementById(noteId + "_escalation")?.value || "none",
      };
    }

    function outcomeContext(noteId) {
      return {
        outcome: document.getElementById(noteId + "_outcome")?.value || "none",
        followup_notes: document.getElementById(noteId + "_followup")?.value || "",
      };
    }

    function actionButton(label, className, handler) {
      const id = "btn_" + Math.random().toString(36).slice(2);
      queueMicrotask(() => {
        const button = document.getElementById(id);
        if (button) button.addEventListener("click", handler);
      });
      return `<button id="${id}" class="${h(className)}" type="button">${h(label)}</button>`;
    }

    function actionsCell(buttons) {
      return `<div class="actions">${buttons.join("")}</div>`;
    }

    function filterControls(queue) {
      if (queue.dashboard || queue.workload) return "";
      if (queue.auditFilters) {
        return `<label>Level
          <select id="${queue.id}_level">
            ${["", "INFO", "WARNING", "ERROR"].map(level => `<option value="${h(level)}">${h(level || "all")}</option>`).join("")}
          </select>
        </label>
        <label>Action <input id="${queue.id}_action" autocomplete="off" placeholder="channel_review"></label>
        <label>Resource <input id="${queue.id}_resource_type" autocomplete="off" placeholder="Channel"></label>
        <label>Resource ID <input id="${queue.id}_resource_id" autocomplete="off" placeholder="123"></label>
        <label>User <input id="${queue.id}_user_id" inputmode="numeric" autocomplete="off" placeholder="telegram id"></label>
        <label>Search <input id="${queue.id}_q" autocomplete="off" placeholder="details"></label>`;
      }
      const reviewFilters = queue.reviewFilters ? `
        <label>Assigned
          <input id="${queue.id}_assigned_to" inputmode="numeric" autocomplete="off" placeholder="id or unassigned">
        </label>
        <label>Reviewed
          <input id="${queue.id}_reviewed_by" inputmode="numeric" autocomplete="off" placeholder="id or unreviewed">
        </label>
        <label>Escalation
          <select id="${queue.id}_escalation">
            ${["", "none", "watch", "operator", "risk", "urgent"].map(level => `<option value="${h(level)}">${h(level || "all")}</option>`).join("")}
          </select>
        </label>` : "";
      const followupFilters = queue.followupFilters ? `
        <label>Follow-up
          <select id="${queue.id}_followup_state">
            ${["", "needs_followup", "in_followup", "resolved", "unresolved"].map(state => `<option value="${h(state)}">${h(state || "all")}</option>`).join("")}
          </select>
        </label>` : "";
      return `<label>Status
        <select id="${queue.id}_status">
          ${queue.statuses.map(status => `<option value="${h(status)}">${h(status || "all")}</option>`).join("")}
        </select>
      </label>${reviewFilters}${followupFilters}`;
    }

    function renderShell() {
      const tabs = document.getElementById("tabs");
      const sections = document.getElementById("sections");
      tabs.innerHTML = queues.map((queue, index) => (
        `<button class="tab ${index === 0 ? "active" : ""}" data-queue="${queue.id}" type="button">${h(queue.label)}</button>`
      )).join("");
      sections.innerHTML = queues.map((queue, index) => (
        `<section id="${queue.id}" class="section ${index === 0 ? "active" : ""}">
          <header class="section-header">
            <div class="section-title">${h(queue.label)}</div>
            <div class="section-tools">
              ${filterControls(queue)}
              <button type="button" data-load="${queue.id}">Load</button>
            </div>
          </header>
          <div id="${queue.id}_state" class="state">Idle</div>
          <div id="${queue.id}_detail" class="detail-panel"></div>
          <div class="table-wrap">
            <table>
              <thead><tr>${queue.columns.map(column => `<th>${h(column)}</th>`).join("")}</tr></thead>
              <tbody id="${queue.id}_rows"></tbody>
            </table>
          </div>
        </section>`
      )).join("");
      tabs.querySelectorAll(".tab").forEach(tab => {
        tab.addEventListener("click", () => {
          document.querySelectorAll(".tab").forEach(item => item.classList.remove("active"));
          document.querySelectorAll(".section").forEach(item => item.classList.remove("active"));
          tab.classList.add("active");
          document.getElementById(tab.dataset.queue).classList.add("active");
          loadQueue(tab.dataset.queue);
        });
      });
      document.querySelectorAll("[data-load]").forEach(button => {
        button.addEventListener("click", () => loadQueue(button.dataset.load));
      });
    }

    async function loadQueue(queueId) {
      const queue = queues.find(item => item.id === queueId);
      if (!queue) return;
      const url = new URL(queue.endpoint, window.location.origin);
      if (!queue.dashboard && !queue.workload) {
        if (queue.auditFilters) {
          [
            ["level", "level"],
            ["action", "action"],
            ["resource_type", "resource_type"],
            ["resource_id", "resource_id"],
            ["user_id", "user_id"],
            ["q", "q"],
          ].forEach(([param, field]) => {
            const value = document.getElementById(queue.id + "_" + field)?.value.trim() || "";
            if (value) url.searchParams.set(param, value);
          });
        } else {
          const status = document.getElementById(queue.id + "_status").value;
          if (status) url.searchParams.set("status", status);
          if (queue.reviewFilters) {
            [
              ["assigned_to", "assigned_to"],
              ["reviewed_by", "reviewed_by"],
              ["escalation", "escalation"],
            ].forEach(([param, field]) => {
              const value = document.getElementById(queue.id + "_" + field)?.value.trim() || "";
              if (value) url.searchParams.set(param, value);
            });
          }
          if (queue.followupFilters) {
            [
              ["followup_state", "followup_state"],
            ].forEach(([param, field]) => {
              const value = document.getElementById(queue.id + "_" + field)?.value.trim() || "";
              if (value) url.searchParams.set(param, value);
            });
          }
        }
      }
      const state = document.getElementById(queue.id + "_state");
      const rows = document.getElementById(queue.id + "_rows");
      state.className = "state";
      state.textContent = "Loading";
      rows.innerHTML = "";
      try {
        const response = await fetch(url, { credentials: "same-origin" });
        const payload = await response.json();
        if (!response.ok || !payload.ok) throw new Error(payload.error || `HTTP ${response.status}`);
        if (queue.dashboard) {
          rows.innerHTML = queue.renderDashboard(payload.dashboard || {});
          state.textContent = "Dashboard loaded";
          return;
        }
        if (queue.workload) {
          rows.innerHTML = queue.renderWorkload(payload.workload || {});
          state.textContent = "Workload loaded";
          return;
        }
        const items = payload[queue.itemKey] || [];
        rows.innerHTML = items.map(item => `<tr>${queue.render(item).map(cell => `<td>${cell}</td>`).join("")}</tr>`).join("");
        state.textContent = `${items.length} item(s)`;
      } catch (error) {
        state.className = "state error";
        state.textContent = error.message || "Load failed";
      }
    }

    function noteValue(noteId) {
      return document.getElementById(noteId)?.value || "";
    }

    async function postReview(url, body) {
      const response = await fetch(url, {
        method: "POST",
        credentials: "same-origin",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      });
      const payload = await response.json();
      if (!response.ok || !payload.ok) throw new Error(payload.error || `HTTP ${response.status}`);
      await loadQueue(activeQueueId());
    }

    async function reviewStatus(url, status, noteId, options = {}) {
      try {
        const context = options.includeOutcome ? outcomeContext(noteId) : {};
        await postReview(url, { user_id: reviewerId(), status, notes: noteValue(noteId), ...reviewContext(noteId), ...context });
      } catch (error) {
        alert(error.message || "Review failed");
      }
    }

    async function followupReview(feedbackId, noteId, status, outcome) {
      const outcomeSelect = document.getElementById(noteId + "_outcome");
      if (outcomeSelect) outcomeSelect.value = outcome;
      await reviewStatus(`/platform/api/admin/relay-feedback/${feedbackId}/review`, status, noteId, { includeOutcome: true });
    }

    async function reviewClaim(url, approved, noteId) {
      try {
        await postReview(url, { user_id: reviewerId(), approved, notes: noteValue(noteId) });
      } catch (error) {
        alert(error.message || "Review failed");
      }
    }

    async function reviewRelayProvider(providerId, status, riskStatus, noteId) {
      try {
        await postReview(`/platform/api/admin/relays/${providerId}/review`, {
          user_id: reviewerId(),
          status,
          risk_status: riskStatus,
          notes: noteValue(noteId),
        });
      } catch (error) {
        alert(error.message || "Review failed");
      }
    }

    async function loadChannelAdminDetail(channelId) {
      const panel = document.getElementById("channelReports_detail");
      if (!panel) return;
      panel.className = "detail-panel active";
      panel.textContent = "Loading channel detail";
      try {
        const response = await fetch(`/platform/api/admin/channels/${channelId}`, { credentials: "same-origin" });
        const payload = await response.json();
        if (!response.ok || !payload.ok) throw new Error(payload.error || `HTTP ${response.status}`);
        panel.innerHTML = renderChannelAdminDetail(payload.result || {});
      } catch (error) {
        panel.className = "detail-panel active state error";
        panel.textContent = error.message || "Load failed";
      }
    }

    function renderChannelAdminDetail(detail) {
      const channel = detail.channel || {};
      const report = detail.report || {};
      const interactions = detail.interactions || {};
      const submissions = detail.submissions || [];
      const claims = detail.claims || [];
      const audits = detail.audit_trail || [];
      const moderationHistory = detail.moderation_history || [];
      const submissionRows = submissions.length ? submissions.map(item => (
        `<div class="row-meta">${h(item.status || "-")} / submitter ${h(item.submitter_id || "-")} / ${h(item.submitter_relation || "-")} / ${h(item.created_at || "-")}</div>`
      )).join("") : `<div class="row-meta">No submissions</div>`;
      const claimRows = claims.length ? claims.map(item => (
        `<div class="row-meta">${h(item.method || "-")} / ${h(item.status || "-")} / claimant ${h(item.claimant_id || "-")} / ${h(item.verified_at || item.created_at || "-")}</div>`
      )).join("") : `<div class="row-meta">No claims</div>`;
      const historyRows = moderationHistory.length ? moderationHistory.map(item => {
        const historyText = [item.summary, item.notes].filter(Boolean).join(" / ") || "-";
        return `<div class="row-meta">${h(item.at || "-")} / ${h(item.kind || "-")} / ${h(item.status || item.action || "-")} / actor ${h(item.actor_id || item.reviewer_id || "-")} / ${h(historyText)}</div>`;
      }).join("") : `<div class="row-meta">No moderation history</div>`;
      const auditRows = audits.length ? audits.map(item => (
        `<div class="row-meta">${h(item.timestamp || "-")} / ${h(item.action || "-")} / ${h(item.details || "-")}</div>`
      )).join("") : `<div class="row-meta">No audit events</div>`;
      const interactionRows = Object.keys(interactions).length ? Object.entries(interactions).map(([key, value]) => (
        `<div class="row-meta">${h(key)}: ${h(value)}</div>`
      )).join("") : `<div class="row-meta">No interactions</div>`;
      return `<div class="detail-grid">
        <section class="detail-block">
          <h3>${h(channel.title || channel.username || "Channel detail")}</h3>
          <div class="row-meta">@${h(channel.username || "-")} / ${h(channel.category || "-")} / ${h(channel.language || "-")}</div>
          <div class="row-meta">status ${h(channel.status || "-")} / risk ${h(channel.risk_status || "-")} / owner ${h(channel.owner_user_id || "-")}</div>
          <div class="row-meta">risk notes: ${h(channel.risk_notes || "-")}</div>
        </section>
        <section class="detail-block">
          <h3>Reports</h3>
          <div class="row-meta">count ${h(report.report_count || 0)} / ${h(report.first_reported_at || "-")} / ${h(report.last_reported_at || "-")}</div>
          <div class="row-meta">assigned ${h(report.assigned_to || "-")} / escalation ${h(report.escalation || "none")}</div>
          <div class="row-meta">reviewed ${h(report.reviewed_by || "-")} ${h(report.reviewed_at || "")}</div>
        </section>
        <section class="detail-block">
          <h3>Interactions</h3>
          ${interactionRows}
        </section>
        <section class="detail-block">
          <h3>Submissions</h3>
          ${submissionRows}
        </section>
        <section class="detail-block">
          <h3>Claims</h3>
          ${claimRows}
        </section>
        <section class="detail-block">
          <h3>Moderation history</h3>
          ${historyRows}
        </section>
        <section class="detail-block">
          <h3>Audit trail</h3>
          ${auditRows}
        </section>
      </div>`;
    }

    async function loadRelayAdminDetail(providerId) {
      const panel = document.getElementById("relayProviders_detail");
      if (!panel) return;
      panel.className = "detail-panel active";
      panel.textContent = "Loading relay detail";
      try {
        const response = await fetch(`/platform/api/admin/relays/${providerId}`, { credentials: "same-origin" });
        const payload = await response.json();
        if (!response.ok || !payload.ok) throw new Error(payload.error || `HTTP ${response.status}`);
        panel.innerHTML = renderRelayAdminDetail(payload.result || {});
      } catch (error) {
        panel.className = "detail-panel active state error";
        panel.textContent = error.message || "Load failed";
      }
    }

    function renderRelayAdminDetail(detail) {
      const provider = detail.provider || {};
      const feedback = detail.feedback || {};
      const claims = detail.claims || [];
      const audits = detail.audit_trail || [];
      const recent = feedback.recent || [];
      const claimRows = claims.length ? claims.map(item => (
        `<div class="row-meta">${h(item.method || "-")} / ${h(item.status || "-")} / claimant ${h(item.claimant_id || "-")} / ${h(item.verified_at || item.created_at || "-")}</div>`
      )).join("") : `<div class="row-meta">No claims</div>`;
      const feedbackRows = recent.length ? recent.map(item => (
        `<div class="row-meta">${h(item.feedback_type || "-")}${item.rating ? " " + h(item.rating) + "/5" : ""}: ${h(item.text || "-")}</div>`
      )).join("") : `<div class="row-meta">No approved feedback</div>`;
      const auditRows = audits.length ? audits.map(item => (
        `<div class="row-meta">${h(item.timestamp || "-")} / ${h(item.action || "-")} / ${h(item.details || "-")}</div>`
      )).join("") : `<div class="row-meta">No audit events</div>`;
      return `<div class="detail-grid">
        <section class="detail-block">
          <h3>${h(provider.name || "Relay detail")}</h3>
          <div class="row-meta">${h(provider.base_url || "-")}</div>
          <div class="row-meta">protocol ${h(provider.protocol || "-")} / region ${h(provider.region || "-")}</div>
          <div class="row-meta">risk ${h(provider.risk_status || "-")} / owner ${provider.owner_verified ? "verified" : "unverified"}</div>
        </section>
        <section class="detail-block">
          <h3>Claims</h3>
          ${claimRows}
        </section>
        <section class="detail-block">
          <h3>Feedback</h3>
          <div class="row-meta">average ${h(feedback.average_rating || 0)} / complaints ${h((feedback.counts || {}).complaint || 0)}</div>
          ${feedbackRows}
        </section>
        <section class="detail-block">
          <h3>Audit trail</h3>
          ${auditRows}
        </section>
      </div>`;
    }

    async function reviewChannelReport(channelId, riskStatus, noteId) {
      try {
        await postReview(`/platform/api/admin/channels/${channelId}/report-review`, {
          user_id: reviewerId(),
          risk_status: riskStatus,
          notes: noteValue(noteId),
          ...reviewContext(noteId),
        });
      } catch (error) {
        alert(error.message || "Review failed");
      }
    }

    async function reviewInviteReward(rewardId, status, riskScore, noteId) {
      try {
        await postReview(`/platform/api/admin/invite-rewards/${rewardId}/review`, {
          user_id: reviewerId(),
          status,
          risk_score: riskScore,
          risk_reason: noteValue(noteId),
          notes: noteValue(noteId),
        });
      } catch (error) {
        alert(error.message || "Review failed");
      }
    }

    renderShell();
    loadQueue(queues[0].id);
  </script>
</body>
</html>
"""


PLATFORM_MINI_APP_HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>TGSellBot Platform</title>
  <script src="https://telegram.org/js/telegram-web-app.js"></script>
  <style>
    :root {
      color-scheme: light;
      --bg: #f6f7f8;
      --panel: #ffffff;
      --line: #d7dde5;
      --text: #17202a;
      --muted: #657184;
      --accent: #00796b;
      --danger: #b42318;
      --ok: #1a7f37;
      --warn: #9a6700;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font: 15px/1.45 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    button,
    input,
    select,
    textarea {
      font: inherit;
    }
    button {
      min-height: 2.25rem;
      padding: .35rem .7rem;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
      color: var(--text);
      cursor: pointer;
    }
    button.primary { background: var(--accent); border-color: var(--accent); color: #fff; }
    button.secondary { color: #035c52; border-color: #9bcac2; }
    button:disabled { opacity: .55; cursor: wait; }
    input,
    select,
    textarea {
      width: 100%;
      min-height: 2.35rem;
      padding: .4rem .55rem;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
      color: var(--text);
    }
    textarea {
      min-height: 5.2rem;
      resize: vertical;
    }
    .shell {
      max-width: 860px;
      margin: 0 auto;
      padding: .85rem;
    }
    .topbar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: .75rem;
      margin-bottom: .75rem;
    }
    h1 {
      margin: 0;
      font-size: 1.2rem;
      line-height: 1.2;
      letter-spacing: 0;
    }
    .muted { color: var(--muted); }
    .tabs {
      display: grid;
      grid-template-columns: repeat(5, minmax(0, 1fr));
      gap: .35rem;
      margin-bottom: .75rem;
    }
    .tab {
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .tab.active {
      border-color: var(--accent);
      background: #eaf4f2;
      color: #035c52;
      font-weight: 700;
    }
    .panel {
      display: none;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      overflow: hidden;
    }
    .panel.active { display: block; }
    .panel-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: .75rem;
      padding: .75rem;
      border-bottom: 1px solid var(--line);
      background: #fbfcfd;
    }
    .panel-title {
      font-weight: 800;
    }
    .body {
      padding: .75rem;
      display: grid;
      gap: .7rem;
    }
    form {
      display: grid;
      gap: .65rem;
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: .65rem;
    }
    label {
      display: grid;
      gap: .25rem;
      color: var(--muted);
      font-size: .84rem;
      font-weight: 650;
    }
    .checkline {
      display: inline-flex;
      align-items: center;
      gap: .4rem;
      min-height: 2.45rem;
      color: var(--text);
      font-weight: 600;
    }
    .actions {
      display: flex;
      align-items: center;
      gap: .5rem;
      flex-wrap: wrap;
    }
    .state {
      color: var(--muted);
      font-size: .9rem;
      min-height: 1.35rem;
    }
    .state.error { color: var(--danger); }
    .state.ok { color: var(--ok); }
    .list {
      display: grid;
      gap: .55rem;
    }
    .item {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: .65rem;
      background: #fff;
      display: grid;
      gap: .35rem;
    }
    .item-title {
      font-weight: 750;
      word-break: break-word;
    }
    .item-meta {
      color: var(--muted);
      font-size: .84rem;
      word-break: break-word;
    }
    .link-btn {
      min-height: 0;
      padding: 0;
      border: 0;
      background: transparent;
      color: var(--accent);
      font-weight: 750;
      cursor: pointer;
    }
    .row-actions {
      display: flex;
      gap: .4rem;
      flex-wrap: wrap;
    }
    .badge {
      display: inline-block;
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: .1rem .45rem;
      font-size: .78rem;
      color: var(--muted);
      background: #fff;
    }
    .notice {
      border-left: 3px solid var(--warn);
      background: #fff8e6;
      padding: .55rem .65rem;
      color: #694800;
    }
    .empty {
      border-style: dashed;
      background: #f9fbfc;
      min-height: 7.5rem;
      place-content: center;
      text-align: center;
    }
    .empty .row-actions {
      justify-content: center;
      margin-top: .25rem;
    }
    .filters {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: .5rem;
      align-items: end;
    }
    .filters .actions { align-self: end; }
    .pager {
      display: flex;
      gap: .45rem;
      flex-wrap: wrap;
      align-items: center;
    }
    .pager .state { min-height: 1rem; }
    .inline-meta {
      display: flex;
      gap: .35rem;
      flex-wrap: wrap;
      align-items: center;
    }
    @media (max-width: 620px) {
      .shell { padding: .65rem; }
      .tabs { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .panel-header,
      .topbar {
        align-items: stretch;
        flex-direction: column;
      }
      .grid { grid-template-columns: 1fr; }
      .filters { grid-template-columns: 1fr; }
      .actions button,
      .row-actions button { flex: 1 1 8rem; }
    }
  </style>
</head>
<body>
  <main class="shell">
    <header class="topbar">
      <div>
        <h1>TGSellBot Platform</h1>
        <div id="identity" class="muted">Telegram Mini App</div>
      </div>
      <button id="refresh" class="secondary" type="button">Refresh</button>
    </header>

    <nav class="tabs" aria-label="Platform sections">
      <button class="tab active" data-tab="channels" type="button">频道</button>
      <button class="tab" data-tab="relays" type="button">中转站</button>
      <button class="tab" data-tab="model_lab" type="button">检测</button>
      <button class="tab" data-tab="contribute" type="button">贡献</button>
      <button class="tab" data-tab="wallet" type="button">账本</button>
    </nav>

    <section id="channels" class="panel active">
      <header class="panel-header">
        <div class="panel-title">频道发现</div>
      </header>
      <div class="body">
        <div id="channelState" class="state"></div>
        <div class="filters">
          <label>搜索
            <input id="channelQuery" placeholder="频道、标题或简介">
          </label>
          <label>分类
            <input id="channelCategory" placeholder="ai, tools, news">
          </label>
          <label>语言
            <select id="channelLanguage">
              <option value="">全部</option>
              <option value="zh">中文</option>
              <option value="en">English</option>
              <option value="ru">Русский</option>
              <option value="multi">Multi</option>
            </select>
          </label>
          <div class="actions">
            <button id="searchChannels" type="button">搜索</button>
          </div>
        </div>
        <div class="pager">
          <button id="channelPrev" type="button">上一页</button>
          <button id="channelNext" type="button">下一页</button>
          <span id="channelPageState" class="state"></span>
        </div>
        <div id="channelList" class="list"></div>
        <div id="channelDetail" class="list"></div>
        <form id="channelForm">
          <div class="grid">
            <label>频道链接或 username
              <input name="channel" placeholder="https://t.me/example 或 @example" required>
            </label>
            <label>分类
              <input name="category" placeholder="ai, tools, news" required>
            </label>
            <label>语言
              <select name="language">
                <option value="zh">中文</option>
                <option value="en">English</option>
                <option value="ru">Русский</option>
                <option value="multi">Multi</option>
              </select>
            </label>
            <label>提交者关系
              <select name="submitter_relation">
                <option value="recommender">推荐者</option>
                <option value="owner">频道主</option>
                <option value="member">成员</option>
              </select>
            </label>
          </div>
          <label>推荐理由
            <textarea name="reason" maxlength="1000" required></textarea>
          </label>
          <label>商业声明
            <select name="commercial_content">
              <option value="unknown">不确定</option>
              <option value="none">无商业推广</option>
              <option value="sponsored">含商业推广</option>
            </select>
          </label>
          <div class="actions">
            <button class="primary" type="submit">提交频道</button>
            <span id="channelSubmitState" class="state"></span>
          </div>
        </form>
      </div>
    </section>

    <section id="relays" class="panel">
      <header class="panel-header">
        <div class="panel-title">中转站目录</div>
      </header>
      <div class="body">
        <div id="relayState" class="state"></div>
        <div class="filters">
          <label>搜索
            <input id="relayQuery" placeholder="名称、模型或地区">
          </label>
          <label>协议
            <select id="relayProtocol">
              <option value="">全部</option>
              <option value="openai-compatible">OpenAI-compatible</option>
              <option value="anthropic-compatible">Anthropic-compatible</option>
            </select>
          </label>
          <label>地区
            <input id="relayRegion" placeholder="US, HK, SG">
          </label>
          <div class="actions">
            <button id="searchRelays" type="button">搜索</button>
          </div>
        </div>
        <div class="pager">
          <button id="relayPrev" type="button">上一页</button>
          <button id="relayNext" type="button">下一页</button>
          <span id="relayPageState" class="state"></span>
        </div>
        <div id="relayList" class="list"></div>
        <div id="relayDetail" class="list"></div>
        <form id="relayForm">
          <div class="grid">
            <label>名称
              <input name="name" required>
            </label>
            <label>API Base URL
              <input name="base_url" placeholder="https://relay.example.com/v1" required>
            </label>
            <label>协议类型
              <select name="protocol">
                <option value="openai-compatible">OpenAI-compatible</option>
                <option value="anthropic-compatible">Anthropic-compatible</option>
              </select>
            </label>
            <label>地区
              <input name="region" placeholder="US, HK, SG">
            </label>
          </div>
          <label>模型范围
            <textarea name="model_scope" maxlength="1000"></textarea>
          </label>
          <label>价格说明
            <textarea name="pricing" maxlength="1000"></textarea>
          </label>
          <div class="actions">
            <button class="primary" type="submit">提交中转站</button>
            <span id="relaySubmitState" class="state"></span>
          </div>
        </form>
      </div>
    </section>

    <section id="contribute" class="panel">
      <header class="panel-header">
        <div class="panel-title">贡献任务</div>
        <button id="loadOwnerDashboard" type="button">刷新归属</button>
      </header>
      <div class="body">
        <div id="ownerDashboardState" class="state"></div>
        <div id="ownerDashboardList" class="list"></div>
        <article class="item">
          <div class="item-title">提交优质频道</div>
          <div class="item-meta">通过审核后进入发现列表，奖励后续走可审计积分账本。</div>
          <div class="row-actions">
            <button type="button" data-jump="channels">去提交频道</button>
          </div>
        </article>
        <article class="item">
          <div class="item-title">提交中转站资料</div>
          <div class="item-meta">只评价协议兼容、能力一致性和疑似降级风险，不证明真实上游模型。</div>
          <div class="row-actions">
            <button type="button" data-jump="relays">去提交站点</button>
          </div>
        </article>
      </div>
    </section>

    <section id="model_lab" class="panel">
      <header class="panel-header">
        <div class="panel-title">接口检测</div>
        <div class="row-actions">
          <button id="loadTests" type="button">刷新任务</button>
          <button id="loadReports" type="button">刷新报告</button>
        </div>
      </header>
      <div class="body">
        <div class="notice">不要在 Telegram 聊天中发送 API Key。此表单只把 Key 发送到检测入口，后端只保存 fingerprint 和掩码。</div>
        <form id="testForm">
          <div class="grid">
            <label>Endpoint
              <input name="endpoint" placeholder="https://relay.example.com/v1" required>
            </label>
            <label>协议
              <select name="protocol">
                <option value="openai-compatible">OpenAI-compatible</option>
                <option value="anthropic-compatible">Anthropic-compatible</option>
              </select>
            </label>
            <label>请求模型
              <input name="requested_model" placeholder="gpt-4.1">
            </label>
            <label>API Key
              <input name="api_key" type="password" autocomplete="off" required>
            </label>
            <label>执行方式
              <span class="checkline"><input name="run_now" type="checkbox" value="1"> 立即运行 P0</span>
            </label>
          </div>
          <div class="actions">
            <button class="primary" type="submit">创建检测任务</button>
            <span id="testSubmitState" class="state"></span>
          </div>
        </form>
        <div id="testState" class="state"></div>
        <div id="testResult" class="list"></div>
        <div id="reportState" class="state"></div>
        <div id="reportList" class="list"></div>
      </div>
    </section>

    <section id="wallet" class="panel">
      <header class="panel-header">
        <div class="panel-title">账本</div>
        <button id="loadLedger" type="button">刷新账本</button>
      </header>
      <div class="body">
        <div id="ledgerState" class="state"></div>
        <div id="ledgerList" class="list"></div>
      </div>
    </section>
  </main>

  <script>
    const tg = window.Telegram?.WebApp;
    if (tg) {
      tg.ready();
      tg.expand();
    }
    const initData = tg?.initData || "";
    const tgUser = tg?.initDataUnsafe?.user || null;
    const currentUserId = tgUser?.id || 0;
    const identity = document.getElementById("identity");
    if (tgUser) identity.textContent = [tgUser.first_name, tgUser.username ? "@" + tgUser.username : ""].filter(Boolean).join(" ");
    const channelState = { offset: 0, limit: 10, hasMore: false, activeId: null, detail: null, claimNotice: null };
    const relayState = { offset: 0, limit: 10, hasMore: false, activeId: null, detail: null, claimNotice: null, feedbackMode: "rating", feedbackNotice: null };
    const ownerDashboardState = { dashboard: null };
    const modelLabState = {
      jobOffset: 0,
      jobLimit: 10,
      jobHasMore: false,
      reportOffset: 0,
      reportLimit: 10,
      reportHasMore: false,
      activeJobId: null,
      activeReportId: null,
      jobDetail: null,
      reportDetail: null,
    };

    const initialTab = new URLSearchParams(window.location.search).get("tab") || "channels";
    document.querySelectorAll(".tab").forEach(button => {
      button.addEventListener("click", () => selectTab(button.dataset.tab));
    });
    document.querySelectorAll("[data-jump]").forEach(button => {
      button.addEventListener("click", () => selectTab(button.dataset.jump));
    });
    document.getElementById("refresh").addEventListener("click", () => refreshActive());
    document.getElementById("loadOwnerDashboard").addEventListener("click", () => loadOwnerDashboard());
    document.getElementById("loadTests").addEventListener("click", () => loadModelTests());
    document.getElementById("loadReports").addEventListener("click", () => loadModelReports());
    document.getElementById("searchChannels").addEventListener("click", () => {
      channelState.offset = 0;
      loadChannels();
    });
    document.getElementById("channelPrev").addEventListener("click", () => {
      channelState.offset = Math.max(0, channelState.offset - channelState.limit);
      loadChannels();
    });
    document.getElementById("channelNext").addEventListener("click", () => {
      if (channelState.hasMore) {
        channelState.offset += channelState.limit;
        loadChannels();
      }
    });
    document.getElementById("searchRelays").addEventListener("click", () => {
      relayState.offset = 0;
      loadRelays();
    });
    document.getElementById("relayPrev").addEventListener("click", () => {
      relayState.offset = Math.max(0, relayState.offset - relayState.limit);
      loadRelays();
    });
    document.getElementById("relayNext").addEventListener("click", () => {
      if (relayState.hasMore) {
        relayState.offset += relayState.limit;
        loadRelays();
      }
    });
    document.getElementById("loadLedger").addEventListener("click", loadLedger);
    document.getElementById("channelForm").addEventListener("submit", event => submitForm(event, "/platform/api/channels/submissions", "channelSubmitState", () => {
      event.target.reset();
      loadChannels();
    }));
    document.getElementById("relayForm").addEventListener("submit", event => submitForm(event, "/platform/api/relays", "relaySubmitState", () => event.target.reset()));
    document.getElementById("testForm").addEventListener("submit", submitTest);

    function h(value) {
      return String(value ?? "").replace(/[&<>"']/g, char => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
      }[char]));
    }

    function selectTab(tab) {
      document.querySelectorAll(".tab").forEach(item => item.classList.toggle("active", item.dataset.tab === tab));
      document.querySelectorAll(".panel").forEach(item => item.classList.toggle("active", item.id === tab));
      const url = new URL(window.location.href);
      url.searchParams.set("tab", tab);
      window.history.replaceState(null, "", url);
      if (tab === "channels") loadChannels();
      if (tab === "relays") loadRelays();
      if (tab === "model_lab") {
        loadModelTests();
        loadModelReports();
      }
      if (tab === "contribute") loadOwnerDashboard();
      if (tab === "wallet") loadLedger();
    }

    function activeTab() {
      return document.querySelector(".tab.active")?.dataset.tab || "channels";
    }

    function refreshActive() {
      const tab = activeTab();
      if (tab === "channels") loadChannels();
      if (tab === "relays") loadRelays();
      if (tab === "model_lab") {
        loadModelTests();
        loadModelReports();
      }
      if (tab === "contribute") loadOwnerDashboard();
      if (tab === "wallet") loadLedger();
    }

    function setState(id, message, mode = "") {
      const node = document.getElementById(id);
      node.textContent = message || "";
      node.className = "state" + (mode ? " " + mode : "");
    }

    function renderEmpty(title, detail = "", actions = "") {
      return (
        `<article class="item empty">
          <div class="item-title">${h(title)}</div>
          ${detail ? `<div class="item-meta">${h(detail)}</div>` : ""}
          ${actions ? `<div class="row-actions">${actions}</div>` : ""}
        </article>`
      );
    }

    function renderTelegramRequired() {
      return renderEmpty("需要从 Telegram 打开", "当前没有 Telegram initData，个人数据无法读取。");
    }

    function bindUtilityButtons(root = document) {
      root.querySelectorAll("[data-scroll-to]").forEach(button => {
        button.addEventListener("click", () => {
          document.getElementById(button.dataset.scrollTo)?.scrollIntoView({ block: "start", behavior: "smooth" });
        });
      });
      root.querySelectorAll("[data-jump]").forEach(button => {
        button.addEventListener("click", () => selectTab(button.dataset.jump));
      });
    }

    function authHeaders() {
      return {
        "content-type": "application/json",
        "x-telegram-init-data": initData,
      };
    }

    async function apiFetch(url, options = {}) {
      if (!initData) throw new Error("Telegram initData is required.");
      const response = await fetch(url, {
        ...options,
        headers: { ...authHeaders(), ...(options.headers || {}) },
      });
      const payload = await response.json();
      if (!response.ok || !payload.ok) throw new Error(payload.error || `HTTP ${response.status}`);
      return payload;
    }

    function formData(form) {
      const data = Object.fromEntries(new FormData(form).entries());
      data.user_id = currentUserId;
      return data;
    }

    function languageOptions(value) {
      return ["zh", "en", "ru", "multi"].map(item => (
        `<option value="${item}" ${item === value ? "selected" : ""}>${item}</option>`
      )).join("");
    }

    function protocolOptions(value) {
      return ["openai-compatible", "anthropic-compatible"].map(item => (
        `<option value="${item}" ${item === value ? "selected" : ""}>${item}</option>`
      )).join("");
    }

    function renderClaimVerification(kind, result) {
      if (!result) return "";
      const verification = result.verification || {};
      const expectedText = verification.expected_text || "";
      const challenge = verification.challenge || result.challenge || "";
      const method = result.method || verification.method || "";
      return (
        `<article class="item claim-verification" data-claim-verification="${h(kind)}">
          <div class="item-title">认领验证 #${h(result.id || "")} <span class="badge">${h(result.status || "pending")}</span> <span class="badge">${h(method || "-")}</span></div>
          <div class="item-meta">${h(verification.instruction || "请按提示提交证明，等待审核员确认。")}</div>
          ${expectedText ? `<div class="item-meta">Expected text: ${h(expectedText)}</div>` : ""}
          ${challenge && !expectedText.includes(challenge) ? `<div class="item-meta">Challenge: ${h(challenge)}</div>` : ""}
        </article>`
      );
    }

    function visibilityLabel(visibility) {
      const labels = {
        private: "私有：仅提交者可查看",
        unlisted: "不公开：仅持链接/授权入口可查看",
        public: "公开：可进入公开报告流",
      };
      return labels[visibility] || "未知可见性";
    }

    function renderScoreBadges(scores) {
      const entries = Object.entries(scores || {});
      if (!entries.length) return `<span class="badge">scores unavailable</span>`;
      return entries.map(([key, value]) => `<span class="badge">${h(key)} ${h(value)}</span>`).join("");
    }

    function renderReportTimeline(report) {
      const job = report.job || {};
      const items = [
        ["job created", job.created_at],
        ["job updated", job.updated_at],
        ["report created", report.created_at],
        ["report updated", report.updated_at],
      ].filter(([, value]) => value);
      return items.length ? items.map(([label, value]) => (
        `<div class="item-meta">${h(label)} · ${h(value)}</div>`
      )).join("") : `<div class="item-meta">暂无时间线</div>`;
    }

    function renderRunHistory(runs) {
      const rows = runs || [];
      if (!rows.length) return `<div class="item-meta">暂无运行历史</div>`;
      return rows.map(run => (
        `<div class="item-meta">Run #${h(run.id)} · ${h(run.status || "-")} · worker ${h(run.worker_id || "-")} · ${h(run.duration_ms || 0)}ms · requests ${h(run.request_count || 0)} · tokens ${h(run.total_tokens || 0)}${run.estimated_cost ? " · cost " + h(run.estimated_cost) : ""}${run.error_type ? " · " + h(run.error_type) : ""}${run.error_summary ? " · " + h(run.error_summary) : ""} · ${h(run.created_at || "-")}</div>`
      )).join("");
    }

    function renderEvidenceSummary(evidence) {
      const entries = Object.entries(evidence || {});
      if (!entries.length) return `<div class="item-meta">暂无证据摘要</div>`;
      return entries.slice(0, 8).map(([key, value]) => (
        `<div class="item-meta">${h(key)}: ${h(typeof value === "object" ? JSON.stringify(value) : value)}</div>`
      )).join("");
    }

    function renderVisibilityControls(reportId, activeVisibility = "") {
      return (
        `<button type="button" data-report-visibility="${h(reportId)}" data-visibility="private" ${activeVisibility === "private" ? "disabled" : ""}>${h(visibilityLabel("private").split("：")[0])}</button>` +
        `<button type="button" data-report-visibility="${h(reportId)}" data-visibility="unlisted" ${activeVisibility === "unlisted" ? "disabled" : ""}>${h(visibilityLabel("unlisted").split("：")[0])}</button>` +
        `<button type="button" data-report-visibility="${h(reportId)}" data-visibility="public" ${activeVisibility === "public" ? "disabled" : ""}>${h(visibilityLabel("public").split("：")[0])}</button>`
      );
    }

    function publicReportUrl(report) {
      if (!report || report.visibility === "private") return "";
      const url = new URL(`/platform/reports/${report.id}`, window.location.origin);
      if (report.visibility === "unlisted" && report.share_token) {
        url.searchParams.set("token", report.share_token);
      }
      return url.toString();
    }

    function reportShareText(report) {
      const parts = [
        `TGSellBot Model Lab Report #${report?.id || ""}`,
        report?.grade ? `grade ${report.grade}` : "",
        report?.declared_model ? `declared ${report.declared_model}` : "",
        report?.returned_model ? `returned ${report.returned_model}` : "",
      ].filter(Boolean);
      return parts.join(" · ");
    }

    function renderReportShareControls(report) {
      const shareUrl = publicReportUrl(report);
      if (!shareUrl) {
        return `<div class="item-meta">当前为私有报告，不生成公开入口。</div>`;
      }
      const shareText = reportShareText(report);
      return (
        `<div class="item-meta">公开入口：${h(shareUrl)}</div>
        <button type="button" data-copy-report-url="${h(shareUrl)}">复制报告链接</button>
        <button type="button" data-share-report-url="${h(shareUrl)}" data-share-report-text="${h(shareText)}">分享报告</button>`
      );
    }

    async function copyTextToClipboard(value) {
      const text = String(value || "");
      if (!text) return false;
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(text);
        return true;
      }
      const textarea = document.createElement("textarea");
      textarea.value = text;
      textarea.setAttribute("readonly", "");
      textarea.style.position = "fixed";
      textarea.style.left = "-9999px";
      document.body.appendChild(textarea);
      textarea.select();
      let copied = false;
      try {
        copied = document.execCommand("copy");
      } finally {
        textarea.remove();
      }
      return copied;
    }

    function telegramShareUrl(url, text) {
      const share = new URL("https://t.me/share/url");
      share.searchParams.set("url", url);
      if (text) share.searchParams.set("text", text);
      return share.toString();
    }

    async function shareReportLink(url, text) {
      if (!url) {
        setState("reportState", "No public report link", "error");
        return;
      }
      if (navigator.share) {
        try {
          await navigator.share({ title: "TGSellBot Model Lab Report", text, url });
          setState("reportState", "Share sheet opened", "ok");
          return;
        } catch (error) {
          if (error?.name === "AbortError") return;
        }
      }
      const shareUrl = telegramShareUrl(url, text);
      if (tg?.openTelegramLink) {
        tg.openTelegramLink(shareUrl);
      } else {
        window.open(shareUrl, "_blank", "noopener,noreferrer");
      }
      setState("reportState", "Telegram share opened", "ok");
    }

    function ratingOptions(value = "5") {
      return ["5", "4", "3", "2", "1"].map(item => (
        `<option value="${item}" ${String(value) === item ? "selected" : ""}>${item}</option>`
      )).join("");
    }

    function renderRelayFeedbackForms(providerId, activeMode = "rating") {
      const notice = relayState.feedbackNotice?.providerId === String(providerId)
        ? relayState.feedbackNotice
        : null;
      return (
        `<div class="feedback-panel" data-relay-feedback-panel="${h(providerId)}">
          <div class="item-title">社区反馈</div>
          <div class="item-meta">只评价协议兼容、能力一致性和疑似降级风险，不证明真实上游模型。</div>
          <div class="grid">
            <form data-relay-feedback-form="rating" data-provider="${h(providerId)}">
              <label>评分
                <select name="rating">${ratingOptions("5")}</select>
              </label>
              <label>评价内容
                <textarea name="text" maxlength="4000" placeholder="稳定性、模型列表、流式输出或 JSON 输出表现"></textarea>
              </label>
              <div class="actions">
                <button class="${activeMode === "rating" ? "primary" : ""}" type="submit">提交评价</button>
              </div>
            </form>
            <form data-relay-feedback-form="complaint" data-provider="${h(providerId)}">
              <label>投诉说明
                <textarea name="text" maxlength="4000" required placeholder="描述异常、复现路径或疑似降级风险"></textarea>
              </label>
              <div class="actions">
                <button class="${activeMode === "complaint" ? "primary" : ""}" type="submit">提交投诉</button>
              </div>
            </form>
          </div>
          <div id="relayFeedbackState" class="state${notice?.mode ? " " + h(notice.mode) : ""}">${h(notice?.message || "")}</div>
        </div>`
      );
    }

    async function submitForm(event, endpoint, stateId, onSuccess) {
      event.preventDefault();
      setState(stateId, "Submitting");
      try {
        await apiFetch(endpoint, {
          method: "POST",
          body: JSON.stringify(formData(event.target)),
        });
        setState(stateId, "Submitted", "ok");
        if (onSuccess) onSuccess();
      } catch (error) {
        setState(stateId, error.message || "Failed", "error");
      }
    }

    async function loadChannels() {
      if (!initData) {
        setState("channelState", "Telegram user is required.", "error");
        document.getElementById("channelList").innerHTML = renderTelegramRequired();
        return;
      }
      const q = document.getElementById("channelQuery").value.trim();
      const category = document.getElementById("channelCategory").value.trim();
      const language = document.getElementById("channelLanguage").value.trim();
      const url = new URL("/platform/api/channels/discover", window.location.origin);
      if (q) url.searchParams.set("q", q);
      if (category) url.searchParams.set("category", category);
      if (language) url.searchParams.set("language", language);
      url.searchParams.set("limit", String(channelState.limit));
      url.searchParams.set("offset", String(channelState.offset));
      setState("channelState", "Loading");
      try {
        const payload = await apiFetch(url);
        const rows = payload.channels || [];
        channelState.hasMore = Boolean(payload.has_more);
        const channelList = document.getElementById("channelList");
        channelList.innerHTML = rows.length ? rows.map(channel => (
          `<article class="item">
            <div class="item-title"><button class="link-btn" type="button" data-detail="${channel.id}">@${h(channel.username)}</button> <span class="badge">${h(channel.category)}</span> <span class="badge">${h(channel.language)}</span></div>
            <div class="item-meta">${h(channel.title || "")}</div>
            <div>${h(channel.description || "")}</div>
            <div class="inline-meta">
              <span class="badge">${h(channel.status || "-")}</span>
              <span class="badge">#${h(channel.id)}</span>
              <span class="badge">${h(channel.risk_status || "-")}</span>
            </div>
            <div class="row-actions">
              <button type="button" data-action="favorite" data-channel="${channel.id}">收藏</button>
              <button type="button" data-action="hide" data-channel="${channel.id}">隐藏</button>
              <button type="button" data-action="report" data-channel="${channel.id}">举报</button>
              <button type="button" data-action="claim" data-channel="${channel.id}">认领</button>
            </div>
          </article>`
        )).join("") : renderEmpty(
          "暂无频道结果",
          q || category || language ? "没有匹配当前筛选条件的频道。" : "还没有已审核频道。",
          `<button type="button" data-scroll-to="channelForm">提交频道</button>`
        );
        bindUtilityButtons(channelList);
        channelList.querySelectorAll("[data-channel]").forEach(button => {
          button.addEventListener("click", () => recordChannelAction(button.dataset.channel, button.dataset.action));
        });
        channelList.querySelectorAll("[data-detail]").forEach(button => {
          button.addEventListener("click", () => loadChannelDetail(button.dataset.detail));
        });
        const total = Number(payload.total || rows.length || 0);
        const page = Math.floor(channelState.offset / channelState.limit) + 1;
        const start = total ? channelState.offset + 1 : 0;
        const end = Math.min(channelState.offset + rows.length, total || rows.length);
        document.getElementById("channelPageState").textContent = total ? `第 ${page} 页 · ${start}-${end} / ${total}` : `第 ${page} 页`;
        setState("channelState", `${rows.length} item(s)`, rows.length ? "ok" : "");
      } catch (error) {
        setState("channelState", error.message || "Load failed", "error");
      }
    }

    async function recordChannelAction(channelId, action) {
      try {
        if (action === "claim") {
          const payload = await apiFetch(`/platform/api/channels/${channelId}/claim`, {
            method: "POST",
            body: JSON.stringify({ user_id: currentUserId, method: "challenge" }),
          });
          channelState.claimNotice = { channelId: String(channelId), result: payload.result || {} };
          await loadChannelDetail(channelId);
          setState("channelState", `Claim #${payload.result?.id || channelId} created`, "ok");
          return;
        }
        await apiFetch(`/platform/api/channels/${channelId}/interactions`, {
          method: "POST",
          body: JSON.stringify({ user_id: currentUserId, action, source: "mini_app" }),
        });
        if (channelState.activeId === String(channelId) && (action === "favorite" || action === "hide" || action === "report")) {
          await loadChannelDetail(channelId);
        }
      } catch (error) {
        alert(error.message || "Action failed");
      }
    }

    async function loadChannelDetail(channelId) {
      channelState.activeId = String(channelId);
      setState("channelState", "Loading detail");
      try {
        const payload = await apiFetch(`/platform/api/channels/${channelId}`);
        channelState.detail = payload.result || null;
        renderChannelDetail();
        setState("channelState", "Detail loaded", "ok");
      } catch (error) {
        setState("channelState", error.message || "Load failed", "error");
      }
    }

    function renderChannelDetail() {
      const node = document.getElementById("channelDetail");
      const detail = channelState.detail;
      if (!detail) {
        node.innerHTML = "";
        return;
      }
      const channel = detail.channel || {};
      const interactions = detail.interactions || {};
      const viewer = detail.viewer || {};
      const claim = detail.claim || {};
      const submissions = detail.submissions || [];
      const claims = detail.claims || [];
      const auditTrail = detail.audit_trail || [];
      const claimNotice = channelState.claimNotice?.channelId === String(channel.id)
        ? renderClaimVerification("channel", channelState.claimNotice.result)
        : "";
      const ownerForm = viewer.can_edit_profile ? (
        `<form class="owner-profile-form" data-channel-owner-profile="${h(channel.id)}">
          <div class="grid">
            <label>标题
              <input name="title" maxlength="255" value="${h(channel.title || "")}">
            </label>
            <label>分类
              <input name="category" maxlength="64" value="${h(channel.category || "")}">
            </label>
            <label>语言
              <select name="language">${languageOptions(channel.language || "zh")}</select>
            </label>
          </div>
          <label>简介
            <textarea name="description" maxlength="4000">${h(channel.description || "")}</textarea>
          </label>
          <div class="actions">
            <button class="primary" type="submit">保存资料</button>
            <span id="channelOwnerProfileState" class="state"></span>
          </div>
        </form>`
      ) : "";
      node.innerHTML = (
        `<article class="item">
          <div class="item-title">@${h(channel.username)} <span class="badge">${h(channel.category || "-")}</span> <span class="badge">${h(channel.language || "-")}</span></div>
          <div class="item-meta">${h(channel.title || "")}</div>
          <div>${h(channel.description || "")}</div>
          <div class="inline-meta">
            <span class="badge">status ${h(channel.status || "-")}</span>
            <span class="badge">risk ${h(channel.risk_status || "-")}</span>
            <span class="badge">score ${h(channel.quality_score ?? 0)}</span>
            <span class="badge">favorites ${h(interactions.favorite || 0)}</span>
            <span class="badge">hides ${h(interactions.hide || 0)}</span>
            <span class="badge">reports ${h(interactions.report || 0)}</span>
          </div>
          <div class="item-meta">认领 ${h(claim.status || "unclaimed")} / ${h(channel.url || "")}</div>
          <div class="item-meta">当前状态：${viewer.favorite ? "已收藏" : "未收藏"} / ${viewer.hidden ? "已隐藏" : "未隐藏"} / ${viewer.reported ? "已举报" : "未举报"}</div>
          <div class="list">
            ${claimNotice}
            <div class="item-meta">编辑资料：${h(channel.owner_verified ? "已验证归属" : "未验证归属")} / ${h(channel.created_at || "-")} / ${h(channel.updated_at || "-")}</div>
            ${ownerForm}
            <div class="item-meta">申报摘要：${h(submissions[0]?.reason || "暂无")}</div>
            <div class="item-meta">审核备注：${h(submissions[0]?.review_notes || "暂无")}</div>
            <div class="item-meta">认领方式：${h(claim.method || "unclaimed")} / ${h(claim.verified_at || "-")}</div>
            ${claims.length ? claims.map(item => (
              `<div class="item-meta">认领记录 #${h(item.id)} · ${h(item.status)} · ${h(item.method)} · ${h(item.verified_at || item.created_at || "-")}</div>`
            )).join("") : `<div class="item-meta">暂无认领记录</div>`}
            ${auditTrail.length ? auditTrail.map(item => (
              `<div class="item-meta">审计 ${h(item.action)} · ${h(item.details || "-")} · ${h(item.timestamp || "-")}</div>`
            )).join("") : `<div class="item-meta">暂无审计轨迹</div>`}
          </div>
          <div class="row-actions">
            <button type="button" data-action="favorite" data-channel="${channel.id}">收藏</button>
            <button type="button" data-action="hide" data-channel="${channel.id}">隐藏</button>
            <button type="button" data-action="report" data-channel="${channel.id}">举报</button>
            <button type="button" data-action="claim" data-channel="${channel.id}">认领</button>
          </div>
        </article>`
      );
      node.querySelectorAll("[data-channel]").forEach(button => {
        button.addEventListener("click", () => recordChannelAction(button.dataset.channel, button.dataset.action));
      });
      node.querySelector("[data-channel-owner-profile]")?.addEventListener("submit", submitChannelOwnerProfile);
    }

    async function submitChannelOwnerProfile(event) {
      event.preventDefault();
      const form = event.target;
      const channelId = form.dataset.channelOwnerProfile;
      setState("channelOwnerProfileState", "Saving");
      try {
        await apiFetch(`/platform/api/channels/${channelId}/owner-profile`, {
          method: "POST",
          body: JSON.stringify(formData(form)),
        });
        setState("channelOwnerProfileState", "Saved", "ok");
        await loadChannelDetail(channelId);
        await loadChannels();
      } catch (error) {
        setState("channelOwnerProfileState", error.message || "Save failed", "error");
      }
    }

    async function loadRelays() {
      if (!initData) {
        setState("relayState", "Telegram user is required.", "error");
        document.getElementById("relayList").innerHTML = renderTelegramRequired();
        return;
      }
      const q = document.getElementById("relayQuery").value.trim();
      const protocol = document.getElementById("relayProtocol").value.trim();
      const region = document.getElementById("relayRegion").value.trim();
      const url = new URL("/platform/api/relays/discover", window.location.origin);
      if (q) url.searchParams.set("q", q);
      if (protocol) url.searchParams.set("protocol", protocol);
      if (region) url.searchParams.set("region", region);
      url.searchParams.set("limit", String(relayState.limit));
      url.searchParams.set("offset", String(relayState.offset));
      setState("relayState", "Loading");
      try {
        const payload = await apiFetch(url);
        const rows = payload.providers || [];
        relayState.hasMore = Boolean(payload.has_more);
        const relayList = document.getElementById("relayList");
        relayList.innerHTML = rows.length ? rows.map(provider => (
          `<article class="item">
            <div class="item-title"><button class="link-btn" type="button" data-relay-detail="${provider.id}">${h(provider.name)}</button> <span class="badge">${h(provider.protocol)}</span> <span class="badge">${h(provider.region || "-")}</span></div>
            <div class="item-meta">${h(provider.base_url || "")}</div>
            <div>${h(provider.model_scope || "")}</div>
            <div class="inline-meta">
              <span class="badge">${h(provider.status || "-")}</span>
              <span class="badge">risk ${h(provider.risk_status || "-")}</span>
              <span class="badge">score ${h(provider.reputation_score ?? 0)}</span>
              <span class="badge">${provider.owner_verified ? "已认证" : "未认证"}</span>
            </div>
            <div class="row-actions">
              <button type="button" data-relay-action="claim" data-provider="${provider.id}">认领</button>
              <button type="button" data-relay-action="rating" data-provider="${provider.id}">评价</button>
              <button type="button" data-relay-action="complaint" data-provider="${provider.id}">投诉</button>
            </div>
          </article>`
        )).join("") : renderEmpty(
          "暂无中转站结果",
          q || protocol || region ? "没有匹配当前筛选条件的中转站。" : "还没有已审核中转站。",
          `<button type="button" data-scroll-to="relayForm">提交中转站</button>`
        );
        bindUtilityButtons(relayList);
        relayList.querySelectorAll("[data-relay-detail]").forEach(button => {
          button.addEventListener("click", () => loadRelayDetail(button.dataset.relayDetail));
        });
        relayList.querySelectorAll("[data-relay-action]").forEach(button => {
          button.addEventListener("click", () => handleRelayAction(button.dataset.provider, button.dataset.relayAction));
        });
        const total = Number(payload.total || rows.length || 0);
        const page = Math.floor(relayState.offset / relayState.limit) + 1;
        const start = total ? relayState.offset + 1 : 0;
        const end = Math.min(relayState.offset + rows.length, total || rows.length);
        document.getElementById("relayPageState").textContent = total ? `第 ${page} 页 · ${start}-${end} / ${total}` : `第 ${page} 页`;
        setState("relayState", `${rows.length} item(s)`, rows.length ? "ok" : "");
      } catch (error) {
        setState("relayState", error.message || "Load failed", "error");
      }
    }

    async function loadRelayDetail(providerId) {
      relayState.activeId = String(providerId);
      setState("relayState", "Loading detail");
      try {
        const payload = await apiFetch(`/platform/api/relays/${providerId}`);
        relayState.detail = payload.result || null;
        renderRelayDetail();
        setState("relayState", "Detail loaded", "ok");
      } catch (error) {
        setState("relayState", error.message || "Load failed", "error");
      }
    }

    function renderRelayDetail() {
      const node = document.getElementById("relayDetail");
      const detail = relayState.detail;
      if (!detail) {
        node.innerHTML = "";
        return;
      }
      const provider = detail.provider || {};
      const feedback = detail.feedback || {};
      const counts = feedback.counts || {};
      const recent = feedback.recent || [];
      const claim = detail.claim || {};
      const claims = detail.claims || [];
      const auditTrail = detail.audit_trail || [];
      const viewer = detail.viewer || {};
      const claimNotice = relayState.claimNotice?.providerId === String(provider.id)
        ? renderClaimVerification("relay", relayState.claimNotice.result)
        : "";
      const feedbackForms = renderRelayFeedbackForms(provider.id, relayState.feedbackMode);
      const ownerForm = viewer.can_edit_profile ? (
        `<form class="owner-profile-form" data-relay-owner-profile="${h(provider.id)}">
          <div class="grid">
            <label>名称
              <input name="name" maxlength="128" value="${h(provider.name || "")}">
            </label>
            <label>官网
              <input name="website_url" value="${h(provider.website_url || "")}">
            </label>
            <label>协议
              <select name="protocol">${protocolOptions(provider.protocol || "openai-compatible")}</select>
            </label>
            <label>地区
              <input name="region" maxlength="64" value="${h(provider.region || "")}">
            </label>
          </div>
          <label>模型范围
            <textarea name="model_scope" maxlength="1000">${h(provider.model_scope || "")}</textarea>
          </label>
          <label>价格说明
            <textarea name="pricing" maxlength="1000">${h(provider.pricing || "")}</textarea>
          </label>
          <div class="actions">
            <button class="primary" type="submit">保存资料</button>
            <span id="relayOwnerProfileState" class="state"></span>
          </div>
        </form>`
      ) : "";
      node.innerHTML = (
        `<article class="item">
          <div class="item-title">${h(provider.name)} <span class="badge">${h(provider.protocol || "-")}</span> <span class="badge">${h(provider.region || "-")}</span></div>
          <div class="item-meta">${h(provider.base_url || "")}</div>
          <div>${h(provider.model_scope || "")}</div>
          <div class="inline-meta">
            <span class="badge">status ${h(provider.status || "-")}</span>
            <span class="badge">risk ${h(provider.risk_status || "-")}</span>
            <span class="badge">score ${h(provider.reputation_score ?? 0)}</span>
            <span class="badge">rating ${h(feedback.average_rating || 0)}</span>
            <span class="badge">complaints ${h(counts.complaint || 0)}</span>
            <span class="badge">${provider.owner_verified ? "已认证" : "未认证"}</span>
          </div>
          <div class="item-meta">认领 ${h(claim.status || "unclaimed")} / 价格 ${h(provider.pricing || "-")}</div>
          <div class="list">
            ${claimNotice}
            <div class="item-meta">网站：${h(provider.website_url || "-")}</div>
            <div class="item-meta">公开地址：${h(provider.base_url || "-")}</div>
            ${ownerForm}
            <div class="item-meta">历史认领：${claims.length ? h(claims[0].method || "-") + " / " + h(claims[0].status || "-") : "暂无"}</div>
            ${recent.length ? recent.map(item => (
              `<div class="item-meta">${h(item.feedback_type)}${item.rating ? " " + h(item.rating) + "/5" : ""}: ${h(item.text || "-")}</div>`
            )).join("") : `<div class="item-meta">暂无已审核评价</div>`}
            ${feedbackForms}
            ${auditTrail.length ? auditTrail.map(item => (
              `<div class="item-meta">审计 ${h(item.action)} · ${h(item.details || "-")} · ${h(item.timestamp || "-")}</div>`
            )).join("") : `<div class="item-meta">暂无审计轨迹</div>`}
          </div>
          <div class="row-actions">
            <button type="button" data-relay-action="claim" data-provider="${provider.id}">认领</button>
            <button type="button" data-relay-action="rating" data-provider="${provider.id}">评价</button>
            <button type="button" data-relay-action="complaint" data-provider="${provider.id}">投诉</button>
          </div>
        </article>`
      );
      node.querySelectorAll("[data-relay-action]").forEach(button => {
        button.addEventListener("click", () => handleRelayAction(button.dataset.provider, button.dataset.relayAction));
      });
      node.querySelector("[data-relay-owner-profile]")?.addEventListener("submit", submitRelayOwnerProfile);
      node.querySelectorAll("[data-relay-feedback-form]").forEach(form => {
        form.addEventListener("submit", submitRelayFeedback);
      });
    }

    async function submitRelayOwnerProfile(event) {
      event.preventDefault();
      const form = event.target;
      const providerId = form.dataset.relayOwnerProfile;
      setState("relayOwnerProfileState", "Saving");
      try {
        await apiFetch(`/platform/api/relays/${providerId}/owner-profile`, {
          method: "POST",
          body: JSON.stringify(formData(form)),
        });
        setState("relayOwnerProfileState", "Saved", "ok");
        await loadRelayDetail(providerId);
        await loadRelays();
      } catch (error) {
        setState("relayOwnerProfileState", error.message || "Save failed", "error");
      }
    }

    async function handleRelayAction(providerId, action) {
      if (action === "rating" || action === "complaint") {
        relayState.feedbackMode = action;
        await loadRelayDetail(providerId);
        document.getElementById("relayFeedbackState")?.scrollIntoView({ block: "nearest" });
        return;
      }
      await recordRelayAction(providerId, action);
    }

    async function recordRelayAction(providerId, action) {
      try {
        if (action === "claim") {
          const payload = await apiFetch(`/platform/api/relays/${providerId}/claim`, {
            method: "POST",
            body: JSON.stringify({ user_id: currentUserId, method: "domain" }),
          });
          relayState.claimNotice = { providerId: String(providerId), result: payload.result || {} };
          await loadRelayDetail(providerId);
          setState("relayState", `Relay claim #${payload.result?.id || providerId} created`, "ok");
          return;
        }
      } catch (error) {
        alert(error.message || "Action failed");
      }
    }

    async function submitRelayFeedback(event) {
      event.preventDefault();
      const form = event.target;
      const providerId = form.dataset.provider;
      const feedbackType = form.dataset.relayFeedbackForm;
      const data = formData(form);
      data.feedback_type = feedbackType;
      if (feedbackType === "rating") {
        data.rating = Number(data.rating);
        if (!Number.isInteger(data.rating) || data.rating < 1 || data.rating > 5) {
          setState("relayFeedbackState", "评分必须是 1-5 的整数", "error");
          return;
        }
      }
      data.text = String(data.text || "").trim();
      if (feedbackType === "complaint" && !data.text) {
        setState("relayFeedbackState", "投诉说明不能为空", "error");
        return;
      }
      setState("relayFeedbackState", "Submitting");
      try {
        await apiFetch(`/platform/api/relays/${providerId}/feedback`, {
          method: "POST",
          body: JSON.stringify(data),
        });
        form.reset();
        relayState.feedbackMode = feedbackType;
        relayState.feedbackNotice = {
          providerId: String(providerId),
          message: feedbackType === "complaint" ? "投诉已提交，等待审核" : "评价已提交，等待审核",
          mode: "ok",
        };
        await loadRelayDetail(providerId);
      } catch (error) {
        setState("relayFeedbackState", error.message || "Feedback failed", "error");
      }
    }

    async function loadOwnerDashboard() {
      if (!currentUserId) {
        setState("ownerDashboardState", "Telegram user is required.", "error");
        document.getElementById("ownerDashboardList").innerHTML = renderTelegramRequired();
        return;
      }
      setState("ownerDashboardState", "Loading");
      try {
        const payload = await apiFetch(`/platform/api/owner/dashboard?user_id=${currentUserId}`);
        ownerDashboardState.dashboard = payload.dashboard || null;
        renderOwnerDashboard();
        const channelTotal = Number(ownerDashboardState.dashboard?.channels?.total || 0);
        const relayTotal = Number(ownerDashboardState.dashboard?.relays?.total || 0);
        setState("ownerDashboardState", `我的资源 ${channelTotal} channels / ${relayTotal} relays`, channelTotal || relayTotal ? "ok" : "");
      } catch (error) {
        setState("ownerDashboardState", error.message || "Load failed", "error");
      }
    }

    function renderOwnerDashboard() {
      const node = document.getElementById("ownerDashboardList");
      const dashboard = ownerDashboardState.dashboard || {};
      const channelRows = dashboard.channels?.items || [];
      const relayRows = dashboard.relays?.items || [];
      const channelCards = channelRows.map(item => renderOwnerChannelCard(item)).join("");
      const relayCards = relayRows.map(item => renderOwnerRelayCard(item)).join("");
      node.innerHTML = (
        `<article class="item">
          <div class="item-title">我的频道 <span class="badge">${h(dashboard.channels?.total || 0)}</span></div>
          <div class="list">${channelCards || renderEmpty("暂无已认领频道", "", `<button type="button" data-jump="channels">查看频道</button>`)}</div>
        </article>
        <article class="item">
          <div class="item-title">我的中转站 <span class="badge">${h(dashboard.relays?.total || 0)}</span></div>
          <div class="list">${relayCards || renderEmpty("暂无已认领中转站", "", `<button type="button" data-jump="relays">查看中转站</button>`)}</div>
        </article>`
      );
      bindUtilityButtons(node);
      node.querySelectorAll("[data-owner-channel]").forEach(button => {
        button.addEventListener("click", async () => {
          selectTab("channels");
          await loadChannelDetail(button.dataset.ownerChannel);
        });
      });
      node.querySelectorAll("[data-owner-relay]").forEach(button => {
        button.addEventListener("click", async () => {
          selectTab("relays");
          await loadRelayDetail(button.dataset.ownerRelay);
        });
      });
    }

    function renderOwnerChannelCard(item) {
      const channel = item.channel || {};
      const interactions = item.interactions || {};
      const claim = item.latest_claim || {};
      const submission = item.latest_submission || {};
      return (
        `<article class="item" data-owner-channel-card="${h(channel.id)}">
          <div class="item-title">@${h(channel.username || "-")} <span class="badge">${h(channel.status || "-")}</span> <span class="badge">${h(channel.risk_status || "-")}</span></div>
          <div class="item-meta">${h(channel.title || "")}</div>
          <div class="inline-meta">
            <span class="badge">favorites ${h(interactions.favorite || 0)}</span>
            <span class="badge">clicks ${h(interactions.click || 0)}</span>
            <span class="badge">reports ${h(interactions.report || 0)}</span>
            <span class="badge">claim ${h(claim.status || "unclaimed")}</span>
            <span class="badge">submission ${h(submission.status || "-")}</span>
          </div>
          <div class="row-actions">
            <button type="button" data-owner-channel="${h(channel.id)}">查看频道</button>
          </div>
        </article>`
      );
    }

    function renderOwnerRelayCard(item) {
      const provider = item.provider || {};
      const feedback = item.feedback || {};
      const counts = feedback.counts || {};
      const claim = item.latest_claim || {};
      return (
        `<article class="item" data-owner-relay-card="${h(provider.id)}">
          <div class="item-title">${h(provider.name || "-")} <span class="badge">${h(provider.status || "-")}</span> <span class="badge">${h(provider.risk_status || "-")}</span></div>
          <div class="item-meta">${h(provider.base_url || "")}</div>
          <div class="inline-meta">
            <span class="badge">rating ${h(feedback.average_rating || 0)}</span>
            <span class="badge">reviews ${h(counts.rating || 0)}</span>
            <span class="badge">complaints ${h(counts.complaint || 0)}</span>
            <span class="badge">claim ${h(claim.status || "unclaimed")}</span>
          </div>
          <div class="row-actions">
            <button type="button" data-owner-relay="${h(provider.id)}">查看中转站</button>
          </div>
        </article>`
      );
    }

    async function submitTest(event) {
      event.preventDefault();
      const form = event.target;
      const data = formData(form);
      data.run_now = form.elements.run_now.checked;
      data.idempotency_key = "miniapp:" + currentUserId + ":" + Date.now();
      setState("testSubmitState", "Creating");
      try {
        const payload = await apiFetch("/platform/api/relay-tests", {
          method: "POST",
          body: JSON.stringify(data),
        });
        form.reset();
        setState("testSubmitState", "Created", "ok");
        const job = payload.result;
        if (job) renderModelTestJob(job, true);
        await loadModelTests();
        await loadModelReports();
      } catch (error) {
        setState("testSubmitState", error.message || "Failed", "error");
      }
    }

    function renderModelTestJob(job, prepend = false) {
      const node = document.getElementById("testResult");
      const report = job.report || {};
      const item = (
        `<article class="item" data-job="${h(job.id)}">
          <div class="item-title">Job #${h(job.id)} <span class="badge">${h(job.status)}</span> <span class="badge">${h(job.protocol)}</span></div>
          <div class="item-meta">${h(job.endpoint)} / ${h(job.requested_model || "-")}</div>
          <div class="item-meta">Key ${h(job.key_masked || "")} / worker ${h(job.worker_id || "-")}</div>
          <div class="inline-meta">
            <span class="badge">report ${report.id ? "#" + h(report.id) : "none"}</span>
            <span class="badge">visibility ${h(report.visibility || job.report?.visibility || "-")}</span>
            <span class="badge">grade ${h(report.grade || "-")}</span>
          </div>
          <div class="item-meta">${h(report.limitation_note || job.report?.limitation_note || "")}</div>
          <div class="row-actions">
            <button type="button" data-model-job="${h(job.id)}">查看任务</button>
            ${report.id ? `<button type="button" data-model-report="${h(report.id)}">查看报告</button>` : ""}
          </div>
        </article>`
      );
      node.innerHTML = prepend ? item + node.innerHTML : item;
      bindModelLabButtons();
    }

    function renderModelTestJobDetail(job) {
      const node = document.getElementById("testResult");
      if (!job) {
        node.innerHTML = renderEmpty("任务不存在", "检测任务可能已被删除或无权访问。");
        return;
      }
      const report = job.report || {};
      node.innerHTML = (
        `<article class="item">
          <div class="item-title">Job #${h(job.id)} <span class="badge">${h(job.status)}</span></div>
          <div class="item-meta">${h(job.endpoint)} / ${h(job.protocol)} / ${h(job.requested_model || "-")}</div>
          <div class="item-meta">Key ${h(job.key_masked || "")} / worker ${h(job.worker_id || "-")}</div>
          <div class="inline-meta">
            <span class="badge">created ${h(job.created_at || "-")}</span>
            <span class="badge">updated ${h(job.updated_at || "-")}</span>
            <span class="badge">report ${report.id ? "#" + h(report.id) : "none"}</span>
            <span class="badge">visibility ${h(report.visibility || "-")}</span>
          </div>
          <div class="item-meta">${h(job.failure_reason || "")}</div>
          <div class="item-meta">${h(report.limitation_note || "")}</div>
          <div class="list">
            <div class="item-title">运行历史</div>
            ${renderRunHistory(job.runs || [])}
          </div>
          <div class="row-actions">
            ${report.id ? `<button type="button" data-model-report="${h(report.id)}">查看报告</button>` : ""}
          </div>
        </article>`
      );
      bindModelLabButtons();
    }

    function renderModelReportDetail(report) {
      const node = document.getElementById("reportList");
      if (!report) {
        node.innerHTML = renderEmpty("报告不存在", "报告可能已被删除或无权访问。");
        return;
      }
      const job = report.job || {};
      node.innerHTML = (
        `<article class="item" data-report="${h(report.id)}">
          <div class="item-title">Report #${h(report.id)} <span class="badge">${h(report.visibility)}</span> <span class="badge">${h(report.grade || "-")}</span></div>
          <div class="item-meta">Job #${h(report.job_id)} / ${h(job.endpoint || "-")} / ${h(job.protocol || "-")}</div>
          <div class="item-meta">Declared ${h(report.declared_model || "-")} / returned ${h(report.returned_model || "-")}</div>
          <div class="inline-meta">
            <span class="badge">suite ${h(report.suite_version || "-")}</span>
            ${job.status ? `<span class="badge">job ${h(job.status)}</span>` : ""}
            ${renderScoreBadges(report.scores || {})}
          </div>
          <div class="item-meta">${h(visibilityLabel(report.visibility))}</div>
          <div class="item-meta">${h(report.limitation_note || "")}</div>
          <div class="list">
            <div class="item-title">时间线</div>
            ${renderReportTimeline(report)}
          </div>
          <div class="list">
            <div class="item-title">运行历史</div>
            ${renderRunHistory(report.runs || [])}
          </div>
          <div class="list">
            <div class="item-title">脱敏证据摘要</div>
            ${renderEvidenceSummary(report.evidence_json || {})}
          </div>
          <div class="row-actions">
            ${renderVisibilityControls(report.id, report.visibility)}
            ${renderReportShareControls(report)}
          </div>
        </article>`
      );
      bindModelLabButtons();
    }

    function bindModelLabButtons() {
      document.querySelectorAll("[data-model-job]").forEach(button => {
        button.addEventListener("click", () => loadModelTestDetail(button.dataset.modelJob));
      });
      document.querySelectorAll("[data-model-report]").forEach(button => {
        button.addEventListener("click", () => loadModelReportDetail(button.dataset.modelReport));
      });
      document.querySelectorAll("[data-report-visibility]").forEach(button => {
        button.addEventListener("click", () => changeReportVisibility(button.dataset.reportVisibility, button.dataset.visibility));
      });
      document.querySelectorAll("[data-copy-report-url]").forEach(button => {
        button.addEventListener("click", async () => {
          try {
            const copied = await copyTextToClipboard(button.dataset.copyReportUrl || "");
            setState("reportState", copied ? "Report link copied" : "Copy unavailable", copied ? "ok" : "error");
          } catch (_error) {
            setState("reportState", "Copy failed", "error");
          }
        });
      });
      document.querySelectorAll("[data-share-report-url]").forEach(button => {
        button.addEventListener("click", () => shareReportLink(
          button.dataset.shareReportUrl || "",
          button.dataset.shareReportText || "",
        ));
      });
    }

    async function loadModelTests() {
      if (!currentUserId) {
        setState("testState", "Telegram user is required.", "error");
        document.getElementById("testResult").innerHTML = renderTelegramRequired();
        return;
      }
      setState("testState", "Loading");
      try {
        const url = new URL("/platform/api/relay-tests", window.location.origin);
        url.searchParams.set("limit", String(modelLabState.jobLimit));
        url.searchParams.set("offset", String(modelLabState.jobOffset));
        const payload = await apiFetch(url);
        const rows = payload.jobs || [];
        modelLabState.jobHasMore = Boolean(payload.has_more);
        const node = document.getElementById("testResult");
        node.innerHTML = rows.length ? rows.map(job => (
          `<article class="item" data-job="${h(job.id)}">
            <div class="item-title">Job #${h(job.id)} <span class="badge">${h(job.status)}</span> <span class="badge">${h(job.protocol)}</span></div>
            <div class="item-meta">${h(job.endpoint)} / ${h(job.requested_model || "-")}</div>
            <div class="item-meta">Key ${h(job.key_masked || "")} / worker ${h(job.worker_id || "-")}</div>
            <div class="inline-meta">
              <span class="badge">report ${job.report?.id ? "#" + h(job.report.id) : "none"}</span>
              <span class="badge">visibility ${h(job.report?.visibility || "-")}</span>
              <span class="badge">grade ${h(job.report?.grade || "-")}</span>
            </div>
            <div class="row-actions">
              <button type="button" data-model-job="${h(job.id)}">查看任务</button>
              ${job.report?.id ? `<button type="button" data-model-report="${h(job.report.id)}">查看报告</button>` : ""}
            </div>
          </article>`
        )).join("") : renderEmpty(
          "暂无检测任务",
          "还没有创建接口检测任务。",
          `<button type="button" data-scroll-to="testForm">创建检测任务</button>`
        );
        bindUtilityButtons(node);
        bindModelLabButtons();
        setState("testState", `${rows.length} jobs`, rows.length ? "ok" : "");
      } catch (error) {
        setState("testState", error.message || "Load failed", "error");
      }
    }

    async function loadModelReports() {
      if (!currentUserId) {
        setState("reportState", "Telegram user is required.", "error");
        document.getElementById("reportList").innerHTML = renderTelegramRequired();
        return;
      }
      setState("reportState", "Loading");
      try {
        const url = new URL("/platform/api/reports", window.location.origin);
        url.searchParams.set("limit", String(modelLabState.reportLimit));
        url.searchParams.set("offset", String(modelLabState.reportOffset));
        const payload = await apiFetch(url);
        const rows = payload.reports || [];
        modelLabState.reportHasMore = Boolean(payload.has_more);
        const reportList = document.getElementById("reportList");
        reportList.innerHTML = rows.length ? rows.map(report => (
          `<article class="item" data-report="${h(report.id)}">
            <div class="item-title">Report #${h(report.id)} <span class="badge">${h(report.visibility)}</span> <span class="badge">${h(report.grade || "-")}</span></div>
            <div class="item-meta">Job #${h(report.job_id)} / ${h(report.declared_model || "-")} / ${h(report.returned_model || "-")}</div>
            <div class="inline-meta">
              <span class="badge">suite ${h(report.suite_version || "-")}</span>
              <span class="badge">created ${h(report.created_at || "-")}</span>
            </div>
            <div class="item-meta">${h(report.limitation_note || "")}</div>
            <div class="row-actions">
              <button type="button" data-model-report="${h(report.id)}">查看报告</button>
              ${renderVisibilityControls(report.id, report.visibility)}
              ${renderReportShareControls(report)}
            </div>
          </article>`
        )).join("") : renderEmpty(
          "暂无检测报告",
          "完成检测后会生成报告。",
          `<button type="button" data-scroll-to="testForm">创建检测任务</button>`
        );
        bindUtilityButtons(reportList);
        bindModelLabButtons();
        setState("reportState", `${rows.length} reports`, rows.length ? "ok" : "");
      } catch (error) {
        setState("reportState", error.message || "Load failed", "error");
      }
    }

    async function loadModelTestDetail(jobId) {
      modelLabState.activeJobId = String(jobId);
      setState("testState", "Loading detail");
      try {
        const payload = await apiFetch(`/platform/api/relay-tests/${jobId}`);
        modelLabState.jobDetail = payload.result || null;
        renderModelTestJobDetail(modelLabState.jobDetail);
        setState("testState", "Detail loaded", "ok");
      } catch (error) {
        setState("testState", error.message || "Load failed", "error");
      }
    }

    async function loadModelReportDetail(reportId) {
      modelLabState.activeReportId = String(reportId);
      setState("reportState", "Loading detail");
      try {
        const payload = await apiFetch(`/platform/api/reports/${reportId}`);
        modelLabState.reportDetail = payload.result || null;
        renderModelReportDetail(modelLabState.reportDetail);
        setState("reportState", "Detail loaded", "ok");
      } catch (error) {
        setState("reportState", error.message || "Load failed", "error");
      }
    }

    async function changeReportVisibility(reportId, visibility) {
      try {
        await apiFetch(`/platform/api/reports/${reportId}/visibility`, {
          method: "POST",
          body: JSON.stringify({ user_id: currentUserId, visibility }),
        });
        await loadModelReports();
        if (modelLabState.activeReportId === String(reportId)) {
          await loadModelReportDetail(reportId);
        }
      } catch (error) {
        alert(error.message || "Visibility change failed");
      }
    }

    async function loadLedger() {
      if (!currentUserId) {
        setState("ledgerState", "Telegram user is required.", "error");
        document.getElementById("ledgerList").innerHTML = renderTelegramRequired();
        return;
      }
      setState("ledgerState", "Loading");
      try {
        const payload = await apiFetch(`/platform/api/users/${currentUserId}/ledger?limit=20`);
        const ledger = payload.ledger || {};
        const balances = ledger.balances || {};
        const rows = ledger.entries || [];
        document.getElementById("ledgerList").innerHTML = (
          `<article class="item">
            <div class="item-title">Balance ${h(balances.balance || "0.00")} / Points ${h(balances.points || "0.00")}</div>
          </article>` +
          (rows.length ? rows.map(entry => (
            `<article class="item">
              <div class="item-title">${h(entry.entry_type)} <span class="badge">${h(entry.account_type)}</span></div>
              <div class="item-meta">${h(entry.amount)} / ${h(entry.status)} / ${h(entry.created_at)}</div>
            </article>`
          )).join("") : renderEmpty("暂无账本条目", "当前账户还没有平台账本记录。"))
        );
        setState("ledgerState", `${rows.length} entries`, "ok");
      } catch (error) {
        setState("ledgerState", error.message || "Load failed", "error");
      }
    }

    selectTab(["channels", "relays", "model_lab", "contribute", "wallet"].includes(initialTab) ? initialTab : "channels");
  </script>
</body>
</html>
"""


PLATFORM_PUBLIC_REPORT_HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>TGSellBot Model Lab Report</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f5f6f8;
      --panel: #ffffff;
      --line: #d9dee6;
      --text: #18212f;
      --muted: #657084;
      --accent: #006d5b;
      --danger: #b42318;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font: 15px/1.45 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    header {
      border-bottom: 1px solid var(--line);
      background: var(--panel);
      padding: 16px;
    }
    main {
      width: min(920px, 100%);
      margin: 0 auto;
      padding: 16px;
    }
    h1 {
      margin: 0;
      font-size: 20px;
      line-height: 1.25;
    }
    button {
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
      color: var(--text);
      cursor: pointer;
      font: inherit;
      padding: 8px 10px;
    }
    button.primary {
      background: var(--accent);
      border-color: var(--accent);
      color: #fff;
    }
    .subhead {
      color: var(--muted);
      margin-top: 6px;
    }
    .item {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      margin-bottom: 12px;
      padding: 14px;
    }
    .item-title {
      font-weight: 700;
      margin-bottom: 6px;
    }
    .item-meta {
      color: var(--muted);
      font-size: 13px;
      margin-top: 4px;
      overflow-wrap: anywhere;
    }
    .badge {
      display: inline-block;
      border: 1px solid var(--line);
      border-radius: 999px;
      color: var(--muted);
      font-size: 12px;
      margin: 2px 4px 2px 0;
      padding: 2px 7px;
    }
    .row-actions {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 10px;
    }
    .state {
      color: var(--muted);
      min-height: 22px;
      margin-bottom: 10px;
    }
    .state.error { color: var(--danger); }
    .state.ok { color: var(--accent); }
  </style>
</head>
<body>
  <header>
    <h1>TGSellBot Model Lab Report</h1>
    <div class="subhead">只展示协议兼容、能力一致性和疑似降级风险评估。黑盒测试不能证明真实上游模型。</div>
  </header>
  <main>
    <div id="state" class="state"></div>
    <div id="content"></div>
  </main>
  <script>
    function h(value) {
      return String(value ?? "").replace(/[&<>"']/g, char => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
      }[char]));
    }

    function setState(message, mode = "") {
      const node = document.getElementById("state");
      node.textContent = message || "";
      node.className = "state" + (mode ? " " + mode : "");
    }

    async function apiFetch(url) {
      const response = await fetch(url);
      const payload = await response.json();
      if (!response.ok || !payload.ok) throw new Error(payload.error || `HTTP ${response.status}`);
      return payload;
    }

    function renderScoreBadges(scores) {
      const entries = Object.entries(scores || {});
      if (!entries.length) return `<span class="badge">scores unavailable</span>`;
      return entries.map(([key, value]) => `<span class="badge">${h(key)} ${h(value)}</span>`).join("");
    }

    function renderEvidenceSummary(evidence) {
      const entries = Object.entries(evidence || {});
      if (!entries.length) return `<div class="item-meta">暂无证据摘要</div>`;
      return entries.slice(0, 8).map(([key, value]) => (
        `<div class="item-meta">${h(key)}: ${h(typeof value === "object" ? JSON.stringify(value) : value)}</div>`
      )).join("");
    }

    function renderRunHistory(runs) {
      const rows = runs || [];
      if (!rows.length) return `<div class="item-meta">暂无运行历史</div>`;
      return rows.map(run => (
        `<div class="item-meta">Run #${h(run.id)} · ${h(run.status || "-")} · worker ${h(run.worker_id || "-")} · ${h(run.duration_ms || 0)}ms · requests ${h(run.request_count || 0)} · tokens ${h(run.total_tokens || 0)}${run.estimated_cost ? " · cost " + h(run.estimated_cost) : ""}${run.error_type ? " · " + h(run.error_type) : ""}${run.error_summary ? " · " + h(run.error_summary) : ""} · ${h(run.created_at || "-")}</div>`
      )).join("");
    }

    function reportUrl(report) {
      const url = new URL(`/platform/reports/${report.id}`, window.location.origin);
      if (report.visibility === "unlisted" && report.share_token) {
        url.searchParams.set("token", report.share_token);
      }
      return url.toString();
    }

    function reportShareText(report) {
      const parts = [
        `TGSellBot Model Lab Report #${report?.id || ""}`,
        report?.grade ? `grade ${report.grade}` : "",
        report?.declared_model ? `declared ${report.declared_model}` : "",
        report?.returned_model ? `returned ${report.returned_model}` : "",
      ].filter(Boolean);
      return parts.join(" · ");
    }

    async function copyTextToClipboard(value) {
      const text = String(value || "");
      if (!text) return false;
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(text);
        return true;
      }
      const textarea = document.createElement("textarea");
      textarea.value = text;
      textarea.setAttribute("readonly", "");
      textarea.style.position = "fixed";
      textarea.style.left = "-9999px";
      document.body.appendChild(textarea);
      textarea.select();
      let copied = false;
      try {
        copied = document.execCommand("copy");
      } finally {
        textarea.remove();
      }
      return copied;
    }

    function telegramShareUrl(url, text) {
      const share = new URL("https://t.me/share/url");
      share.searchParams.set("url", url);
      if (text) share.searchParams.set("text", text);
      return share.toString();
    }

    async function shareReportLink(url, text) {
      if (!url) {
        setState("No public report link", "error");
        return;
      }
      if (navigator.share) {
        try {
          await navigator.share({ title: "TGSellBot Model Lab Report", text, url });
          setState("Share sheet opened", "ok");
          return;
        } catch (error) {
          if (error?.name === "AbortError") return;
        }
      }
      window.open(telegramShareUrl(url, text), "_blank", "noopener,noreferrer");
      setState("Telegram share opened", "ok");
    }

    function renderReport(report, compact = false) {
      const job = report.job || {};
      const publicUrl = reportUrl(report);
      const shareText = reportShareText(report);
      return (
        `<article class="item" data-public-report="${h(report.id)}">
          <div class="item-title">Report #${h(report.id)} <span class="badge">${h(report.visibility)}</span> <span class="badge">${h(report.grade || "-")}</span></div>
          <div class="item-meta">Job #${h(report.job_id)} / ${h(job.endpoint || "-")} / ${h(job.protocol || "-")}</div>
          <div class="item-meta">Declared ${h(report.declared_model || "-")} / returned ${h(report.returned_model || "-")}</div>
          <div class="item-meta">${h(report.limitation_note || "")}</div>
          <div>${renderScoreBadges(report.scores || {})}</div>
          ${compact ? "" : `<div class="item-title">运行历史</div>${renderRunHistory(report.runs || [])}`}
          ${compact ? "" : `<div class="item-title">脱敏证据摘要</div>${renderEvidenceSummary(report.evidence_json || {})}`}
          <div class="row-actions">
            ${compact ? `<button class="primary" type="button" data-open-report="${h(report.id)}">查看报告</button>` : ""}
            <button type="button" data-copy-report-url="${h(publicUrl)}">复制链接</button>
            <button type="button" data-share-report-url="${h(publicUrl)}" data-share-report-text="${h(shareText)}">分享报告</button>
          </div>
        </article>`
      );
    }

    function bindButtons() {
      document.querySelectorAll("[data-open-report]").forEach(button => {
        button.addEventListener("click", () => {
          window.location.href = `/platform/reports/${button.dataset.openReport}`;
        });
      });
      document.querySelectorAll("[data-copy-report-url]").forEach(button => {
        button.addEventListener("click", async () => {
          try {
            const copied = await copyTextToClipboard(button.dataset.copyReportUrl || "");
            setState(copied ? "Link copied" : "Copy unavailable", copied ? "ok" : "error");
          } catch (_error) {
            setState("Copy failed", "error");
          }
        });
      });
      document.querySelectorAll("[data-share-report-url]").forEach(button => {
        button.addEventListener("click", () => shareReportLink(
          button.dataset.shareReportUrl || "",
          button.dataset.shareReportText || "",
        ));
      });
    }

    async function loadReport(reportId) {
      const params = new URLSearchParams(window.location.search);
      const url = new URL(`/platform/api/public/reports/${reportId}`, window.location.origin);
      if (params.get("token")) url.searchParams.set("token", params.get("token"));
      setState("Loading");
      const payload = await apiFetch(url);
      document.getElementById("content").innerHTML = renderReport(payload.result || {});
      setState("Report loaded", "ok");
      bindButtons();
    }

    async function loadPublicList() {
      setState("Loading");
      const payload = await apiFetch("/platform/api/public/reports?limit=20");
      const rows = payload.reports || [];
      document.getElementById("content").innerHTML = rows.length
        ? rows.map(report => renderReport(report, true)).join("")
        : `<article class="item"><div class="item-meta">暂无公开报告</div></article>`;
      setState(`${rows.length} public reports`, rows.length ? "ok" : "");
      bindButtons();
    }

    (async function boot() {
      try {
        const match = window.location.pathname.match(/\/platform\/reports\/(\d+)$/);
        if (match) {
          await loadReport(match[1]);
        } else {
          await loadPublicList();
        }
      } catch (error) {
        setState(error.message || "Load failed", "error");
      }
    })();
  </script>
</body>
</html>
"""
