import json
from unittest.mock import AsyncMock, patch

from sqlalchemy import select
from starlette.requests import Request

from bot.database import Database
from bot.database.methods.audit import log_audit
from bot.database.methods.platform import (
    create_ledger_entry,
    record_model_test_run,
    submit_channel,
    submit_relay_provider,
    verify_relay_claim,
)
from bot.database.methods import (
    get_or_create_group_invite_link,
    perform_daily_checkin,
    record_group_invite_join,
    reward_group_inviter_after_checkin,
    settle_mature_group_invite_rewards,
)
from bot.database.methods.read import check_user
from bot.database.methods.read import get_role_id_by_name
from bot.database.models.main import BotSettings
from bot.database.models.main import LedgerEntries
from bot.web.platform import (
    api_admin_channel_report_review,
    api_admin_channel_reports,
    api_admin_channel_detail,
    api_admin_channel_review,
    api_admin_channel_claims,
    api_admin_channel_submissions,
    api_admin_dashboard,
    api_admin_fraud_event_review,
    api_admin_fraud_events,
    api_admin_audit_logs,
    api_admin_invite_reward_review,
    api_admin_invite_rewards,
    api_admin_owner_dashboards,
    api_admin_relays,
    api_admin_review_workload,
    api_admin_relay_detail,
    api_admin_relay_review,
    api_admin_relay_claims,
    api_admin_relay_feedback,
    api_admin_relay_feedback_review,
    api_channel_claim,
    api_channel_claim_review,
    api_channel_interaction,
    api_channel_detail,
    api_channel_owner_profile,
    api_create_model_test,
    api_discover_channels,
    api_discover_relays,
    api_create_report,
    api_relay_detail,
    api_relay_claim,
    api_relay_claim_review,
    api_relay_feedback,
    api_relay_owner_profile,
    api_get_model_test,
    api_get_report,
    api_list_model_tests,
    api_list_reports,
    api_owner_dashboard,
    api_public_report,
    api_public_reports,
    api_ledger,
    api_user_appeal,
    api_report_visibility,
    api_submit_relay,
    api_submit_channel,
    platform_mini_app_page,
    platform_public_report_page,
    platform_review_app_page,
    platform_routes,
    PlatformAPIError,
)
from tests.test_telegram_init_data import make_init_data


def _request(
        *,
        method: str = "GET",
        path: str = "/",
        path_params: dict | None = None,
        query: str = "",
        body: dict | None = None,
        authenticated: bool = True,
        init_data: str | None = None,
) -> Request:
    payload = json.dumps(body or {}).encode("utf-8")
    headers = [(b"content-type", b"application/json")]
    if init_data is not None:
        headers.append((b"x-telegram-init-data", init_data.encode("utf-8")))
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "headers": headers,
        "query_string": query.encode("utf-8"),
        "path_params": path_params or {},
        "session": {"authenticated": authenticated},
    }

    async def receive():
        return {"type": "http.request", "body": payload, "more_body": False}

    return Request(scope, receive)


def _json(response):
    return json.loads(response.body.decode("utf-8"))


async def _async_value(value):
    return value


async def _set_platform_api_enabled(value: str) -> None:
    await BotSettings.insert_defaults()
    async with Database().session() as s:
        setting = (
            await s.execute(select(BotSettings).where(BotSettings.key == "platform_api_enabled"))
        ).scalars().one()
        setting.value = value


async def _role_user(user_factory, telegram_id: int, role_name: str = "REVIEWER"):
    role_id = await get_role_id_by_name(role_name)
    assert role_id is not None
    return await user_factory(telegram_id=telegram_id, role_id=role_id)


class TestPlatformAPI:
    async def test_platform_api_requires_session_and_feature_flag(self, user_factory):
        await user_factory(telegram_id=240001)
        await _set_platform_api_enabled("1")
        request = _request(
            method="POST",
            path="/platform/api/channels/submissions",
            body={"user_id": 240001, "channel": "@test", "category": "ai", "language": "zh", "reason": "test"},
            authenticated=False,
        )

        unauthorized = await api_submit_channel(request)
        assert unauthorized.status_code == 401
        assert _json(unauthorized)["code"] == "telegram_init_data_invalid"

    async def test_platform_api_returns_404_when_feature_flag_is_disabled(self, user_factory):
        await user_factory(telegram_id=240001)
        await _set_platform_api_enabled("0")
        request = _request(
            method="POST",
            path="/platform/api/channels/submissions",
            body={"user_id": 240001, "channel": "@test", "category": "ai", "language": "zh", "reason": "test"},
        )
        disabled = await api_submit_channel(request)

        assert disabled.status_code == 404
        assert _json(disabled)["code"] == "platform_disabled"

    async def test_mini_app_api_creates_channel_and_reads_own_ledger(self, user_factory):
        await _set_platform_api_enabled("1")
        await user_factory(telegram_id=240002)
        await create_ledger_entry(
            240002,
            "points",
            "opening_balance",
            9,
            idempotency_key="api-ledger-240002-points",
        )
        await create_ledger_entry(
            240002,
            "points",
            "group_invite_reward",
            3,
            idempotency_key="api-ledger-240002-points-reward",
        )
        await create_ledger_entry(
            240002,
            "balance",
            "opening_balance",
            5,
            idempotency_key="api-ledger-240002-balance",
        )

        channel_request = _request(
            method="POST",
            path="/platform/api/channels/submissions",
            body={
                "user_id": 240002,
                "channel": "https://t.me/Api_Channel",
                "category": "ai",
                "language": "zh",
                "reason": "api test",
            },
            authenticated=False,
            init_data=make_init_data(240002, token="test_token"),
        )
        channel_response = await api_submit_channel(channel_request)
        ledger_response = await api_ledger(_request(
            path="/platform/api/users/240002/ledger",
            path_params={"user_id": 240002},
            query="account_type=points&limit=1",
            authenticated=False,
            init_data=make_init_data(240002, token="test_token"),
        ))
        ledger_page_two = await api_ledger(_request(
            path="/platform/api/users/240002/ledger",
            path_params={"user_id": 240002},
            query="account_type=points&limit=1&offset=1",
            authenticated=False,
            init_data=make_init_data(240002, token="test_token"),
        ))
        forbidden_ledger = await api_ledger(_request(
            path="/platform/api/users/240003/ledger",
            path_params={"user_id": 240003},
            query="account_type=points",
            authenticated=False,
            init_data=make_init_data(240002, token="test_token"),
        ))

        assert channel_response.status_code == 201
        assert _json(channel_response)["result"]["channel"]["username"] == "api_channel"
        assert ledger_response.status_code == 200
        assert _json(ledger_response)["ledger"]["balances"]["points"] == "12.00"
        assert _json(ledger_response)["ledger"]["balances"]["balance"] == "5.00"
        assert _json(ledger_response)["ledger"]["total"] == 2
        assert _json(ledger_response)["ledger"]["has_more"] is True
        assert len(_json(ledger_response)["ledger"]["entries"]) == 1
        assert ledger_page_two.status_code == 200
        assert _json(ledger_page_two)["ledger"]["offset"] == 1
        assert _json(ledger_page_two)["ledger"]["has_more"] is False
        assert len(_json(ledger_page_two)["ledger"]["entries"]) == 1
        assert forbidden_ledger.status_code == 403
        assert _json(forbidden_ledger)["code"] == "forbidden"

    async def test_mini_app_api_discovers_filters_pages_and_claims_channel(self, user_factory):
        await _set_platform_api_enabled("1")
        await _role_user(user_factory, 240020)
        init_data = make_init_data(240020, token="test_token")
        first = await submit_channel(
            {
                "channel": "@api_discover_one",
                "category": "ai",
                "language": "zh",
                "title": "Discover One",
                "reason": "test",
            },
            submitter_id=240020,
        )
        second = await submit_channel(
            {
                "channel": "@api_discover_two",
                "category": "ai",
                "language": "en",
                "title": "Discover Two",
                "reason": "test",
            },
            submitter_id=240020,
        )
        await api_admin_channel_review(_request(
            method="POST",
            path=f"/platform/api/admin/channels/submissions/{first['submission']['id']}/review",
            path_params={"submission_id": first["submission"]["id"]},
            body={"user_id": 240020, "status": "approved"},
            authenticated=True,
        ))
        await api_admin_channel_review(_request(
            method="POST",
            path=f"/platform/api/admin/channels/submissions/{second['submission']['id']}/review",
            path_params={"submission_id": second["submission"]["id"]},
            body={"user_id": 240020, "status": "approved"},
            authenticated=True,
        ))

        page = await api_discover_channels(_request(
            path="/platform/api/channels/discover",
            query="category=ai&limit=1&offset=0",
            authenticated=False,
            init_data=init_data,
        ))
        zh_only = await api_discover_channels(_request(
            path="/platform/api/channels/discover",
            query="category=ai&language=zh&limit=10&offset=0",
            authenticated=False,
            init_data=init_data,
        ))
        claim = await api_channel_claim(_request(
            method="POST",
            path=f"/platform/api/channels/{first['channel']['id']}/claim",
            path_params={"channel_id": first["channel"]["id"]},
            body={"user_id": 240020, "method": "challenge"},
            authenticated=False,
            init_data=init_data,
        ))
        claim_list = await api_admin_channel_claims(_request(
            path="/platform/api/admin/channel-claims",
            query="status=pending",
            authenticated=True,
        ))
        detail = await api_channel_detail(_request(
            path=f"/platform/api/channels/{first['channel']['id']}",
            path_params={"channel_id": first["channel"]["id"]},
            authenticated=False,
            init_data=init_data,
        ))

        page_payload = _json(page)
        zh_payload = _json(zh_only)
        claim_payload = _json(claim)
        claim_queue_payload = _json(claim_list)
        detail_payload = _json(detail)["result"]

        assert page.status_code == 200
        assert page_payload["total"] == 2
        assert page_payload["has_more"] is True
        assert len(page_payload["channels"]) == 1
        assert zh_payload["total"] == 1
        assert zh_payload["channels"][0]["username"] == "api_discover_one"
        assert claim.status_code == 201
        assert claim_payload["result"]["channel_id"] == first["channel"]["id"]
        assert claim_payload["result"]["status"] == "pending"
        assert claim_payload["result"]["verification"]["expected_text"] == f"TGSellBot claim {claim_payload['result']['challenge']}"
        assert claim_list.status_code == 200
        queued_claim = claim_queue_payload["claims"][0]["claim"]
        assert queued_claim["id"] == claim_payload["result"]["id"]
        assert queued_claim["verification"]["challenge"] == claim_payload["result"]["challenge"]
        assert queued_claim["verification"]["expected_text"] == claim_payload["result"]["verification"]["expected_text"]
        assert detail.status_code == 200
        assert "challenge" not in detail_payload["claims"][0]
        assert detail_payload["claims"][0]["verification"]["challenge_required"] is True

    async def test_admin_api_live_verifies_bot_admin_channel_claims(self, user_factory):
        await _set_platform_api_enabled("1")
        await _role_user(user_factory, 240030)
        await user_factory(telegram_id=240031)
        claimant_init_data = make_init_data(240031, token="test_token")
        submission = await submit_channel(
            {
                "channel": "@api_bot_admin_claim",
                "category": "ai",
                "language": "zh",
                "title": "Bot Admin Claim",
                "reason": "live bot admin verification",
            },
            submitter_id=240030,
        )
        await api_admin_channel_review(_request(
            method="POST",
            path=f"/platform/api/admin/channels/submissions/{submission['submission']['id']}/review",
            path_params={"submission_id": submission["submission"]["id"]},
            body={"user_id": 240030, "status": "approved"},
            authenticated=True,
        ))
        claim_response = await api_channel_claim(_request(
            method="POST",
            path=f"/platform/api/channels/{submission['channel']['id']}/claim",
            path_params={"channel_id": submission["channel"]["id"]},
            body={"user_id": 240031, "method": "bot_admin"},
            authenticated=False,
            init_data=claimant_init_data,
        ))
        claim = _json(claim_response)["result"]

        live_proof = {
            "verified": True,
            "channel_id": submission["channel"]["id"],
            "claimant_id": 240031,
            "telegram_chat": "@api_bot_admin_claim",
            "telegram_status": "administrator",
        }
        with patch("bot.web.platform._verify_channel_bot_admin_claim", new=AsyncMock(return_value=live_proof)) as verifier:
            approval = await api_channel_claim_review(_request(
                method="POST",
                path=f"/platform/api/channel-claims/{claim['id']}/review",
                path_params={"claim_id": claim["id"]},
                body={"user_id": 240030, "approved": True},
                authenticated=True,
            ))

        detail = await api_channel_detail(_request(
            path=f"/platform/api/channels/{submission['channel']['id']}",
            path_params={"channel_id": submission["channel"]["id"]},
            authenticated=False,
            init_data=claimant_init_data,
        ))

        assert claim_response.status_code == 201
        assert claim["method"] == "bot_admin"
        assert claim["verification"]["admin_rights_required"] is True
        assert verifier.await_count == 1
        assert approval.status_code == 200
        detail_payload = _json(detail)["result"]
        assert detail_payload["claim"]["status"] == "approved"
        assert detail_payload["viewer"]["can_edit_profile"] is True

    async def test_admin_api_rejects_bot_admin_claim_when_live_check_fails(self, user_factory):
        await _set_platform_api_enabled("1")
        await _role_user(user_factory, 240032)
        await user_factory(telegram_id=240033)
        claimant_init_data = make_init_data(240033, token="test_token")
        submission = await submit_channel(
            {
                "channel": "@api_bot_admin_claim_fail",
                "category": "ai",
                "language": "zh",
                "title": "Bot Admin Claim Fail",
                "reason": "live bot admin verification failure",
            },
            submitter_id=240032,
        )
        await api_admin_channel_review(_request(
            method="POST",
            path=f"/platform/api/admin/channels/submissions/{submission['submission']['id']}/review",
            path_params={"submission_id": submission["submission"]["id"]},
            body={"user_id": 240032, "status": "approved"},
            authenticated=True,
        ))
        claim_response = await api_channel_claim(_request(
            method="POST",
            path=f"/platform/api/channels/{submission['channel']['id']}/claim",
            path_params={"channel_id": submission["channel"]["id"]},
            body={"user_id": 240033, "method": "bot_admin"},
            authenticated=False,
            init_data=claimant_init_data,
        ))
        claim = _json(claim_response)["result"]

        with patch(
            "bot.web.platform._verify_channel_bot_admin_claim",
            new=AsyncMock(side_effect=PlatformAPIError(
                "Claimant is not a Telegram channel administrator.",
                409,
                "bot_admin_verification_failed",
            )),
        ):
            approval = await api_channel_claim_review(_request(
                method="POST",
                path=f"/platform/api/channel-claims/{claim['id']}/review",
                path_params={"claim_id": claim["id"]},
                body={"user_id": 240032, "approved": True},
                authenticated=True,
            ))

        detail = await api_channel_detail(_request(
            path=f"/platform/api/channels/{submission['channel']['id']}",
            path_params={"channel_id": submission["channel"]["id"]},
            authenticated=False,
            init_data=claimant_init_data,
        ))

        assert approval.status_code == 409
        assert _json(approval)["code"] == "bot_admin_verification_failed"
        detail_payload = _json(detail)["result"]
        assert detail_payload["claim"]["status"] == "unclaimed"
        assert detail_payload["claims"][0]["status"] == "pending"
        assert detail_payload["viewer"]["can_edit_profile"] is False

    async def test_mini_app_api_reads_channel_detail_and_updates_viewer_state(self, user_factory):
        await _set_platform_api_enabled("1")
        await _role_user(user_factory, 240026)
        await user_factory(telegram_id=240027)
        init_data = make_init_data(240027, token="test_token")
        submission = await submit_channel(
            {
                "channel": "@api_detail_channel",
                "category": "ai",
                "language": "zh",
                "title": "API Detail",
                "reason": "detail api",
            },
            submitter_id=240026,
        )
        await api_admin_channel_review(_request(
            method="POST",
            path=f"/platform/api/admin/channels/submissions/{submission['submission']['id']}/review",
            path_params={"submission_id": submission["submission"]["id"]},
            body={"user_id": 240026, "status": "approved"},
            authenticated=True,
        ))
        await api_channel_interaction(_request(
            method="POST",
            path=f"/platform/api/channels/{submission['channel']['id']}/interactions",
            path_params={"channel_id": submission["channel"]["id"]},
            body={"user_id": 240027, "action": "favorite", "source": "mini_app"},
            authenticated=False,
            init_data=init_data,
        ))

        detail = await api_channel_detail(_request(
            path=f"/platform/api/channels/{submission['channel']['id']}",
            path_params={"channel_id": submission["channel"]["id"]},
            authenticated=False,
            init_data=init_data,
        ))

        assert detail.status_code == 200
        detail_payload = _json(detail)["result"]
        assert detail_payload["channel"]["username"] == "api_detail_channel"
        assert detail_payload["viewer"]["favorite"] is True
        assert detail_payload["viewer"]["can_edit_profile"] is False
        assert detail_payload["interactions"]["favorite"] == 1
        assert detail_payload["submissions"][0]["reason"] == "detail api"
        assert detail_payload["audit_trail"]

    async def test_mini_app_api_reads_model_test_job_and_report_by_owner(self, user_factory):
        await _set_platform_api_enabled("1")
        await user_factory(telegram_id=240003)
        await user_factory(telegram_id=240004)
        init_data = make_init_data(240003, token="test_token")
        other_init_data = make_init_data(240004, token="test_token")

        job_response = await api_create_model_test(_request(
            method="POST",
            path="/platform/api/relay-tests",
            body={
                "user_id": 240003,
                "endpoint": "https://api-relay.example.com/v1",
                "protocol": "openai-compatible",
                "requested_model": "gpt-4.1",
                "api_key": "sk-api-test-secret",
                "idempotency_key": "api-job-240003",
            },
            authenticated=False,
            init_data=init_data,
        ))
        job = _json(job_response)["result"]
        report_response = await api_create_report(_request(
            method="POST",
            path=f"/platform/api/relay-tests/{job['id']}/reports",
            path_params={"job_id": job["id"]},
            body={
                "user_id": 240003,
                "declared_model": "gpt-4.1",
                "returned_model": "gpt-4.1",
                "suite_version": "p0",
                "scores": {"protocol": 1},
                "evidence_json": {"authorization": "Bearer secret", "result": "ok"},
            },
            authenticated=False,
            init_data=init_data,
        ))
        report = _json(report_response)["result"]
        second_job_response = await api_create_model_test(_request(
            method="POST",
            path="/platform/api/relay-tests",
            body={
                "user_id": 240003,
                "endpoint": "https://api-relay-two.example.com/v1",
                "protocol": "openai-compatible",
                "requested_model": "gpt-4.1-mini",
                "api_key": "sk-api-test-secret-two",
                "idempotency_key": "api-job-240003-second",
            },
            authenticated=False,
            init_data=init_data,
        ))
        second_job = _json(second_job_response)["result"]
        second_report_response = await api_create_report(_request(
            method="POST",
            path=f"/platform/api/relay-tests/{second_job['id']}/reports",
            path_params={"job_id": second_job["id"]},
            body={
                "user_id": 240003,
                "declared_model": "gpt-4.1-mini",
                "returned_model": "gpt-4.1-mini",
                "suite_version": "p0",
                "scores": {"protocol": 1},
                "evidence_json": {"result": "ok"},
            },
            authenticated=False,
            init_data=init_data,
        ))
        second_report = _json(second_report_response)["result"]

        loaded_job = await api_get_model_test(_request(
            path=f"/platform/api/relay-tests/{job['id']}",
            path_params={"job_id": job["id"]},
            query="user_id=240003",
            authenticated=False,
            init_data=init_data,
        ))
        loaded_report = await api_get_report(_request(
            path=f"/platform/api/reports/{report['id']}",
            path_params={"report_id": report["id"]},
            query="user_id=240003",
            authenticated=False,
            init_data=init_data,
        ))
        listed_jobs = await api_list_model_tests(_request(
            path="/platform/api/relay-tests",
            query="user_id=240003&limit=1",
            authenticated=False,
            init_data=init_data,
        ))
        listed_jobs_page_two = await api_list_model_tests(_request(
            path="/platform/api/relay-tests",
            query="user_id=240003&limit=1&offset=1",
            authenticated=False,
            init_data=init_data,
        ))
        listed_reports = await api_list_reports(_request(
            path="/platform/api/reports",
            query="user_id=240003&limit=1",
            authenticated=False,
            init_data=init_data,
        ))
        listed_reports_page_two = await api_list_reports(_request(
            path="/platform/api/reports",
            query="user_id=240003&limit=1&offset=1",
            authenticated=False,
            init_data=init_data,
        ))
        visibility = await api_report_visibility(_request(
            method="POST",
            path=f"/platform/api/reports/{report['id']}/visibility",
            path_params={"report_id": report["id"]},
            body={"user_id": 240003, "visibility": "public"},
            authenticated=False,
            init_data=init_data,
        ))
        updated_report = await api_get_report(_request(
            path=f"/platform/api/reports/{report['id']}",
            path_params={"report_id": report["id"]},
            query="user_id=240003",
            authenticated=False,
            init_data=init_data,
        ))
        blocked_report = await api_get_report(_request(
            path=f"/platform/api/reports/{report['id']}",
            path_params={"report_id": report["id"]},
            query="user_id=240004",
            authenticated=False,
            init_data=init_data,
        ))
        other_user_reports = await api_list_reports(_request(
            path="/platform/api/reports",
            query="user_id=240004",
            authenticated=False,
            init_data=other_init_data,
        ))
        other_visibility = await api_report_visibility(_request(
            method="POST",
            path=f"/platform/api/reports/{report['id']}/visibility",
            path_params={"report_id": report["id"]},
            body={"user_id": 240004, "visibility": "private"},
            authenticated=False,
            init_data=other_init_data,
        ))
        admin_only = await api_channel_claim_review(_request(
            method="POST",
            path="/platform/api/channel-claims/1/review",
            path_params={"claim_id": 1},
            body={"approved": True},
            authenticated=False,
            init_data=init_data,
        ))

        assert job_response.status_code == 201
        assert second_job_response.status_code == 201
        assert second_report_response.status_code == 201
        assert "sk-api-test-secret" not in str(job)
        assert "sk-api-test-secret-two" not in str(second_job)
        assert loaded_job.status_code == 200
        assert _json(loaded_job)["result"]["status"] == "completed"
        assert _json(loaded_job)["result"]["report"]["id"] == report["id"]
        assert listed_jobs.status_code == 200
        assert _json(listed_jobs)["total"] == 2
        assert _json(listed_jobs)["has_more"] is True
        assert len(_json(listed_jobs)["jobs"]) == 1
        assert listed_jobs_page_two.status_code == 200
        assert _json(listed_jobs_page_two)["offset"] == 1
        assert _json(listed_jobs_page_two)["has_more"] is False
        assert {row["id"] for row in _json(listed_jobs)["jobs"] + _json(listed_jobs_page_two)["jobs"]} == {job["id"], second_job["id"]}
        assert listed_reports.status_code == 200
        assert _json(listed_reports)["total"] == 2
        assert _json(listed_reports)["has_more"] is True
        assert len(_json(listed_reports)["reports"]) == 1
        assert listed_reports_page_two.status_code == 200
        assert _json(listed_reports_page_two)["offset"] == 1
        assert _json(listed_reports_page_two)["has_more"] is False
        assert {row["id"] for row in _json(listed_reports)["reports"] + _json(listed_reports_page_two)["reports"]} == {report["id"], second_report["id"]}
        assert visibility.status_code == 200
        assert _json(updated_report)["result"]["visibility"] == "public"
        assert loaded_report.status_code == 200
        assert _json(loaded_report)["result"]["evidence_json"]["authorization"] != "Bearer secret"
        assert blocked_report.status_code == 403
        assert other_user_reports.status_code == 200
        assert _json(other_user_reports)["reports"] == []
        assert other_visibility.status_code == 404
        assert admin_only.status_code == 403
        assert _json(admin_only)["code"] == "reviewer_role_required"

    async def test_public_model_report_entries_are_visibility_scoped_and_redacted(self, user_factory):
        await _set_platform_api_enabled("1")
        await user_factory(telegram_id=240005)
        init_data = make_init_data(240005, token="test_token")

        job_response = await api_create_model_test(_request(
            method="POST",
            path="/platform/api/relay-tests",
            body={
                "user_id": 240005,
                "endpoint": "https://public-report.example.com/v1?debug=1",
                "protocol": "openai-compatible",
                "requested_model": "gpt-public",
                "api_key": "sk-public-report-secret",
                "idempotency_key": "api-job-240005-public-report",
            },
            authenticated=False,
            init_data=init_data,
        ))
        job = _json(job_response)["result"]
        public_report_response = await api_create_report(_request(
            method="POST",
            path=f"/platform/api/relay-tests/{job['id']}/reports",
            path_params={"job_id": job["id"]},
            body={
                "user_id": 240005,
                "declared_model": "gpt-public",
                "returned_model": "gpt-public",
                "suite_version": "p0-public",
                "scores": {"protocol": 1, "streaming": 1},
                "grade": "A",
                "evidence_json": {
                    "authorization": "Bearer sk-public-report-secret",
                    "result": "protocol compatibility ok",
                },
                "visibility": "public",
            },
            authenticated=False,
            init_data=init_data,
        ))
        public_report = _json(public_report_response)["result"]
        await record_model_test_run(
            job["id"],
            "public-api-worker",
            "completed",
            duration_ms=321,
            report_data={
                "estimated_cost": "0.000123",
                "evidence_json": {
                    "authorization": "Bearer sk-public-report-secret",
                    "suite": [
                        {"metadata": {"status_code": 200, "usage": {"total_tokens": 5}}},
                        {"metadata": {"status_code": 200, "usage": {"total_tokens": 7}}},
                    ],
                },
            },
        )

        public_list = await api_public_reports(_request(
            path="/platform/api/public/reports",
            authenticated=False,
        ))
        public_detail = await api_public_report(_request(
            path=f"/platform/api/public/reports/{public_report['id']}",
            path_params={"report_id": public_report["id"]},
            authenticated=False,
        ))
        owner_detail = await api_get_report(_request(
            path=f"/platform/api/reports/{public_report['id']}",
            path_params={"report_id": public_report["id"]},
            authenticated=False,
            init_data=init_data,
        ))
        unlisted_visibility = await api_report_visibility(_request(
            method="POST",
            path=f"/platform/api/reports/{public_report['id']}/visibility",
            path_params={"report_id": public_report["id"]},
            body={"user_id": 240005, "visibility": "unlisted"},
            authenticated=False,
            init_data=init_data,
        ))
        owner_unlisted_detail = await api_get_report(_request(
            path=f"/platform/api/reports/{public_report['id']}",
            path_params={"report_id": public_report["id"]},
            authenticated=False,
            init_data=init_data,
        ))
        share_token = _json(owner_unlisted_detail)["result"]["share_token"]
        unlisted_without_token = await api_public_report(_request(
            path=f"/platform/api/public/reports/{public_report['id']}",
            path_params={"report_id": public_report["id"]},
            authenticated=False,
        ))
        unlisted_with_token = await api_public_report(_request(
            path=f"/platform/api/public/reports/{public_report['id']}",
            path_params={"report_id": public_report["id"]},
            query=f"token={share_token}",
            authenticated=False,
        ))
        after_unlisted_list = await api_public_reports(_request(
            path="/platform/api/public/reports",
            authenticated=False,
        ))

        assert public_report_response.status_code == 201
        assert public_list.status_code == 200
        assert public_detail.status_code == 200
        listed_report = _json(public_list)["reports"][0]
        public_payload = _json(public_detail)["result"]
        assert listed_report["id"] == public_report["id"]
        assert listed_report["visibility"] == "public"
        assert public_payload["job"]["endpoint"] == "https://public-report.example.com/v1"
        assert public_payload["job"]["protocol"] == "openai-compatible"
        assert public_payload["runs"][0]["status"] == "completed"
        assert public_payload["runs"][0]["worker_id"] == "public-api-worker"
        assert public_payload["runs"][0]["duration_ms"] == 321
        assert public_payload["runs"][0]["total_tokens"] == 12
        assert public_payload["runs"][0]["estimated_cost"] == "0.000123"
        assert public_payload["evidence_json"]["authorization"] != "Bearer sk-public-report-secret"
        assert public_payload["limitation_note"]
        assert "user_id" not in public_payload
        assert "user_id" not in public_payload["job"]
        assert "key_fingerprint" not in str(public_payload)
        assert "key_masked" not in str(public_payload)
        assert "idempotency_key" not in str(public_payload)
        assert "sk-public-report-secret" not in str(public_payload)
        assert "authorization" not in str(public_payload["runs"])
        assert _json(owner_detail)["result"]["share_token"] == ""
        assert unlisted_visibility.status_code == 200
        assert len(share_token) == 40
        assert unlisted_without_token.status_code == 404
        assert unlisted_with_token.status_code == 200
        assert _json(unlisted_with_token)["result"]["visibility"] == "unlisted"
        assert _json(unlisted_with_token)["result"]["share_token"] == share_token
        assert _json(unlisted_with_token)["result"]["runs"][0]["worker_id"] == "public-api-worker"
        assert all(row["id"] != public_report["id"] for row in _json(after_unlisted_list)["reports"])

        private_visibility = await api_report_visibility(_request(
            method="POST",
            path=f"/platform/api/reports/{public_report['id']}/visibility",
            path_params={"report_id": public_report["id"]},
            body={"user_id": 240005, "visibility": "private"},
            authenticated=False,
            init_data=init_data,
        ))
        private_with_token = await api_public_report(_request(
            path=f"/platform/api/public/reports/{public_report['id']}",
            path_params={"report_id": public_report["id"]},
            query=f"token={share_token}",
            authenticated=False,
        ))
        assert private_visibility.status_code == 200
        assert private_with_token.status_code == 404

    async def test_user_appeal_records_and_admin_reviews_fraud_events(self, user_factory):
        await _set_platform_api_enabled("1")
        await _role_user(user_factory, 240050, "RISK_OPERATOR")
        init_data = make_init_data(240050, token="test_token")

        appeal = await api_user_appeal(_request(
            method="POST",
            path="/platform/api/users/240050/appeals",
            path_params={"user_id": 240050},
            body={
                "user_id": 240050,
                "reason": "please review",
                "source": "mini_app",
                "dedupe_key": "support-ticket:240050",
                "evidence": {"authorization": "Bearer secret", "token": "sk-test-secret"},
            },
            authenticated=False,
            init_data=init_data,
        ))
        duplicate_appeal = await api_user_appeal(_request(
            method="POST",
            path="/platform/api/users/240050/appeals",
            path_params={"user_id": 240050},
            body={
                "user_id": 240050,
                "reason": "please review again",
                "source": "mini_app",
                "dedupe_key": "support-ticket:240050",
                "evidence": {"token": "sk-second-secret"},
            },
            authenticated=False,
            init_data=init_data,
        ))
        listing = await api_admin_fraud_events(_request(
            path="/platform/api/admin/fraud-events",
            query="event_type=appeal",
            authenticated=True,
        ))
        review = await api_admin_fraud_event_review(_request(
            method="POST",
            path=f"/platform/api/admin/fraud-events/{_json(appeal)['result']['id']}/review",
            path_params={"event_id": _json(appeal)["result"]["id"]},
            body={"user_id": 240050, "status": "resolved", "notes": "handled"},
            authenticated=True,
        ))

        assert appeal.status_code == 201
        assert _json(appeal)["result"]["event_type"] == "appeal"
        assert _json(appeal)["result"]["status"] == "open"
        assert _json(appeal)["result"]["duplicate"] is False
        assert duplicate_appeal.status_code == 200
        assert _json(duplicate_appeal)["result"]["id"] == _json(appeal)["result"]["id"]
        assert _json(duplicate_appeal)["result"]["duplicate"] is True
        assert listing.status_code == 200
        assert len(_json(listing)["events"]) == 1
        event_payload = _json(listing)["events"][0]
        assert event_payload["status"] == "open"
        assert event_payload["evidence"]["dedupe_key"] == "support-ticket:240050"
        assert event_payload["evidence"]["evidence"]["authorization"] == "Bear...cret"
        assert "sk-test-secret" not in str(event_payload)
        assert "sk-second-secret" not in str(event_payload)
        assert review.status_code == 200

    async def test_admin_session_reviews_invite_rewards(self, user_factory):
        await _set_platform_api_enabled("1")
        await _role_user(user_factory, 240060, "RISK_OPERATOR")
        invite_link = await get_or_create_group_invite_link(
            240060,
            -1003919149099,
            create_link_cb=lambda: _async_value("https://t.me/+api-invite-review"),
        )
        await record_group_invite_join(240061, -1003919149099, invite_link)
        await perform_daily_checkin(240061, reward_amount=1, tickets_per_day=0)
        reward = await reward_group_inviter_after_checkin(240061, -1003919149099, points=2)

        queue = await api_admin_invite_rewards(_request(
            path="/platform/api/admin/invite-rewards",
            query="status=qualified",
            authenticated=True,
        ))
        block = await api_admin_invite_reward_review(_request(
            method="POST",
            path=f"/platform/api/admin/invite-rewards/{reward['id']}/review",
            path_params={"reward_id": reward["id"]},
            body={"user_id": 240060, "status": "risk_blocked", "risk_score": 15, "risk_reason": "linked users"},
            authenticated=True,
        ))
        blocked_queue = await api_admin_invite_rewards(_request(
            path="/platform/api/admin/invite-rewards",
            query="status=risk_blocked",
            authenticated=True,
        ))

        assert queue.status_code == 200
        assert _json(queue)["rewards"][0]["id"] == reward["id"]
        assert block.status_code == 200
        assert _json(blocked_queue)["rewards"][0]["risk_reason"] == "linked users"

    async def test_admin_session_rejected_settled_invite_reward_reverses_points(self, user_factory):
        await _set_platform_api_enabled("1")
        await _role_user(user_factory, 240061, "RISK_OPERATOR")
        invite_link = await get_or_create_group_invite_link(
            240061,
            -1003919149099,
            create_link_cb=lambda: _async_value("https://t.me/+api-invite-reversal"),
        )
        await record_group_invite_join(240062, -1003919149099, invite_link)
        await perform_daily_checkin(240062, reward_amount=1, tickets_per_day=0)
        reward = await reward_group_inviter_after_checkin(240062, -1003919149099, points=4)
        settlement = await settle_mature_group_invite_rewards(
            default_points=4,
            now=reward["settlement_at"],
            limit=10,
        )
        assert settlement["settled"] == 1

        inviter = await check_user(240061)
        assert inviter["points_balance"] == reward["points_awarded"]

        response = await api_admin_invite_reward_review(_request(
            method="POST",
            path=f"/platform/api/admin/invite-rewards/{reward['id']}/review",
            path_params={"reward_id": reward["id"]},
            body={"user_id": 240061, "status": "rejected", "risk_score": 50, "risk_reason": "fraud"},
            authenticated=True,
        ))
        inviter = await check_user(240061)
        async with Database().session() as s:
            ledger_rows = (await s.execute(select(LedgerEntries).where(
                LedgerEntries.user_id == 240061,
                LedgerEntries.entry_type.in_(["group_invite_reward", "group_invite_reward_reversal"]),
            ).order_by(LedgerEntries.id.asc()))).scalars().all()

        assert response.status_code == 200
        assert inviter["points_balance"] == 0
        assert len(ledger_rows) == 2
        assert float(ledger_rows[0].amount) == float(reward["points_awarded"])
        assert float(ledger_rows[1].amount) == float(-reward["points_awarded"])
        assert ledger_rows[1].reversed_id == ledger_rows[0].id

    async def test_admin_session_can_restore_settled_reward_after_reversal(self, user_factory):
        await _set_platform_api_enabled("1")
        await _role_user(user_factory, 240063, "RISK_OPERATOR")
        invite_link = await get_or_create_group_invite_link(
            240063,
            -1003919149099,
            create_link_cb=lambda: _async_value("https://t.me/+api-invite-restore"),
        )
        await record_group_invite_join(240064, -1003919149099, invite_link)
        await perform_daily_checkin(240064, reward_amount=1, tickets_per_day=0)
        reward = await reward_group_inviter_after_checkin(240064, -1003919149099, points=2)
        await settle_mature_group_invite_rewards(
            default_points=2,
            now=reward["settlement_at"],
            limit=10,
        )
        await api_admin_invite_reward_review(_request(
            method="POST",
            path=f"/platform/api/admin/invite-rewards/{reward['id']}/review",
            path_params={"reward_id": reward["id"]},
            body={"user_id": 240063, "status": "rejected", "risk_score": 45, "risk_reason": "temporary"},
            authenticated=True,
        ))
        restore_response = await api_admin_invite_reward_review(_request(
            method="POST",
            path=f"/platform/api/admin/invite-rewards/{reward['id']}/review",
            path_params={"reward_id": reward["id"]},
            body={"user_id": 240063, "status": "qualified", "risk_score": 0, "risk_reason": ""},
            authenticated=True,
        ))

        inviter = await check_user(240063)
        async with Database().session() as s:
            ledger_rows = (await s.execute(select(LedgerEntries).where(
                LedgerEntries.user_id == 240063,
                LedgerEntries.entry_type.like("group_invite_reward%"),
            ).order_by(LedgerEntries.id.asc()))).scalars().all()

        assert restore_response.status_code == 200
        assert inviter["points_balance"] == reward["points_awarded"]
        assert len(ledger_rows) == 3
        assert ledger_rows[-1].entry_type == "group_invite_reward_reinstatement"
        assert float(ledger_rows[-1].amount) == float(reward["points_awarded"])

    async def test_mini_app_api_can_run_model_test_once_with_ephemeral_key(self, user_factory, monkeypatch):
        await _set_platform_api_enabled("1")
        await user_factory(telegram_id=240004)
        init_data = make_init_data(240004, token="test_token")
        seen = {}
        monkeypatch.setenv("MODEL_LAB_WORKER_RUNNER", "/usr/local/libexec/tgsellbot/run-isolated-worker.sh")

        async def fake_run_once(job_id, api_key, *, worker_id, worker_runner=None):
            seen["job_id"] = job_id
            seen["api_key"] = api_key
            seen["worker_id"] = worker_id
            seen["worker_runner"] = worker_runner
            from bot.database.methods.platform import complete_model_test_job

            return await complete_model_test_job(
                job_id,
                worker_id,
                {
                    "declared_model": "gpt-run-now",
                    "returned_model": "gpt-run-now",
                    "suite_version": "model-lab-test",
                    "scores": {"protocol_compatibility": 1, "observed_behavior": 1},
                    "grade": "A",
                    "evidence_json": {"credential": {"api_key": api_key}},
                    "visibility": "private",
                },
            )

        monkeypatch.setattr("bot.web.platform.run_model_test_job_once", fake_run_once)

        response = await api_create_model_test(_request(
            method="POST",
            path="/platform/api/relay-tests",
            body={
                "user_id": 240004,
                "endpoint": "https://run-now-relay.example.com/v1",
                "protocol": "openai-compatible",
                "requested_model": "gpt-run-now",
                "api_key": "sk-run-now-secret",
                "idempotency_key": "api-job-240004",
                "run_now": True,
            },
            authenticated=False,
            init_data=init_data,
        ))
        payload = _json(response)

        assert response.status_code == 201
        assert payload["result"]["status"] == "completed"
        assert seen["api_key"] == "sk-run-now-secret"
        assert seen["worker_id"] == f"miniapp:{seen['job_id']}"
        assert seen["worker_runner"] == "/usr/local/libexec/tgsellbot/run-isolated-worker.sh"
        assert "sk-run-now-secret" not in str(payload)

    async def test_mini_app_run_now_requires_isolated_worker_runner(self, user_factory, monkeypatch):
        await _set_platform_api_enabled("1")
        await user_factory(telegram_id=240064)
        init_data = make_init_data(240064, token="test_token")
        monkeypatch.delenv("MODEL_LAB_WORKER_RUNNER", raising=False)

        response = await api_create_model_test(_request(
            method="POST",
            path="/platform/api/relay-tests",
            body={
                "user_id": 240064,
                "endpoint": "https://runner-required.example.com/v1",
                "protocol": "openai-compatible",
                "requested_model": "gpt-runner-required",
                "api_key": "sk-runner-required-secret",
                "idempotency_key": "api-job-240064-runner-required",
                "run_now": True,
            },
            authenticated=False,
            init_data=init_data,
        ))
        listed_jobs = await api_list_model_tests(_request(
            path="/platform/api/relay-tests",
            query="user_id=240064",
            authenticated=False,
            init_data=init_data,
        ))

        assert response.status_code == 503
        assert _json(response)["code"] == "model_worker_runner_required"
        assert _json(listed_jobs)["jobs"] == []
        assert "sk-runner-required-secret" not in str(_json(response))

    async def test_admin_session_can_review_channels_and_relays(self, user_factory):
        await _set_platform_api_enabled("1")
        await _role_user(user_factory, 240010)
        channel = await submit_channel(
            {
                "channel": "@admin_review_channel",
                "category": "ai",
                "language": "zh",
                "reason": "admin review",
            },
            submitter_id=240010,
        )
        relay = await submit_relay_provider(
            {
                "name": "Admin Relay",
                "base_url": "https://admin-relay.example.com/v1",
                "protocol": "openai-compatible",
            },
            submitter_id=240010,
        )

        channel_list = await api_admin_channel_submissions(_request(
            path="/platform/api/admin/channels/submissions",
            authenticated=True,
        ))
        relay_list = await api_admin_relays(_request(
            path="/platform/api/admin/relays",
            authenticated=True,
        ))
        channel_review = await api_admin_channel_review(_request(
            method="POST",
            path=f"/platform/api/admin/channels/submissions/{channel['submission']['id']}/review",
            path_params={"submission_id": channel["submission"]["id"]},
            body={"user_id": 240010, "status": "approved", "notes": "looks good"},
            authenticated=True,
        ))
        relay_review = await api_admin_relay_review(_request(
            method="POST",
            path=f"/platform/api/admin/relays/{relay['id']}/review",
            path_params={"provider_id": relay["id"]},
            body={"user_id": 240010, "status": "approved", "risk_status": "normal", "notes": "looks good"},
            authenticated=True,
        ))

        assert channel_list.status_code == 200
        assert channel_list.headers["content-type"].startswith("application/json")
        assert relay_list.status_code == 200
        assert channel_review.status_code == 200
        assert relay_review.status_code == 200

    async def test_reviewer_init_data_can_use_channel_review_api_without_admin_session(self, user_factory):
        await _set_platform_api_enabled("1")
        await _role_user(user_factory, 240080, "REVIEWER")
        await _role_user(user_factory, 240081, "RISK_OPERATOR")
        await user_factory(telegram_id=240082)
        reviewer_init_data = make_init_data(240080, token="test_token")
        risk_init_data = make_init_data(240081, token="test_token")
        ordinary_init_data = make_init_data(240082, token="test_token")
        channel = await submit_channel(
            {
                "channel": "@reviewer_gate_channel",
                "category": "ai",
                "language": "zh",
                "reason": "reviewer gate",
            },
            submitter_id=240080,
        )

        ordinary_list = await api_admin_channel_submissions(_request(
            path="/platform/api/admin/channels/submissions",
            authenticated=False,
            init_data=ordinary_init_data,
        ))
        reviewer_list = await api_admin_channel_submissions(_request(
            path="/platform/api/admin/channels/submissions",
            authenticated=False,
            init_data=reviewer_init_data,
        ))
        review = await api_admin_channel_review(_request(
            method="POST",
            path=f"/platform/api/admin/channels/submissions/{channel['submission']['id']}/review",
            path_params={"submission_id": channel["submission"]["id"]},
            body={"status": "approved", "notes": "reviewed through init data"},
            authenticated=False,
            init_data=reviewer_init_data,
        ))
        await api_channel_interaction(_request(
            method="POST",
            path=f"/platform/api/channels/{channel['channel']['id']}/interactions",
            path_params={"channel_id": channel["channel"]["id"]},
            body={"action": "report", "source": "mini_app"},
            authenticated=False,
            init_data=ordinary_init_data,
        ))
        report_list = await api_admin_channel_reports(_request(
            path="/platform/api/admin/channel-reports",
            query="status=reported",
            authenticated=False,
            init_data=reviewer_init_data,
        ))
        denied_risk_review = await api_admin_channel_report_review(_request(
            method="POST",
            path=f"/platform/api/admin/channels/{channel['channel']['id']}/report-review",
            path_params={"channel_id": channel["channel"]["id"]},
            body={"risk_status": "risk_blocked", "escalation": "risk", "notes": "risk only"},
            authenticated=False,
            init_data=reviewer_init_data,
        ))
        risk_review = await api_admin_channel_report_review(_request(
            method="POST",
            path=f"/platform/api/admin/channels/{channel['channel']['id']}/report-review",
            path_params={"channel_id": channel["channel"]["id"]},
            body={"risk_status": "risk_blocked", "escalation": "risk", "notes": "risk reviewed"},
            authenticated=False,
            init_data=risk_init_data,
        ))

        assert ordinary_list.status_code == 403
        assert _json(ordinary_list)["code"] == "reviewer_role_required"
        assert reviewer_list.status_code == 200
        assert review.status_code == 200
        assert report_list.status_code == 200
        assert _json(report_list)["reports"][0]["report"]["report_count"] == 1
        assert denied_risk_review.status_code == 403
        assert _json(denied_risk_review)["code"] == "risk_role_required"
        assert risk_review.status_code == 200

    async def test_reviewer_init_data_can_use_relay_review_api_without_admin_session(self, user_factory):
        await _set_platform_api_enabled("1")
        await _role_user(user_factory, 240083, "REVIEWER")
        await _role_user(user_factory, 240084, "RISK_OPERATOR")
        await user_factory(telegram_id=240085)
        reviewer_init_data = make_init_data(240083, token="test_token")
        risk_init_data = make_init_data(240084, token="test_token")
        ordinary_init_data = make_init_data(240085, token="test_token")
        relay = await submit_relay_provider(
            {
                "name": "Reviewer Gate Relay",
                "base_url": "https://reviewer-gate-relay.example.com/v1",
                "protocol": "openai-compatible",
            },
            submitter_id=240083,
        )

        ordinary_list = await api_admin_relays(_request(
            path="/platform/api/admin/relays",
            authenticated=False,
            init_data=ordinary_init_data,
        ))
        reviewer_list = await api_admin_relays(_request(
            path="/platform/api/admin/relays",
            authenticated=False,
            init_data=reviewer_init_data,
        ))
        review = await api_admin_relay_review(_request(
            method="POST",
            path=f"/platform/api/admin/relays/{relay['id']}/review",
            path_params={"provider_id": relay["id"]},
            body={"status": "approved", "risk_status": "normal", "notes": "reviewed through init data"},
            authenticated=False,
            init_data=reviewer_init_data,
        ))
        feedback = await api_relay_feedback(_request(
            method="POST",
            path=f"/platform/api/relays/{relay['id']}/feedback",
            path_params={"provider_id": relay["id"]},
            body={"feedback_type": "complaint", "text": "reviewer gate complaint"},
            authenticated=False,
            init_data=ordinary_init_data,
        ))
        complaint = _json(feedback)["result"]
        feedback_list = await api_admin_relay_feedback(_request(
            path="/platform/api/admin/relay-feedback",
            query="feedback_type=complaint",
            authenticated=False,
            init_data=reviewer_init_data,
        ))
        denied_risk_review = await api_admin_relay_feedback_review(_request(
            method="POST",
            path=f"/platform/api/admin/relay-feedback/{complaint['id']}/review",
            path_params={"feedback_id": complaint["id"]},
            body={"status": "risk_blocked", "escalation": "urgent", "notes": "risk only"},
            authenticated=False,
            init_data=reviewer_init_data,
        ))
        risk_review = await api_admin_relay_feedback_review(_request(
            method="POST",
            path=f"/platform/api/admin/relay-feedback/{complaint['id']}/review",
            path_params={"feedback_id": complaint["id"]},
            body={
                "status": "risk_blocked",
                "escalation": "urgent",
                "notes": "risk reviewed",
                "outcome": "escalated",
            },
            authenticated=False,
            init_data=risk_init_data,
        ))

        assert ordinary_list.status_code == 403
        assert _json(ordinary_list)["code"] == "reviewer_role_required"
        assert reviewer_list.status_code == 200
        assert review.status_code == 200
        assert feedback.status_code == 201
        assert feedback_list.status_code == 200
        assert _json(feedback_list)["feedback"][0]["feedback"]["id"] == complaint["id"]
        assert denied_risk_review.status_code == 403
        assert _json(denied_risk_review)["code"] == "risk_role_required"
        assert risk_review.status_code == 200

    async def test_mini_app_api_discovers_and_reads_relay_directory(self, user_factory):
        await _set_platform_api_enabled("1")
        await _role_user(user_factory, 240040)
        init_data = make_init_data(240040, token="test_token")
        relay = await submit_relay_provider(
            {
                "name": "API Directory Relay",
                "base_url": "https://api-directory-relay.example.com/v1?debug=1",
                "protocol": "openai-compatible",
                "model_scope": "gpt models",
                "region": "SG",
                "pricing": "metered",
            },
            submitter_id=240040,
        )
        await api_admin_relay_review(_request(
            method="POST",
            path=f"/platform/api/admin/relays/{relay['id']}/review",
            path_params={"provider_id": relay["id"]},
            body={"user_id": 240040, "status": "approved", "risk_status": "normal"},
            authenticated=True,
        ))

        directory = await api_discover_relays(_request(
            path="/platform/api/relays/discover",
            query="q=directory&protocol=openai-compatible&region=SG",
            authenticated=False,
            init_data=init_data,
        ))
        claim = await api_relay_claim(_request(
            method="POST",
            path=f"/platform/api/relays/{relay['id']}/claim",
            path_params={"provider_id": relay["id"]},
            body={"user_id": 240040, "method": "domain"},
            authenticated=False,
            init_data=init_data,
        ))
        claim_list = await api_admin_relay_claims(_request(
            path="/platform/api/admin/relay-claims",
            query="status=pending",
            authenticated=True,
        ))
        detail = await api_relay_detail(_request(
            path=f"/platform/api/relays/{relay['id']}",
            path_params={"provider_id": relay["id"]},
            authenticated=False,
            init_data=init_data,
        ))

        assert directory.status_code == 200
        directory_payload = _json(directory)
        assert directory_payload["total"] == 1
        assert directory_payload["providers"][0]["base_url"] == "https://api-directory-relay.example.com/v1"
        assert claim.status_code == 201
        claim_payload = _json(claim)["result"]
        assert claim_payload["method"] == "domain"
        assert claim_payload["verification"]["expected_text"] == f"tgsellbot-relay-claim={claim_payload['challenge']}"
        assert claim_list.status_code == 200
        queued_claim = _json(claim_list)["claims"][0]["claim"]
        assert queued_claim["id"] == claim_payload["id"]
        assert queued_claim["verification"]["challenge"] == claim_payload["challenge"]
        assert queued_claim["verification"]["domain_control_required"] is True
        assert detail.status_code == 200
        detail_payload = _json(detail)["result"]
        assert detail_payload["provider"]["pricing"] == "metered"
        assert "challenge" not in detail_payload["claims"][0]
        assert detail_payload["claims"][0]["verification"]["challenge_required"] is True
        assert detail_payload["audit_trail"]

    async def test_relay_owner_profile_api_requires_verified_owner_and_keeps_endpoint_stable(self, user_factory):
        await _set_platform_api_enabled("1")
        await _role_user(user_factory, 240045)
        await user_factory(telegram_id=240046)
        submitter_init_data = make_init_data(240045, token="test_token")
        owner_init_data = make_init_data(240046, token="test_token")
        relay = await submit_relay_provider(
            {
                "name": "API Owner Relay",
                "base_url": "https://api-owner-relay.example.com/v1?debug=1",
                "protocol": "openai-compatible",
                "model_scope": "old models",
                "region": "SG",
            },
            submitter_id=240045,
        )
        await api_admin_relay_review(_request(
            method="POST",
            path=f"/platform/api/admin/relays/{relay['id']}/review",
            path_params={"provider_id": relay["id"]},
            body={"user_id": 240045, "status": "approved", "risk_status": "normal"},
            authenticated=True,
        ))
        claim = await api_relay_claim(_request(
            method="POST",
            path=f"/platform/api/relays/{relay['id']}/claim",
            path_params={"provider_id": relay["id"]},
            body={"user_id": 240046, "method": "manual"},
            authenticated=False,
            init_data=owner_init_data,
        ))
        claim_id = _json(claim)["result"]["id"]
        await api_relay_claim_review(_request(
            method="POST",
            path=f"/platform/api/relay-claims/{claim_id}/review",
            path_params={"claim_id": claim_id},
            body={"user_id": 240045, "approved": True},
            authenticated=True,
        ))

        denied = await api_relay_owner_profile(_request(
            method="POST",
            path=f"/platform/api/relays/{relay['id']}/owner-profile",
            path_params={"provider_id": relay["id"]},
            body={"user_id": 240045, "name": "Not Owner"},
            authenticated=False,
            init_data=submitter_init_data,
        ))
        allowed = await api_relay_owner_profile(_request(
            method="POST",
            path=f"/platform/api/relays/{relay['id']}/owner-profile",
            path_params={"provider_id": relay["id"]},
            body={
                "user_id": 240046,
                "name": "Updated API Owner Relay",
                "website_url": "https://relay-owner.example.com/home?utm_source=owner",
                "model_scope": "updated models",
                "region": "US",
                "pricing": "published tiers",
                "base_url": "https://changed.example.com/v1",
            },
            authenticated=False,
            init_data=owner_init_data,
        ))
        detail = await api_relay_detail(_request(
            path=f"/platform/api/relays/{relay['id']}",
            path_params={"provider_id": relay["id"]},
            authenticated=False,
            init_data=owner_init_data,
        ))

        assert denied.status_code == 403
        assert _json(denied)["code"] == "forbidden"
        assert allowed.status_code == 200
        result = _json(allowed)["result"]
        assert result["name"] == "Updated API Owner Relay"
        assert result["base_url"] == "https://api-owner-relay.example.com/v1"
        assert result["website_url"] == "https://relay-owner.example.com/home"
        assert "utm_source=owner" not in str(result)
        provider = _json(detail)["result"]["provider"]
        viewer = _json(detail)["result"]["viewer"]
        assert provider["base_url"] == "https://api-owner-relay.example.com/v1"
        assert provider["model_scope"] == "updated models"
        assert viewer["can_edit_profile"] is True

    async def test_admin_api_requires_domain_claim_proof_before_approval(self, user_factory, monkeypatch):
        await _set_platform_api_enabled("1")
        await _role_user(user_factory, 240043)
        init_data = make_init_data(240043, token="test_token")

        relay = await submit_relay_provider(
            {
                "name": "API Domain Claim Relay",
                "base_url": "https://api-domain-claim-relay.example.com/v1",
                "protocol": "openai-compatible",
            },
            submitter_id=240043,
        )
        await api_admin_relay_review(_request(
            method="POST",
            path=f"/platform/api/admin/relays/{relay['id']}/review",
            path_params={"provider_id": relay["id"]},
            body={"user_id": 240043, "status": "approved", "risk_status": "normal"},
            authenticated=True,
        ))
        claim = await api_relay_claim(_request(
            method="POST",
            path=f"/platform/api/relays/{relay['id']}/claim",
            path_params={"provider_id": relay["id"]},
            body={"user_id": 240043, "method": "domain"},
            authenticated=False,
            init_data=init_data,
        ))
        claim_payload = _json(claim)["result"]
        expected_text = claim_payload["verification"]["expected_text"]
        proof_state = {"body": "missing proof"}

        async def fake_resolver(hostname):
            return ["93.184.216.34"]

        async def fake_fetcher(url):
            return proof_state["body"]

        async def safe_verify(claim_id, reviewer_id, approved, notes="", **kwargs):
            return await verify_relay_claim(
                claim_id,
                reviewer_id,
                approved,
                notes,
                fetcher=fake_fetcher,
                resolver=fake_resolver,
            )

        monkeypatch.setattr("bot.web.platform.verify_relay_claim", safe_verify)

        rejected = await api_relay_claim_review(_request(
            method="POST",
            path=f"/platform/api/relay-claims/{claim_payload['id']}/review",
            path_params={"claim_id": claim_payload["id"]},
            body={"user_id": 240043, "approved": True, "notes": "no proof yet"},
            authenticated=True,
        ))
        pending = await api_admin_relay_claims(_request(
            path="/platform/api/admin/relay-claims",
            query="status=pending",
            authenticated=True,
        ))

        proof_state["body"] = f"{expected_text}\n"
        approved = await api_relay_claim_review(_request(
            method="POST",
            path=f"/platform/api/relay-claims/{claim_payload['id']}/review",
            path_params={"claim_id": claim_payload["id"]},
            body={"user_id": 240043, "approved": True, "notes": "proof found"},
            authenticated=True,
        ))

        assert claim.status_code == 201
        assert rejected.status_code == 400
        assert _json(rejected)["code"] == "bad_request"
        assert "domain proof not found" in _json(rejected)["error"]
        assert _json(pending)["claims"][0]["claim"]["id"] == claim_payload["id"]
        assert approved.status_code == 200

    async def test_admin_api_reads_relay_provider_detail_history(self, user_factory):
        await _set_platform_api_enabled("1")
        await _role_user(user_factory, 240044)
        relay = await submit_relay_provider(
            {
                "name": "Admin Detail Relay",
                "base_url": "https://admin-detail-relay.example.com/v1?debug=1",
                "protocol": "openai-compatible",
                "model_scope": "chat models",
                "region": "HK",
                "pricing": "metered",
            },
            submitter_id=240044,
        )
        await api_admin_relay_review(_request(
            method="POST",
            path=f"/platform/api/admin/relays/{relay['id']}/review",
            path_params={"provider_id": relay["id"]},
            body={"user_id": 240044, "status": "approved", "risk_status": "normal"},
            authenticated=True,
        ))
        claim = await api_relay_claim(_request(
            method="POST",
            path=f"/platform/api/relays/{relay['id']}/claim",
            path_params={"provider_id": relay["id"]},
            body={"user_id": 240044, "method": "manual"},
            authenticated=False,
            init_data=make_init_data(240044, token="test_token"),
        ))
        feedback = await api_relay_feedback(_request(
            method="POST",
            path=f"/platform/api/relays/{relay['id']}/feedback",
            path_params={"provider_id": relay["id"]},
            body={"user_id": 240044, "feedback_type": "rating", "text": "usable", "rating": 5},
            authenticated=False,
            init_data=make_init_data(240044, token="test_token"),
        ))
        await api_admin_relay_feedback_review(_request(
            method="POST",
            path=f"/platform/api/admin/relay-feedback/{_json(feedback)['result']['id']}/review",
            path_params={"feedback_id": _json(feedback)["result"]["id"]},
            body={"user_id": 240044, "status": "approved", "notes": "visible in detail"},
            authenticated=True,
        ))

        reviewer_detail = await api_admin_relay_detail(_request(
            path=f"/platform/api/admin/relays/{relay['id']}",
            path_params={"provider_id": relay["id"]},
            authenticated=False,
            init_data=make_init_data(240044, token="test_token"),
        ))
        detail = await api_admin_relay_detail(_request(
            path=f"/platform/api/admin/relays/{relay['id']}",
            path_params={"provider_id": relay["id"]},
            authenticated=True,
        ))
        payload = _json(detail)["result"]

        assert claim.status_code == 201
        assert reviewer_detail.status_code == 200
        assert detail.status_code == 200
        assert payload["provider"]["name"] == "Admin Detail Relay"
        assert payload["provider"]["base_url"] == "https://admin-detail-relay.example.com/v1"
        assert payload["feedback"]["recent"][0]["text"] == "usable"
        assert payload["feedback"]["average_rating"] == 5.0
        assert payload["claims"][0]["method"] == "manual"
        assert "challenge" not in payload["claims"][0]
        assert {event["action"] for event in payload["audit_trail"]} >= {"relay_submit", "relay_review"}

    async def test_admin_session_can_filter_and_triage_relay_complaints(self, user_factory):
        await _set_platform_api_enabled("1")
        await _role_user(user_factory, 240041)
        await user_factory(telegram_id=240042)
        owner_init_data = make_init_data(240041, token="test_token")
        feedback_init_data = make_init_data(240042, token="test_token")

        relay_response = await api_submit_relay(_request(
            method="POST",
            path="/platform/api/relays",
            body={
                "user_id": 240041,
                "name": "Complaint Queue Relay",
                "base_url": "https://complaint-queue-relay.example.com/v1?debug=1",
                "protocol": "openai-compatible",
                "model_scope": "chat models",
                "region": "SG",
                "pricing": "usage based",
            },
            authenticated=False,
            init_data=owner_init_data,
        ))
        relay = _json(relay_response)["result"]
        await api_admin_relay_review(_request(
            method="POST",
            path=f"/platform/api/admin/relays/{relay['id']}/review",
            path_params={"provider_id": relay["id"]},
            body={"user_id": 240041, "status": "approved", "risk_status": "normal"},
            authenticated=True,
        ))

        rating_response = await api_relay_feedback(_request(
            method="POST",
            path=f"/platform/api/relays/{relay['id']}/feedback",
            path_params={"provider_id": relay["id"]},
            body={"user_id": 240042, "feedback_type": "rating", "text": "stable enough", "rating": 4},
            authenticated=False,
            init_data=feedback_init_data,
        ))
        complaint_response = await api_relay_feedback(_request(
            method="POST",
            path=f"/platform/api/relays/{relay['id']}/feedback",
            path_params={"provider_id": relay["id"]},
            body={"user_id": 240042, "feedback_type": "complaint", "text": "unexpected timeout during streaming"},
            authenticated=False,
            init_data=feedback_init_data,
        ))
        complaint = _json(complaint_response)["result"]

        complaint_list = await api_admin_relay_feedback(_request(
            path="/platform/api/admin/relay-feedback",
            query="feedback_type=complaint",
            authenticated=True,
        ))
        needs_followup = await api_admin_relay_feedback(_request(
            path="/platform/api/admin/relay-feedback",
            query="feedback_type=complaint&followup_state=needs_followup",
            authenticated=True,
        ))
        review = await api_admin_relay_feedback_review(_request(
            method="POST",
            path=f"/platform/api/admin/relay-feedback/{complaint['id']}/review",
            path_params={"feedback_id": complaint["id"]},
            body={
                "user_id": 240041,
                "status": "under_review",
                "notes": "triaged by complaint queue",
                "assigned_to": 240041,
                "escalation": "operator",
                "outcome": "provider_fixed",
                "followup_notes": "provider published an incident follow-up",
            },
            authenticated=True,
        ))
        under_review = await api_admin_relay_feedback(_request(
            path="/platform/api/admin/relay-feedback",
            query="feedback_type=complaint&status=under_review",
            authenticated=True,
        ))
        outcome_filtered = await api_admin_relay_feedback(_request(
            path="/platform/api/admin/relay-feedback",
            query="feedback_type=complaint&outcome=provider_fixed",
            authenticated=True,
        ))
        resolved_followup = await api_admin_relay_feedback(_request(
            path="/platform/api/admin/relay-feedback",
            query="feedback_type=complaint&followup_state=resolved",
            authenticated=True,
        ))
        unresolved_followup = await api_admin_relay_feedback(_request(
            path="/platform/api/admin/relay-feedback",
            query="feedback_type=complaint&followup_state=unresolved",
            authenticated=True,
        ))
        assigned_filtered = await api_admin_relay_feedback(_request(
            path="/platform/api/admin/relay-feedback",
            query="feedback_type=complaint&assigned_to=240041&reviewed_by=240041&escalation=operator",
            authenticated=True,
        ))
        unassigned_filtered = await api_admin_relay_feedback(_request(
            path="/platform/api/admin/relay-feedback",
            query="feedback_type=complaint&assigned_to=unassigned",
            authenticated=True,
        ))

        assert relay_response.status_code == 201
        assert rating_response.status_code == 201
        assert complaint_response.status_code == 201
        assert complaint_list.status_code == 200
        complaint_rows = _json(complaint_list)["feedback"]
        assert len(complaint_rows) == 1
        assert complaint_rows[0]["feedback"]["id"] == complaint["id"]
        assert complaint_rows[0]["feedback"]["feedback_type"] == "complaint"
        assert complaint_rows[0]["feedback"]["text"] == "unexpected timeout during streaming"
        assert complaint_rows[0]["feedback"]["followup_state"] == "needs_followup"
        assert complaint_rows[0]["provider"]["base_url"] == "https://complaint-queue-relay.example.com/v1"
        assert needs_followup.status_code == 200
        assert _json(needs_followup)["feedback"][0]["feedback"]["id"] == complaint["id"]
        assert review.status_code == 200
        reviewed_rows = _json(under_review)["feedback"]
        assert len(reviewed_rows) == 1
        assert reviewed_rows[0]["feedback"]["id"] == complaint["id"]
        assert reviewed_rows[0]["feedback"]["status"] == "under_review"
        assert reviewed_rows[0]["feedback"]["review_notes"] == "triaged by complaint queue"
        assert reviewed_rows[0]["feedback"]["reviewed_by"] == 240041
        assert reviewed_rows[0]["feedback"]["reviewed_at"]
        assert reviewed_rows[0]["feedback"]["assigned_to"] == 240041
        assert reviewed_rows[0]["feedback"]["escalation"] == "operator"
        assert reviewed_rows[0]["feedback"]["outcome"] == "provider_fixed"
        assert reviewed_rows[0]["feedback"]["followup_state"] == "resolved"
        assert reviewed_rows[0]["feedback"]["followup_notes"] == "provider published an incident follow-up"
        assert reviewed_rows[0]["feedback"]["resolved_by"] == 240041
        assert reviewed_rows[0]["feedback"]["resolved_at"]
        outcome_rows = _json(outcome_filtered)["feedback"]
        assert len(outcome_rows) == 1
        assert outcome_rows[0]["feedback"]["id"] == complaint["id"]
        resolved_rows = _json(resolved_followup)["feedback"]
        assert len(resolved_rows) == 1
        assert resolved_rows[0]["feedback"]["id"] == complaint["id"]
        assert _json(unresolved_followup)["feedback"] == []
        assigned_rows = _json(assigned_filtered)["feedback"]
        assert len(assigned_rows) == 1
        assert assigned_rows[0]["feedback"]["id"] == complaint["id"]
        assert _json(unassigned_filtered)["feedback"] == []

    async def test_admin_session_can_triage_channel_reports(self, user_factory):
        await _set_platform_api_enabled("1")
        await _role_user(user_factory, 240030)
        await user_factory(telegram_id=240031)
        init_data = make_init_data(240031, token="test_token")
        channel = await submit_channel(
            {
                "channel": "@api_report_channel",
                "category": "ai",
                "language": "zh",
                "reason": "report queue",
            },
            submitter_id=240030,
        )
        await api_admin_channel_review(_request(
            method="POST",
            path=f"/platform/api/admin/channels/submissions/{channel['submission']['id']}/review",
            path_params={"submission_id": channel["submission"]["id"]},
            body={"user_id": 240030, "status": "approved"},
            authenticated=True,
        ))

        report = await api_channel_interaction(_request(
            method="POST",
            path=f"/platform/api/channels/{channel['channel']['id']}/interactions",
            path_params={"channel_id": channel["channel"]["id"]},
            body={"user_id": 240031, "action": "report", "source": "mini_app"},
            authenticated=False,
            init_data=init_data,
        ))
        report_list = await api_admin_channel_reports(_request(
            path="/platform/api/admin/channel-reports",
            query="status=reported",
            authenticated=True,
        ))
        review = await api_admin_channel_report_review(_request(
            method="POST",
            path=f"/platform/api/admin/channels/{channel['channel']['id']}/report-review",
            path_params={"channel_id": channel["channel"]["id"]},
            body={
                "user_id": 240030,
                "risk_status": "dismissed",
                "notes": "not actionable",
                "assigned_to": 240030,
                "escalation": "watch",
            },
            authenticated=True,
        ))
        dismissed_list = await api_admin_channel_reports(_request(
            path="/platform/api/admin/channel-reports",
            query="status=dismissed",
            authenticated=True,
        ))
        assigned_list = await api_admin_channel_reports(_request(
            path="/platform/api/admin/channel-reports",
            query="status=dismissed&assigned_to=240030&reviewed_by=240030&escalation=watch",
            authenticated=True,
        ))
        unassigned_list = await api_admin_channel_reports(_request(
            path="/platform/api/admin/channel-reports",
            query="status=dismissed&assigned_to=unassigned",
            authenticated=True,
        ))
        discovered = await api_discover_channels(_request(
            path="/platform/api/channels/discover",
            query="category=ai&language=zh",
            authenticated=False,
            init_data=init_data,
        ))

        assert report.status_code == 201
        assert report_list.status_code == 200
        assert _json(report_list)["reports"][0]["report"]["report_count"] == 1
        assert review.status_code == 200
        dismissed = _json(dismissed_list)["reports"][0]
        assert dismissed["channel"]["risk_status"] == "dismissed"
        assert dismissed["report"]["notes"] == "not actionable"
        assert dismissed["report"]["reviewed_by"] == 240030
        assert dismissed["report"]["reviewed_at"]
        assert dismissed["report"]["assigned_to"] == 240030
        assert dismissed["report"]["escalation"] == "watch"
        assert _json(assigned_list)["reports"][0]["channel"]["id"] == channel["channel"]["id"]
        assert _json(unassigned_list)["reports"] == []
        public_channel = _json(discovered)["channels"][0]
        assert "risk_notes" not in public_channel
        assert "risk_assigned_to" not in public_channel

    async def test_admin_api_reads_channel_report_detail_history(self, user_factory):
        await _set_platform_api_enabled("1")
        await _role_user(user_factory, 240032, "RISK_OPERATOR")
        await user_factory(telegram_id=240033)
        init_data = make_init_data(240033, token="test_token")
        channel = await submit_channel(
            {
                "channel": "@api_channel_detail_history",
                "category": "ai",
                "language": "zh",
                "title": "API Channel Detail",
                "reason": "detail history",
            },
            submitter_id=240032,
        )
        await api_admin_channel_review(_request(
            method="POST",
            path=f"/platform/api/admin/channels/submissions/{channel['submission']['id']}/review",
            path_params={"submission_id": channel["submission"]["id"]},
            body={"user_id": 240032, "status": "approved"},
            authenticated=True,
        ))
        claim = await api_channel_claim(_request(
            method="POST",
            path=f"/platform/api/channels/{channel['channel']['id']}/claim",
            path_params={"channel_id": channel["channel"]["id"]},
            body={"user_id": 240033, "method": "manual"},
            authenticated=False,
            init_data=init_data,
        ))
        claim_id = _json(claim)["result"]["id"]
        await api_channel_claim_review(_request(
            method="POST",
            path=f"/platform/api/channel-claims/{claim_id}/review",
            path_params={"claim_id": claim_id},
            body={"user_id": 240032, "approved": True, "notes": "manual verification"},
            authenticated=True,
        ))
        await api_channel_interaction(_request(
            method="POST",
            path=f"/platform/api/channels/{channel['channel']['id']}/interactions",
            path_params={"channel_id": channel["channel"]["id"]},
            body={"user_id": 240033, "action": "report", "source": "mini_app"},
            authenticated=False,
            init_data=init_data,
        ))
        await api_admin_channel_report_review(_request(
            method="POST",
            path=f"/platform/api/admin/channels/{channel['channel']['id']}/report-review",
            path_params={"channel_id": channel["channel"]["id"]},
            body={
                "user_id": 240032,
                "status": "under_review",
                "notes": "internal detail notes",
                "assigned_to": 240032,
                "escalation": "risk",
            },
            authenticated=True,
        ))

        denied = await api_admin_channel_detail(_request(
            path=f"/platform/api/admin/channels/{channel['channel']['id']}",
            path_params={"channel_id": channel["channel"]["id"]},
            authenticated=False,
            init_data=init_data,
        ))
        detail = await api_admin_channel_detail(_request(
            path=f"/platform/api/admin/channels/{channel['channel']['id']}",
            path_params={"channel_id": channel["channel"]["id"]},
            authenticated=True,
        ))

        assert denied.status_code == 403
        assert _json(denied)["code"] == "reviewer_role_required"
        assert detail.status_code == 200
        payload = _json(detail)["result"]
        assert payload["channel"]["risk_notes"] == "internal detail notes"
        assert payload["channel"]["owner_user_id"] == 240033
        assert payload["report"]["report_count"] == 1
        assert payload["report"]["assigned_to"] == 240032
        assert payload["report"]["escalation"] == "risk"
        assert payload["submissions"][0]["reason"] == "detail history"
        assert payload["claims"][0]["challenge"]
        history = payload["moderation_history"]
        assert {entry["kind"] for entry in history} >= {"risk_state", "report", "submission", "claim", "audit"}
        assert any(
            entry["kind"] == "risk_state"
            and entry["notes"] == "internal detail notes"
            and entry["assigned_to"] == 240032
            and entry["escalation"] == "risk"
            for entry in history
        )
        assert any(entry["kind"] == "report" and entry["actor_id"] == 240033 for entry in history)
        assert {event["action"] for event in payload["audit_trail"]} >= {
            "channel_review",
            "channel_claim_review",
            "channel_report_review",
        }

    async def test_channel_owner_profile_api_requires_verified_owner(self, user_factory):
        await _set_platform_api_enabled("1")
        await _role_user(user_factory, 240034)
        await user_factory(telegram_id=240035)
        owner_init_data = make_init_data(240035, token="test_token")
        submitter_init_data = make_init_data(240034, token="test_token")
        channel = await submit_channel(
            {
                "channel": "@api_owner_profile_channel",
                "category": "ai",
                "language": "zh",
                "title": "Old API Owner Channel",
                "reason": "owner profile api",
            },
            submitter_id=240034,
        )
        await api_admin_channel_review(_request(
            method="POST",
            path=f"/platform/api/admin/channels/submissions/{channel['submission']['id']}/review",
            path_params={"submission_id": channel["submission"]["id"]},
            body={"user_id": 240034, "status": "approved"},
            authenticated=True,
        ))
        claim = await api_channel_claim(_request(
            method="POST",
            path=f"/platform/api/channels/{channel['channel']['id']}/claim",
            path_params={"channel_id": channel["channel"]["id"]},
            body={"user_id": 240035, "method": "manual"},
            authenticated=False,
            init_data=owner_init_data,
        ))
        claim_id = _json(claim)["result"]["id"]
        await api_channel_claim_review(_request(
            method="POST",
            path=f"/platform/api/channel-claims/{claim_id}/review",
            path_params={"claim_id": claim_id},
            body={"user_id": 240034, "approved": True},
            authenticated=True,
        ))

        denied = await api_channel_owner_profile(_request(
            method="POST",
            path=f"/platform/api/channels/{channel['channel']['id']}/owner-profile",
            path_params={"channel_id": channel["channel"]["id"]},
            body={"user_id": 240034, "title": "Not Owner"},
            authenticated=False,
            init_data=submitter_init_data,
        ))
        allowed = await api_channel_owner_profile(_request(
            method="POST",
            path=f"/platform/api/channels/{channel['channel']['id']}/owner-profile",
            path_params={"channel_id": channel["channel"]["id"]},
            body={
                "user_id": 240035,
                "title": "Updated API Owner Channel",
                "category": "models",
                "language": "en",
                "description": "Owner API description",
            },
            authenticated=False,
            init_data=owner_init_data,
        ))
        detail = await api_channel_detail(_request(
            path=f"/platform/api/channels/{channel['channel']['id']}",
            path_params={"channel_id": channel["channel"]["id"]},
            authenticated=False,
            init_data=owner_init_data,
        ))

        assert denied.status_code == 403
        assert _json(denied)["code"] == "forbidden"
        assert allowed.status_code == 200
        assert _json(allowed)["result"]["title"] == "Updated API Owner Channel"
        assert _json(detail)["result"]["channel"]["description"] == "Owner API description"
        assert _json(detail)["result"]["viewer"]["can_edit_profile"] is True

    async def test_owner_dashboard_api_is_mini_app_user_scoped(self, user_factory):
        await _set_platform_api_enabled("1")
        await _role_user(user_factory, 240047)
        await user_factory(telegram_id=240048)
        await user_factory(telegram_id=240049)
        owner_init_data = make_init_data(240048, token="test_token")
        other_init_data = make_init_data(240049, token="test_token")

        channel = await submit_channel(
            {
                "channel": "@api_owner_dashboard_channel",
                "category": "ai",
                "language": "zh",
                "title": "API Owner Dashboard Channel",
                "reason": "owner dashboard api",
            },
            submitter_id=240047,
        )
        await api_admin_channel_review(_request(
            method="POST",
            path=f"/platform/api/admin/channels/submissions/{channel['submission']['id']}/review",
            path_params={"submission_id": channel["submission"]["id"]},
            body={"user_id": 240047, "status": "approved"},
            authenticated=True,
        ))
        channel_claim = await api_channel_claim(_request(
            method="POST",
            path=f"/platform/api/channels/{channel['channel']['id']}/claim",
            path_params={"channel_id": channel["channel"]["id"]},
            body={"user_id": 240048, "method": "manual"},
            authenticated=False,
            init_data=owner_init_data,
        ))
        channel_claim_payload = _json(channel_claim)["result"]
        await api_channel_claim_review(_request(
            method="POST",
            path=f"/platform/api/channel-claims/{channel_claim_payload['id']}/review",
            path_params={"claim_id": channel_claim_payload["id"]},
            body={"user_id": 240047, "approved": True},
            authenticated=True,
        ))
        await api_channel_interaction(_request(
            method="POST",
            path=f"/platform/api/channels/{channel['channel']['id']}/interactions",
            path_params={"channel_id": channel["channel"]["id"]},
            body={"user_id": 240049, "action": "favorite", "source": "mini_app"},
            authenticated=False,
            init_data=other_init_data,
        ))

        relay = await submit_relay_provider(
            {
                "name": "API Owner Dashboard Relay",
                "base_url": "https://api-owner-dashboard-relay.example.com/v1?debug=1",
                "protocol": "openai-compatible",
                "region": "SG",
            },
            submitter_id=240047,
        )
        await api_admin_relay_review(_request(
            method="POST",
            path=f"/platform/api/admin/relays/{relay['id']}/review",
            path_params={"provider_id": relay["id"]},
            body={"user_id": 240047, "status": "approved", "risk_status": "normal"},
            authenticated=True,
        ))
        relay_claim = await api_relay_claim(_request(
            method="POST",
            path=f"/platform/api/relays/{relay['id']}/claim",
            path_params={"provider_id": relay["id"]},
            body={"user_id": 240048, "method": "manual"},
            authenticated=False,
            init_data=owner_init_data,
        ))
        relay_claim_payload = _json(relay_claim)["result"]
        await api_relay_claim_review(_request(
            method="POST",
            path=f"/platform/api/relay-claims/{relay_claim_payload['id']}/review",
            path_params={"claim_id": relay_claim_payload["id"]},
            body={"user_id": 240047, "approved": True},
            authenticated=True,
        ))
        await api_relay_feedback(_request(
            method="POST",
            path=f"/platform/api/relays/{relay['id']}/feedback",
            path_params={"provider_id": relay["id"]},
            body={"user_id": 240049, "feedback_type": "complaint", "text": "slow stream"},
            authenticated=False,
            init_data=other_init_data,
        ))

        dashboard = await api_owner_dashboard(_request(
            path="/platform/api/owner/dashboard",
            query="user_id=240048",
            authenticated=False,
            init_data=owner_init_data,
        ))
        blocked = await api_owner_dashboard(_request(
            path="/platform/api/owner/dashboard",
            query="user_id=240048",
            authenticated=False,
            init_data=other_init_data,
        ))
        other_dashboard = await api_owner_dashboard(_request(
            path="/platform/api/owner/dashboard",
            authenticated=False,
            init_data=other_init_data,
        ))
        admin_denied = await api_admin_owner_dashboards(_request(
            path="/platform/api/admin/owners/dashboard",
            authenticated=False,
            init_data=owner_init_data,
        ))
        admin_allowed = await api_admin_owner_dashboards(_request(
            path="/platform/api/admin/owners/dashboard",
            query="limit=10&offset=0",
            authenticated=True,
        ))

        assert dashboard.status_code == 200
        payload = _json(dashboard)["dashboard"]
        assert payload["owner"]["user_id"] == 240048
        assert payload["channels"]["total"] == 1
        assert payload["channels"]["items"][0]["channel"]["username"] == "api_owner_dashboard_channel"
        assert payload["channels"]["items"][0]["interactions"]["favorite"] == 1
        assert payload["relays"]["total"] == 1
        assert payload["relays"]["items"][0]["provider"]["name"] == "API Owner Dashboard Relay"
        assert payload["relays"]["items"][0]["provider"]["base_url"] == "https://api-owner-dashboard-relay.example.com/v1"
        assert payload["relays"]["items"][0]["feedback"]["counts"]["complaint"] == 1
        assert channel_claim_payload["challenge"] not in str(payload)
        assert relay_claim_payload["challenge"] not in str(payload)
        assert "debug=1" not in str(payload)
        assert blocked.status_code == 403
        assert _json(blocked)["code"] == "forbidden"
        assert other_dashboard.status_code == 200
        assert _json(other_dashboard)["dashboard"]["channels"]["total"] == 0
        assert _json(other_dashboard)["dashboard"]["relays"]["total"] == 0
        assert admin_denied.status_code == 401
        assert _json(admin_denied)["code"] == "unauthorized"
        assert admin_allowed.status_code == 200
        admin_payload = _json(admin_allowed)
        admin_owner_rows = {row["owner_id"]: row for row in admin_payload["owners"]}
        assert admin_owner_rows[240048]["channels"]["total"] == 1
        assert admin_owner_rows[240048]["channels"]["interactions"]["favorite"] == 1
        assert admin_owner_rows[240048]["relays"]["total"] == 1
        assert admin_owner_rows[240048]["relays"]["feedback"]["types"]["complaint"] == 1
        assert channel_claim_payload["challenge"] not in str(admin_payload)
        assert relay_claim_payload["challenge"] not in str(admin_payload)
        assert "base_url_hash" not in str(admin_payload)
        assert "debug=1" not in str(admin_payload)
        assert any(getattr(route, "path", "") == "/platform/api/owner/dashboard" for route in platform_routes)
        assert any(getattr(route, "path", "") == "/platform/api/admin/owners/dashboard" for route in platform_routes)

    async def test_admin_review_workload_allows_session_or_reviewer_role_and_reports_assignments(self, user_factory):
        await _set_platform_api_enabled("1")
        await _role_user(user_factory, 240060, "RISK_OPERATOR")
        await user_factory(telegram_id=240061)
        await user_factory(telegram_id=240062)
        init_data = make_init_data(240062, token="test_token")
        reviewer_init_data = make_init_data(240060, token="test_token")

        channel = await submit_channel(
            {
                "channel": "@api_workload_channel",
                "category": "ai",
                "language": "zh",
                "reason": "workload api",
            },
            submitter_id=240060,
        )
        await api_admin_channel_review(_request(
            method="POST",
            path=f"/platform/api/admin/channels/submissions/{channel['submission']['id']}/review",
            path_params={"submission_id": channel["submission"]["id"]},
            body={"user_id": 240060, "status": "approved"},
            authenticated=True,
        ))
        await api_channel_interaction(_request(
            method="POST",
            path=f"/platform/api/channels/{channel['channel']['id']}/interactions",
            path_params={"channel_id": channel["channel"]["id"]},
            body={"user_id": 240062, "action": "report", "source": "mini_app"},
            authenticated=False,
            init_data=init_data,
        ))
        await api_admin_channel_report_review(_request(
            method="POST",
            path=f"/platform/api/admin/channels/{channel['channel']['id']}/report-review",
            path_params={"channel_id": channel["channel"]["id"]},
            body={
                "user_id": 240060,
                "risk_status": "under_review",
                "notes": "internal workload api note",
                "assigned_to": 240061,
                "escalation": "urgent",
            },
            authenticated=True,
        ))

        relay = await submit_relay_provider(
            {
                "name": "API Workload Relay",
                "base_url": "https://api-workload-relay.example.com/v1",
                "protocol": "openai-compatible",
            },
            submitter_id=240060,
        )
        await api_admin_relay_review(_request(
            method="POST",
            path=f"/platform/api/admin/relays/{relay['id']}/review",
            path_params={"provider_id": relay["id"]},
            body={"user_id": 240060, "status": "approved", "risk_status": "normal"},
            authenticated=True,
        ))
        await api_relay_feedback(_request(
            method="POST",
            path=f"/platform/api/relays/{relay['id']}/feedback",
            path_params={"provider_id": relay["id"]},
            body={"user_id": 240062, "feedback_type": "complaint", "text": "workload complaint"},
            authenticated=False,
            init_data=init_data,
        ))

        denied = await api_admin_review_workload(_request(
            path="/platform/api/admin/review-workload",
            authenticated=False,
            init_data=init_data,
        ))
        allowed = await api_admin_review_workload(_request(
            path="/platform/api/admin/review-workload",
            authenticated=True,
        ))
        reviewer_allowed = await api_admin_review_workload(_request(
            path="/platform/api/admin/review-workload",
            authenticated=False,
            init_data=reviewer_init_data,
        ))

        assert denied.status_code == 403
        assert _json(denied)["code"] == "reviewer_role_required"
        assert allowed.status_code == 200
        assert reviewer_allowed.status_code == 200
        workload = _json(allowed)["workload"]
        assert workload["summary"]["open_total"] == 2
        assert workload["summary"]["unassigned_total"] == 1
        assert workload["summary"]["urgent_total"] == 1
        assert workload["queues"]["channel_reports"]["by_escalation"]["urgent"] == 1
        assert workload["queues"]["relay_feedback"]["by_feedback_type"]["complaint"] == 1
        reviewer_rows = {row["reviewer_id"]: row for row in workload["reviewers"]}
        assert reviewer_rows[240061]["queues"]["channel_reports"] == 1
        assert reviewer_rows[None]["queues"]["relay_feedback"] == 1
        assert {alert["type"] for alert in workload["alerts"]} == {"urgent_escalation"}
        assert "internal workload api note" not in str(workload)
        assert any(getattr(route, "path", "") == "/platform/api/admin/review-workload" for route in platform_routes)

    async def test_admin_audit_logs_are_session_only_filtered_and_redacted(self, user_factory):
        await _set_platform_api_enabled("1")
        await user_factory(telegram_id=240070)
        await user_factory(telegram_id=240071)
        init_data = make_init_data(240071, token="test_token")

        await log_audit(
            "channel_review",
            user_id=240070,
            resource_type="Channel",
            resource_id="api-audit-channel",
            details="status=approved api_key=leaked-secret sk-test-api-audit",
        )
        await log_audit(
            "relay_feedback_review",
            level="ERROR",
            user_id=240071,
            resource_type="RelayFeedback",
            resource_id="api-audit-feedback",
            details="Bearer relay-token followup",
        )

        denied = await api_admin_audit_logs(_request(
            path="/platform/api/admin/audit-logs",
            authenticated=False,
            init_data=init_data,
        ))
        allowed = await api_admin_audit_logs(_request(
            path="/platform/api/admin/audit-logs",
            query="action=channel_review&resource_type=Channel&user_id=240070&q=approved",
            authenticated=True,
        ))
        warning = await api_admin_audit_logs(_request(
            path="/platform/api/admin/audit-logs",
            query="level=ERROR&resource_id=api-audit-feedback",
            authenticated=True,
        ))

        assert denied.status_code == 401
        assert _json(denied)["code"] == "unauthorized"
        assert allowed.status_code == 200
        payload = _json(allowed)
        assert payload["total"] == 1
        assert payload["logs"][0]["action"] == "channel_review"
        assert payload["logs"][0]["user_id"] == 240070
        assert payload["logs"][0]["resource_type"] == "Channel"
        assert payload["filters"]["q"] == "approved"
        assert "leaked-secret" not in str(payload)
        assert "sk-test-api-audit" not in str(payload)
        assert "api_key=[redacted]" in payload["logs"][0]["details"]
        assert "ip_address" not in payload["logs"][0]
        assert warning.status_code == 200
        assert _json(warning)["logs"][0]["level"] == "ERROR"
        assert "relay-token" not in str(_json(warning))
        assert any(getattr(route, "path", "") == "/platform/api/admin/audit-logs" for route in platform_routes)

    async def test_review_routes_reject_non_reviewer_mini_app_user(self, user_factory):
        await _set_platform_api_enabled("1")
        await user_factory(telegram_id=240020)
        init_data = make_init_data(240020, token="test_token")

        denied = await api_admin_channel_submissions(_request(
            path="/platform/api/admin/channels/submissions",
            authenticated=False,
            init_data=init_data,
        ))

        assert denied.status_code == 403
        assert _json(denied)["code"] == "reviewer_role_required"

    async def test_admin_dashboard_is_session_only_and_reports_unavailable_coverage(self, user_factory):
        await _set_platform_api_enabled("1")
        await user_factory(telegram_id=240050)
        init_data = make_init_data(240050, token="test_token")

        denied = await api_admin_dashboard(_request(
            path="/platform/api/admin/dashboard",
            authenticated=False,
            init_data=init_data,
        ))
        allowed = await api_admin_dashboard(_request(
            path="/platform/api/admin/dashboard",
            authenticated=True,
        ))

        assert denied.status_code == 401
        assert _json(denied)["code"] == "unauthorized"
        assert allowed.status_code == 200
        dashboard = _json(allowed)["dashboard"]
        assert "channels" in dashboard
        assert "relays" in dashboard
        assert "model_lab" in dashboard
        assert dashboard["model_lab"]["average_cost"]["status"] == "unavailable"
        assert dashboard["model_lab"]["latency"]["status"] == "unavailable"
        assert dashboard["relays"]["availability"]["status"] == "unavailable"
        assert dashboard["operating"]["thresholds"]["invite_retention"]["min_samples"] == 5
        assert dashboard["operating"]["thresholds"]["bans"]["warning_count"] == 1
        assert dashboard["operating"]["thresholds"]["appeals"]["warning_count"] == 3
        assert dashboard["operating"]["thresholds"]["reviewer_load"]["open_warning_per_reviewer"] == 5
        assert isinstance(dashboard["operating"]["alerts"], list)
        assert dashboard["model_lab"]["operations"]["commands"]["model-test-drain"]["status"] == "unavailable"
        assert dashboard["model_lab"]["operations"]["commands"]["model-sample-retention"]["status"] == "unavailable"
        assert "model_lab.average_cost" in dashboard["coverage"]["unavailable"]
        assert "model_lab.latency" in dashboard["coverage"]["unavailable"]
        assert "relay.availability" in dashboard["coverage"]["unavailable"]
        assert "model_lab.operations.model-test-drain" in dashboard["coverage"]["unavailable"]
        assert "model_lab.operations.model-sample-retention" in dashboard["coverage"]["unavailable"]

    async def test_platform_review_app_requires_admin_session_and_uses_admin_review_api(self):
        unauthenticated = await platform_review_app_page(_request(
            path="/admin/platform/review/app",
            authenticated=False,
        ))
        authenticated = await platform_review_app_page(_request(
            path="/admin/platform/review/app",
            authenticated=True,
        ))
        html = authenticated.body.decode("utf-8")

        assert unauthenticated.status_code == 302
        assert unauthenticated.headers["location"] == "/admin/login"
        assert authenticated.status_code == 200
        assert "/platform/api/admin/channels/submissions" in html
        assert "/platform/api/admin/channel-claims" in html
        assert "Verification" in html
        assert "expected:" in html
        assert "/platform/api/admin/channel-reports" in html
        assert "/platform/api/admin/channels/${channelId}" in html
        assert "/platform/api/admin/relays" in html
        assert "/platform/api/admin/relays/${providerId}" in html
        assert "/platform/api/admin/relay-claims" in html
        assert "/platform/api/admin/relay-feedback" in html
        assert "/platform/api/admin/relay-feedback?feedback_type=complaint" in html
        assert "Relay complaints" in html
        assert "Detail" in html
        assert "renderChannelAdminDetail" in html
        assert "renderRelayAdminDetail" in html
        assert "Moderation history" in html
        assert "moderation_history" in html
        assert "Assigned user" in html
        assert "id or unassigned" in html
        assert "id or unreviewed" in html
        assert "reviewFilters" in html
        assert "followupFilters" in html
        assert "Follow-up" in html
        assert "needs_followup" in html
        assert "in_followup" in html
        assert "Acknowledge" in html
        assert "Monitor" in html
        assert "Resolve" in html
        assert '["assigned_to", "assigned_to"]' in html
        assert '["reviewed_by", "reviewed_by"]' in html
        assert '["escalation", "escalation"]' in html
        assert '["followup_state", "followup_state"]' in html
        assert "urgent" in html
        assert "/platform/api/admin/dashboard" in html
        assert "/platform/api/admin/owners/dashboard" in html
        assert "/platform/api/admin/review-workload" in html
        assert "/platform/api/admin/audit-logs" in html
        assert "Owner dashboards" in html
        assert "Review workload" in html
        assert "Audit logs" in html
        assert "Operating alerts" in html
        assert "Model ops" in html
        assert "ownerDashboards" in html
        assert "reviewWorkload" in html
        assert "auditFilters" in html
        assert '["level", "level"]' in html
        assert '["resource_type", "resource_type"]' in html
        assert '${queue.id}_resource_type' in html
        assert "resource_total" in html
        assert "Urgent escalations" in html
        assert "Thresholds" in html
        assert "Coverage" in html
        assert "Recent resources" in html
        assert "Unavailable metrics" in html
        assert "/client/api" not in html
        assert any(getattr(route, "path", "") == "/admin/platform/review/app" for route in platform_routes)
        assert any(getattr(route, "path", "") == "/platform/api/admin/owners/dashboard" for route in platform_routes)
        assert any(getattr(route, "path", "") == "/platform/api/admin/review-workload" for route in platform_routes)
        assert any(getattr(route, "path", "") == "/platform/api/admin/audit-logs" for route in platform_routes)

    async def test_platform_mini_app_page_uses_telegram_init_data_and_safe_entrypoints(self):
        response = await platform_mini_app_page(_request(path="/platform/app", authenticated=False))
        html = response.body.decode("utf-8")

        assert response.status_code == 200
        assert "https://telegram.org/js/telegram-web-app.js" in html
        assert "x-telegram-init-data" in html
        assert "/platform/api/channels/submissions" in html
        assert "/platform/api/relays" in html
        assert "/platform/api/relays/discover" in html
        assert "/platform/api/relay-tests" in html
        assert "/platform/api/reports" in html
        assert "data-model-report" in html
        assert "data-report-visibility" in html
        assert "modelJobPrev" in html
        assert "modelJobNext" in html
        assert "modelJobPageState" in html
        assert "modelReportPrev" in html
        assert "modelReportNext" in html
        assert "modelReportPageState" in html
        assert "modelLabState.jobHasMore" in html
        assert "modelLabState.reportHasMore" in html
        assert "visibilityLabel" in html
        assert "renderScoreBadges" in html
        assert "renderReportTimeline" in html
        assert "renderEvidenceSummary" in html
        assert "renderVisibilityControls" in html
        assert "renderReportShareControls" in html
        assert "renderRunHistory" in html
        assert "运行历史" in html
        assert html.count("function renderRunHistory") == 1
        assert "publicReportUrl" in html
        assert "data-copy-report-url" in html
        assert "data-share-report-url" in html
        assert "data-share-report-text" in html
        assert "reportShareText" in html
        assert "copyTextToClipboard" in html
        assert "telegramShareUrl" in html
        assert "shareReportLink" in html
        assert "navigator.share" in html
        assert "openTelegramLink" in html
        assert "https://t.me/share/url" in html
        assert "分享报告" in html
        assert "私有：仅提交者可查看" in html
        assert "不公开：仅持链接/授权入口可查看" in html
        assert "公开：可进入公开报告流" in html
        assert "脱敏证据摘要" in html
        assert "时间线" in html
        assert 'data-visibility="unlisted"' in html
        assert "刷新任务" in html
        assert "刷新报告" in html
        assert "/platform/api/users/" in html
        assert "ledgerAccountType" in html
        assert "filterLedger" in html
        assert "ledgerPrev" in html
        assert "ledgerNext" in html
        assert "ledgerPageState" in html
        assert "account_type" in html
        assert "ledgerState.hasMore" in html
        assert "当前筛选" in html
        assert "channelDetail" in html
        assert "relayDetail" in html
        assert "data-detail" in html
        assert "can_edit_profile" in html
        assert 'data-channel-owner-profile="${h(channel.id)}"' in html
        assert 'data-relay-owner-profile="${h(provider.id)}"' in html
        assert "renderClaimVerification" in html
        assert "claim-verification" in html
        assert 'data-claim-verification="${h(kind)}"' in html
        assert "Expected text:" in html
        assert "Challenge:" in html
        assert "channelState.claimNotice" in html
        assert "relayState.claimNotice" in html
        assert 'method: "domain"' in html
        assert "Claim #${payload.result?.id || channelId} created" in html
        assert "Relay claim #${payload.result?.id || providerId} created" in html
        assert "/platform/api/channels/${channelId}/owner-profile" in html
        assert "/platform/api/relays/${providerId}/owner-profile" in html
        assert "channelOwnerProfileState" in html
        assert "relayOwnerProfileState" in html
        assert "renderRelayFeedbackForms" in html
        assert "submitRelayFeedback" in html
        assert 'data-relay-feedback-form="rating"' in html
        assert 'data-relay-feedback-form="complaint"' in html
        assert "relayFeedbackState" in html
        assert "评价已提交，等待审核" in html
        assert "投诉已提交，等待审核" in html
        assert "window.prompt(" not in html
        assert "暂无已审核评价" in html
        assert 'data-tab="contribute"' in html
        assert "/platform/api/owner/dashboard" in html
        assert "loadOwnerDashboard" in html
        assert "ownerDashboardState" in html
        assert "ownerDashboardList" in html
        assert "我的频道" in html
        assert "我的中转站" in html
        assert "data-owner-channel" in html
        assert "data-owner-relay" in html
        assert "function renderEmpty" in html
        assert "function renderTelegramRequired" in html
        assert "需要从 Telegram 打开" in html
        assert "当前没有 Telegram initData，个人数据无法读取。" in html
        assert "function bindUtilityButtons" in html
        assert 'data-scroll-to="channelForm"' in html
        assert 'data-scroll-to="relayForm"' in html
        assert 'data-scroll-to="testForm"' in html
        assert 'data-jump="channels"' in html
        assert 'data-jump="relays"' in html
        assert "暂无频道结果" in html
        assert "暂无中转站结果" in html
        assert "暂无已认领频道" in html
        assert "暂无已认领中转站" in html
        assert "暂无检测任务" in html
        assert "暂无检测报告" in html
        assert "暂无账本条目" in html
        assert "任务不存在" in html
        assert "报告不存在" in html
        assert "localStorage" not in html
        assert "/client/api" not in html
        assert "Do not send API keys in chat" not in html
        assert "不证明真实上游模型" in html
        assert any(getattr(route, "path", "") == "/platform/app" for route in platform_routes)

    async def test_public_report_page_uses_public_api_without_telegram_init_data(self):
        response = await platform_public_report_page(_request(
            path="/platform/reports",
            authenticated=False,
        ))
        html = response.body.decode("utf-8")

        assert response.status_code == 200
        assert "/platform/api/public/reports" in html
        assert "/platform/api/reports/" not in html
        assert "x-telegram-init-data" not in html
        assert "脱敏证据摘要" in html
        assert "运行历史" in html
        assert "renderRunHistory" in html
        assert html.count("function renderRunHistory") == 1
        assert "黑盒测试不能证明真实上游模型" in html
        assert "data-copy-report-url" in html
        assert "data-share-report-url" in html
        assert "data-share-report-text" in html
        assert "reportShareText" in html
        assert "copyTextToClipboard" in html
        assert "telegramShareUrl" in html
        assert "shareReportLink" in html
        assert "navigator.share" in html
        assert "https://t.me/share/url" in html
        assert "分享报告" in html
        assert any(getattr(route, "path", "") == "/platform/reports" for route in platform_routes)
        assert any(getattr(route, "path", "") == "/platform/reports/{report_id:int}" for route in platform_routes)
        assert any(getattr(route, "path", "") == "/platform/api/public/reports" for route in platform_routes)
        assert any(getattr(route, "path", "") == "/platform/api/public/reports/{report_id:int}" for route in platform_routes)
