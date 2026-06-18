from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from bot.database.methods.platform import (
    MODEL_REPORT_LIMITATION,
    admin_owner_dashboards,
    admin_review_workload_metrics,
    claim_model_test_job,
    complete_model_test_job,
    create_channel_claim,
    create_ledger_entry,
    create_opening_ledger_entries,
    create_model_test_job,
    create_model_test_report,
    create_relay_claim,
    discover_channels,
    discover_relay_providers,
    get_channel_detail,
    get_channel_admin_detail,
    get_model_test_job,
    get_model_test_report,
    get_relay_provider_detail,
    ledger_balance,
    list_channel_reports,
    list_ledger_entries,
    list_model_test_jobs,
    list_model_test_reports,
    list_platform_audit_logs,
    list_relay_feedback,
    mark_model_test_job_failed,
    add_relay_feedback,
    owner_dashboard,
    platform_dashboard_metrics,
    record_fraud_event,
    record_channel_interaction,
    record_model_test_run,
    record_relay_availability_sample,
    review_channel_report,
    reconcile_ledger_balances,
    review_relay_feedback,
    review_relay_provider,
    verify_relay_claim_domain_control,
    set_report_visibility,
    review_channel_submission,
    submit_channel,
    submit_relay_provider,
    update_channel_owner_profile,
    update_relay_owner_profile,
    verify_channel_claim,
    verify_relay_claim,
)
from bot.database.methods.audit import log_audit
from bot.database.methods import (
    get_or_create_group_invite_link,
    perform_daily_checkin,
    record_group_invite_join,
    reward_group_inviter_after_checkin,
)
from bot.misc.url_safety import UnsafeURL, fingerprint_secret, normalize_public_https_url
from bot.model_lab.dispatcher import drain_model_test_jobs, run_model_test_job_once


class TestURLSafety:
    def test_normalizes_https_and_redacts_query_for_public_url(self):
        safe = normalize_public_https_url("https://Example.com/v1/chat?x=1")

        assert safe.normalized == "https://example.com/v1/chat?x=1"
        assert safe.public == "https://example.com/v1/chat"
        assert len(safe.url_hash) == 64

    @pytest.mark.parametrize(
        "url",
        [
            "http://example.com",
            "https://localhost/v1",
            "https://127.0.0.1/v1",
            "https://10.0.0.1/v1",
            "https://169.254.169.254/latest/meta-data",
            "https://example.com:5432/v1",
            "https://example.com/v1?api_key=secret",
            "https://example.com/v1?token=secret",
        ],
    )
    def test_blocks_unsafe_targets(self, url):
        with pytest.raises(UnsafeURL):
            normalize_public_https_url(url)


class TestLedgerFoundation:
    async def test_ledger_entry_is_idempotent_and_reconciles_available_balance(self, user_factory):
        await user_factory(telegram_id=210001)

        first = await create_ledger_entry(
            210001,
            "points",
            "opening_balance",
            10,
            idempotency_key="ledger-open-210001",
        )
        second = await create_ledger_entry(
            210001,
            "points",
            "opening_balance",
            10,
            idempotency_key="ledger-open-210001",
        )

        assert first["id"] == second["id"]
        assert await ledger_balance(210001, "points") == Decimal("10.00")

    async def test_opening_entries_are_idempotent_and_reconcile_existing_fields(self, user_factory):
        await user_factory(telegram_id=210002)
        from bot.database.main import Database
        from bot.database.models.main import User
        from sqlalchemy import select

        async with Database().session() as s:
            user = (await s.execute(select(User).where(User.telegram_id == 210002))).scalars().one()
            user.balance = Decimal("25.00")
            user.points_balance = 7

        first = await create_opening_ledger_entries()
        second = await create_opening_ledger_entries()
        reconciliation = await reconcile_ledger_balances()

        assert first["created"] == 2
        assert second["created"] == 0
        assert second["skipped"] == 2
        assert reconciliation["mismatch_count"] == 0
        assert await ledger_balance(210002, "balance") == Decimal("25.00")
        assert await ledger_balance(210002, "points") == Decimal("7.00")

    async def test_opening_entries_dry_run_previews_without_writing(self, user_factory):
        await user_factory(telegram_id=200004)
        from bot.database.main import Database
        from bot.database.models.main import LedgerEntries, User
        from sqlalchemy import func, select

        async with Database().session() as s:
            user = (await s.execute(select(User).where(User.telegram_id == 200004))).scalars().one()
            user.balance = Decimal("12.50")
            user.points_balance = 4

        preview = await create_opening_ledger_entries(limit=1, dry_run=True)
        dry_reconciliation = await reconcile_ledger_balances(limit=1)
        async with Database().session() as s:
            row_count = (await s.execute(
                select(func.count(LedgerEntries.id)).where(LedgerEntries.user_id == 200004)
            )).scalar_one()

        created = await create_opening_ledger_entries(limit=1)
        reconciliation = await reconcile_ledger_balances(limit=1)

        assert preview["dry_run"] is True
        assert preview["created"] == 0
        assert preview["would_create"] == 2
        assert {item["account_type"] for item in preview["preview"]} == {"balance", "points"}
        assert {"12.50", "4.00"} == {item["amount"] for item in preview["preview"]}
        assert row_count == 0
        assert dry_reconciliation["mismatch_count"] == 1
        assert created["created"] == 2
        assert reconciliation["mismatch_count"] == 0

    async def test_lists_ledger_entries_with_available_totals(self, user_factory):
        await user_factory(telegram_id=210003)
        await create_ledger_entry(
            210003,
            "points",
            "opening_balance",
            5,
            idempotency_key="ledger-open-210003-points",
        )
        await create_ledger_entry(
            210003,
            "points",
            "bonus",
            2,
            idempotency_key="ledger-bonus-210003-points",
        )

        ledger = await list_ledger_entries(210003, "points")

        assert ledger["balances"]["points"] == "7.00"
        assert [entry["entry_type"] for entry in ledger["entries"]] == ["bonus", "opening_balance"]


class TestChannelFoundation:
    async def test_channel_submission_normalizes_dedupes_and_discovers_approved(self, user_factory):
        await user_factory(telegram_id=220001)
        result = await submit_channel(
            {
                "channel": "https://t.me/AI_Channel_Test",
                "category": "gpt",
                "language": "zh",
                "title": "AI Channel",
                "reason": "High quality AI updates",
                "commercial_content": "occasional",
                "submitter_relation": "recommender",
            },
            submitter_id=220001,
        )
        duplicate = await submit_channel(
            {
                "channel": "@ai_channel_test",
                "category": "gpt",
                "language": "zh",
                "reason": "same submitter",
            },
            submitter_id=220001,
        )

        assert result["channel"]["username"] == "ai_channel_test"
        assert duplicate["submission"]["duplicate"] is True

        reviewed = await review_channel_submission(result["submission"]["id"], reviewer_id=220001, status="approved")
        assert reviewed is True
        rows = await discover_channels(query="channel", category="gpt", language="zh")
        assert rows["total"] == 1
        assert rows["channels"][0]["username"] == "ai_channel_test"

        interaction = await record_channel_interaction(220001, result["channel"]["id"], "favorite", source="test")
        assert interaction["already_recorded"] is False
        duplicate_interaction = await record_channel_interaction(220001, result["channel"]["id"], "favorite", source="test")
        assert duplicate_interaction["already_recorded"] is True

    async def test_channel_claim_approval_sets_owner(self, user_factory):
        await user_factory(telegram_id=220010)
        await user_factory(telegram_id=220011)
        submission = await submit_channel(
            {
                "channel": "@claim_test_channel",
                "category": "gpt",
                "language": "zh",
                "reason": "owner claim test",
            },
            submitter_id=220010,
        )

        claim = await create_channel_claim(submission["channel"]["id"], 220011)
        ok = await verify_channel_claim(claim["id"], reviewer_id=220010, approved=True)

        assert ok is True
        from bot.database.main import Database
        from bot.database.models.main import Channels
        from sqlalchemy import select

        async with Database().session() as s:
            channel = (
                await s.execute(select(Channels).where(Channels.id == submission["channel"]["id"]))
            ).scalars().one()
            assert channel.owner_user_id == 220011

    async def test_bot_admin_channel_claim_requires_matching_live_proof(self, user_factory):
        await user_factory(telegram_id=220014)
        await user_factory(telegram_id=220015)
        submission = await submit_channel(
            {
                "channel": "@bot_admin_claim_channel",
                "category": "gpt",
                "language": "zh",
                "reason": "bot admin owner claim test",
            },
            submitter_id=220014,
        )

        claim = await create_channel_claim(submission["channel"]["id"], 220015, method="bot_admin")

        with pytest.raises(ValueError, match="Bot admin verification"):
            await verify_channel_claim(claim["id"], reviewer_id=220014, approved=True)

        with pytest.raises(ValueError, match="does not match"):
            await verify_channel_claim(
                claim["id"],
                reviewer_id=220014,
                approved=True,
                bot_admin_verification={
                    "verified": True,
                    "channel_id": submission["channel"]["id"],
                    "claimant_id": 220099,
                    "telegram_status": "administrator",
                },
            )

        ok = await verify_channel_claim(
            claim["id"],
            reviewer_id=220014,
            approved=True,
            bot_admin_verification={
                "verified": True,
                "channel_id": submission["channel"]["id"],
                "claimant_id": 220015,
                "telegram_chat": "@bot_admin_claim_channel",
                "telegram_status": "administrator",
            },
        )

        assert ok is True
        admin_logs = await list_platform_audit_logs(action="channel_claim_review")
        assert admin_logs["logs"][0]["details"].startswith(
            "status=approved, method=bot_admin, bot_admin_verified=True"
        )

        from bot.database.main import Database
        from bot.database.models.main import Channels
        from sqlalchemy import select

        async with Database().session() as s:
            channel = (
                await s.execute(select(Channels).where(Channels.id == submission["channel"]["id"]))
            ).scalars().one()
            assert channel.owner_user_id == 220015

    async def test_channel_claim_verification_context_is_admin_only(self, user_factory):
        await user_factory(telegram_id=220012)
        await user_factory(telegram_id=220013)
        submission = await submit_channel(
            {
                "channel": "@claim_verify_channel",
                "category": "gpt",
                "language": "zh",
                "reason": "owner claim verification test",
            },
            submitter_id=220012,
        )
        await review_channel_submission(submission["submission"]["id"], reviewer_id=220012, status="approved")

        claim = await create_channel_claim(submission["channel"]["id"], 220013, method="challenge")
        detail = await get_channel_detail(submission["channel"]["id"], user_id=220013)

        assert claim["method"] == "challenge"
        assert claim["challenge"]
        assert claim["verification"]["challenge"] == claim["challenge"]
        assert claim["verification"]["expected_text"] == f"TGSellBot claim {claim['challenge']}"
        assert "challenge" not in detail["claims"][0]
        assert detail["claims"][0]["verification"]["challenge_required"] is True
        assert detail["claims"][0]["verification"]["challenge_provided"] is True

        with pytest.raises(ValueError):
            await create_channel_claim(submission["channel"]["id"], 220013, method="chat_message")

    async def test_channel_detail_exposes_public_counts_and_viewer_state(self, user_factory):
        await user_factory(telegram_id=220022)
        await user_factory(telegram_id=220023)
        submission = await submit_channel(
            {
                "channel": "@detail_test_channel",
                "category": "gpt",
                "language": "zh",
                "title": "Detail Test",
                "reason": "detail test",
            },
            submitter_id=220022,
        )
        await review_channel_submission(submission["submission"]["id"], reviewer_id=220022, status="approved")
        await record_channel_interaction(220023, submission["channel"]["id"], "favorite", source="mini_app")
        await record_channel_interaction(220023, submission["channel"]["id"], "report", source="mini_app")

        detail = await get_channel_detail(submission["channel"]["id"], user_id=220023)

        assert detail["channel"]["username"] == "detail_test_channel"
        assert detail["interactions"]["favorite"] == 1
        assert detail["interactions"]["report"] == 1
        assert detail["viewer"]["favorite"] is True
        assert detail["viewer"]["reported"] is True
        assert detail["claim"]["status"] == "unclaimed"
        assert detail["submissions"][0]["reason"] == "detail test"
        assert detail["claims"] == []
        assert detail["audit_trail"]
        assert detail["audit_trail"][0]["action"] == "channel_review"

    async def test_channel_report_queue_updates_risk_and_blocks_discovery(self, user_factory):
        await user_factory(telegram_id=220020)
        await user_factory(telegram_id=220021)
        submission = await submit_channel(
            {
                "channel": "@report_test_channel",
                "category": "gpt",
                "language": "zh",
                "title": "Report Test",
                "reason": "report triage test",
            },
            submitter_id=220020,
        )
        await review_channel_submission(submission["submission"]["id"], reviewer_id=220020, status="approved")

        report = await record_channel_interaction(220021, submission["channel"]["id"], "report", source="mini_app")
        duplicate = await record_channel_interaction(220021, submission["channel"]["id"], "report", source="mini_app")
        queue = await list_channel_reports(status="reported")

        assert report["already_recorded"] is False
        assert duplicate["already_recorded"] is True
        assert len(queue["reports"]) == 1
        assert queue["reports"][0]["report"]["report_count"] == 1
        assert queue["reports"][0]["channel"]["risk_status"] == "reported"

        reviewed = await review_channel_report(
            submission["channel"]["id"],
            reviewer_id=220020,
            risk_status="risk_blocked",
            notes="blocked by report triage",
            assigned_to=220020,
            escalation="risk",
        )
        blocked_queue = await list_channel_reports(status="risk_blocked")
        discovered = await discover_channels(query="report", category="gpt", language="zh")

        assert reviewed is True
        assert blocked_queue["reports"][0]["channel"]["risk_status"] == "risk_blocked"
        assert blocked_queue["reports"][0]["report"]["notes"] == "blocked by report triage"
        assert blocked_queue["reports"][0]["report"]["reviewed_by"] == 220020
        assert blocked_queue["reports"][0]["report"]["reviewed_at"]
        assert blocked_queue["reports"][0]["report"]["assigned_to"] == 220020
        assert blocked_queue["reports"][0]["report"]["escalation"] == "risk"
        assert "risk_notes" not in blocked_queue["reports"][0]["channel"]
        assert discovered["total"] == 0

    async def test_channel_admin_detail_includes_report_history_without_public_leak(self, user_factory):
        await user_factory(telegram_id=220030)
        await user_factory(telegram_id=220031)
        submission = await submit_channel(
            {
                "channel": "@admin_detail_channel",
                "category": "ai",
                "language": "zh",
                "title": "Admin Detail Channel",
                "reason": "admin detail test",
            },
            submitter_id=220030,
        )
        await review_channel_submission(submission["submission"]["id"], reviewer_id=220030, status="approved")
        claim = await create_channel_claim(submission["channel"]["id"], 220030, method="manual")
        await verify_channel_claim(claim["id"], reviewer_id=220030, approved=True, notes="manual owner proof")
        await record_channel_interaction(220031, submission["channel"]["id"], "report", source="mini_app")
        await record_channel_interaction(220031, submission["channel"]["id"], "favorite", source="mini_app")
        await review_channel_report(
            submission["channel"]["id"],
            reviewer_id=220030,
            risk_status="under_review",
            notes="internal report notes",
            assigned_to=220030,
            escalation="operator",
        )

        admin_detail = await get_channel_admin_detail(submission["channel"]["id"])
        public_detail = await get_channel_detail(submission["channel"]["id"], user_id=220031)

        assert admin_detail["channel"]["risk_notes"] == "internal report notes"
        assert admin_detail["channel"]["owner_user_id"] == 220030
        assert admin_detail["report"]["report_count"] == 1
        assert admin_detail["report"]["assigned_to"] == 220030
        assert admin_detail["report"]["escalation"] == "operator"
        assert admin_detail["interactions"]["report"] == 1
        assert admin_detail["interactions"]["favorite"] == 1
        assert admin_detail["submissions"][0]["reason"] == "admin detail test"
        assert admin_detail["claims"][0]["challenge"] == claim["challenge"]
        assert {entry["action"] for entry in admin_detail["audit_trail"]} >= {
            "channel_review",
            "channel_claim_review",
            "channel_report_review",
        }
        assert "risk_notes" not in public_detail["channel"]
        assert "challenge" not in public_detail["claims"][0]

    async def test_channel_owner_profile_update_is_owner_scoped(self, user_factory):
        await user_factory(telegram_id=220040)
        await user_factory(telegram_id=220041)
        submission = await submit_channel(
            {
                "channel": "@owner_profile_channel",
                "category": "ai",
                "language": "zh",
                "title": "Old Channel Title",
                "reason": "owner profile",
            },
            submitter_id=220040,
        )
        await review_channel_submission(submission["submission"]["id"], reviewer_id=220040, status="approved")
        claim = await create_channel_claim(submission["channel"]["id"], 220041, method="manual")
        await verify_channel_claim(claim["id"], reviewer_id=220040, approved=True)

        with pytest.raises(PermissionError):
            await update_channel_owner_profile(
                submission["channel"]["id"],
                220040,
                {"title": "Unauthorized"},
            )

        updated = await update_channel_owner_profile(
            submission["channel"]["id"],
            220041,
            {
                "title": "Owner Edited Channel",
                "category": "models",
                "language": "en",
                "description": "Owner maintained editorial profile",
            },
        )
        detail = await get_channel_detail(submission["channel"]["id"], user_id=220041)
        non_owner_detail = await get_channel_detail(submission["channel"]["id"], user_id=220040)

        assert updated["title"] == "Owner Edited Channel"
        assert updated["category"] == "models"
        assert updated["language"] == "en"
        assert detail["channel"]["description"] == "Owner maintained editorial profile"
        assert detail["channel"]["owner_verified"] is True
        assert detail["viewer"]["can_edit_profile"] is True
        assert non_owner_detail["viewer"]["can_edit_profile"] is False


class TestRelayAndModelLabFoundation:
    async def test_relay_submission_dedupes_by_normalized_hash(self, user_factory):
        await user_factory(telegram_id=230001)
        first = await submit_relay_provider(
            {
                "name": "Relay One",
                "base_url": "https://relay.example.com/v1?x=1",
                "protocol": "openai-compatible",
                "model_scope": "gpt models",
            },
            submitter_id=230001,
        )
        duplicate = await submit_relay_provider(
            {
                "name": "Relay One Again",
                "base_url": "https://relay.example.com/v1?x=1",
                "protocol": "openai-compatible",
            },
            submitter_id=230001,
        )

        assert first["base_url"] == "https://relay.example.com/v1"
        assert duplicate["duplicate"] is True
        assert duplicate["id"] == first["id"]

    async def test_relay_directory_lists_approved_and_detail_feedback(self, user_factory):
        await user_factory(telegram_id=230020)
        from bot.database.main import Database
        relay = await submit_relay_provider(
            {
                "name": "Directory Relay",
                "base_url": "https://directory-relay.example.com/v1?trace=1",
                "protocol": "openai-compatible",
                "model_scope": "gpt models",
                "region": "HK",
                "pricing": "metered",
            },
            submitter_id=230020,
        )
        hidden = await submit_relay_provider(
            {
                "name": "Hidden Relay",
                "base_url": "https://hidden-relay.example.com/v1",
                "protocol": "openai-compatible",
                "model_scope": "gpt models",
                "region": "HK",
            },
            submitter_id=230020,
        )
        await review_relay_provider(relay["id"], reviewer_id=230020, status="approved", risk_status="normal")
        await review_relay_provider(hidden["id"], reviewer_id=230020, status="approved", risk_status="risk_blocked")
        await add_relay_feedback(relay["id"], 230020, "rating", text="works", rating=5)
        async with Database().session() as s:
            from bot.database.models.main import RelayFeedback
            from sqlalchemy import select

            feedback = (await s.execute(select(RelayFeedback))).scalars().one()
            feedback.status = "approved"

        directory = await discover_relay_providers(query="directory", protocol="openai-compatible", region="HK")
        detail = await get_relay_provider_detail(relay["id"])
        blocked_detail = await get_relay_provider_detail(hidden["id"])

        assert directory["total"] == 1
        assert directory["providers"][0]["name"] == "Directory Relay"
        assert directory["providers"][0]["base_url"] == "https://directory-relay.example.com/v1"
        assert detail["provider"]["pricing"] == "metered"
        assert detail["feedback"]["average_rating"] == 5.0
        assert detail["feedback"]["counts"]["rating"] == 1
        assert detail["feedback"]["recent"][0]["text"] == "works"
        assert detail["claims"] == []
        assert detail["audit_trail"]
        assert {entry["action"] for entry in detail["audit_trail"]} >= {"relay_submit", "relay_review"}
        assert blocked_detail is None

    async def test_relay_feedback_review_tracks_internal_outcome_without_public_leak(self, user_factory):
        await user_factory(telegram_id=230022)
        await user_factory(telegram_id=230023)
        relay = await submit_relay_provider(
            {
                "name": "Outcome Relay",
                "base_url": "https://outcome-relay.example.com/v1",
                "protocol": "openai-compatible",
            },
            submitter_id=230022,
        )
        await review_relay_provider(relay["id"], reviewer_id=230022, status="approved", risk_status="normal")
        feedback = await add_relay_feedback(
            relay["id"],
            user_id=230023,
            feedback_type="complaint",
            text="timeout on stream",
        )

        ok = await review_relay_feedback(
            feedback["id"],
            reviewer_id=230022,
            status="approved",
            notes="provider confirmed incident",
            assigned_to=230022,
            escalation="operator",
            outcome="provider_fixed",
            followup_notes="provider deployed timeout fix",
        )
        queue = await list_relay_feedback(feedback_type="complaint", outcome="provider_fixed")
        detail = await get_relay_provider_detail(relay["id"])

        assert ok is True
        row = queue["feedback"][0]["feedback"]
        assert row["id"] == feedback["id"]
        assert row["outcome"] == "provider_fixed"
        assert row["followup_notes"] == "provider deployed timeout fix"
        assert row["resolved_by"] == 230022
        assert row["resolved_at"]
        assert detail["feedback"]["recent"][0]["text"] == "timeout on stream"
        assert "outcome" not in detail["feedback"]["recent"][0]
        assert "followup_notes" not in detail["feedback"]["recent"][0]

        with pytest.raises(ValueError):
            await review_relay_feedback(feedback["id"], reviewer_id=230022, status="approved", outcome="freeform")

    async def test_relay_claim_approval_sets_owner(self, user_factory):
        await user_factory(telegram_id=230010)
        await user_factory(telegram_id=230011)
        relay = await submit_relay_provider(
            {
                "name": "Claim Relay",
                "base_url": "https://claim-relay.example.com/v1",
                "protocol": "openai-compatible",
            },
            submitter_id=230010,
        )

        claim = await create_relay_claim(relay["id"], 230011)
        ok = await verify_relay_claim(claim["id"], reviewer_id=230010, approved=True)

        assert ok is True
        from bot.database.main import Database
        from bot.database.models.main import RelayProviders
        from sqlalchemy import select

        async with Database().session() as s:
            provider = (
                await s.execute(select(RelayProviders).where(RelayProviders.id == relay["id"]))
            ).scalars().one()
            assert provider.owner_user_id == 230011

    async def test_relay_claim_verification_context_is_admin_only(self, user_factory):
        await user_factory(telegram_id=230012)
        await user_factory(telegram_id=230013)
        relay = await submit_relay_provider(
            {
                "name": "Claim Verify Relay",
                "base_url": "https://claim-verify-relay.example.com/v1",
                "protocol": "openai-compatible",
            },
            submitter_id=230012,
        )
        await review_relay_provider(relay["id"], reviewer_id=230012, status="approved", risk_status="normal")

        claim = await create_relay_claim(relay["id"], 230013, method="domain")
        detail = await get_relay_provider_detail(relay["id"])

        assert claim["method"] == "domain"
        assert claim["challenge"]
        assert claim["verification"]["challenge"] == claim["challenge"]
        assert claim["verification"]["expected_text"] == f"tgsellbot-relay-claim={claim['challenge']}"
        assert claim["verification"]["domain_control_required"] is True
        assert "challenge" not in detail["claims"][0]
        assert detail["claims"][0]["verification"]["challenge_required"] is True
        assert detail["claims"][0]["verification"]["challenge_provided"] is True

        with pytest.raises(ValueError):
            await create_relay_claim(relay["id"], 230013, method="shell_access")

    async def test_relay_domain_claim_requires_well_known_proof_before_approval(self, user_factory):
        await user_factory(telegram_id=230014)
        await user_factory(telegram_id=230015)
        relay = await submit_relay_provider(
            {
                "name": "Domain Proof Relay",
                "base_url": "https://domain-proof-relay.example.com/v1",
                "protocol": "openai-compatible",
            },
            submitter_id=230014,
        )
        await review_relay_provider(relay["id"], reviewer_id=230014, status="approved", risk_status="normal")

        claim = await create_relay_claim(relay["id"], 230015, method="domain")
        expected_text = claim["verification"]["expected_text"]
        seen = {}

        async def fake_resolver(hostname):
            seen["hostname"] = hostname
            return ["93.184.216.34"]

        async def missing_fetcher(url):
            seen["missing_url"] = url
            return "not the expected proof"

        with pytest.raises(ValueError, match="domain proof not found"):
            await verify_relay_claim(
                claim["id"],
                reviewer_id=230014,
                approved=True,
                fetcher=missing_fetcher,
                resolver=fake_resolver,
            )

        async def proof_fetcher(url):
            seen["proof_url"] = url
            return f"owner proof\n{expected_text}\n"

        proof = await verify_relay_claim_domain_control(
            type("Claim", (), {"challenge": claim["challenge"]})(),
            type("Provider", (), {
                "public_base_url": "https://domain-proof-relay.example.com/v1",
                "base_url_normalized": "https://domain-proof-relay.example.com/v1",
            })(),
            fetcher=proof_fetcher,
            resolver=fake_resolver,
        )
        ok = await verify_relay_claim(
            claim["id"],
            reviewer_id=230014,
            approved=True,
            fetcher=proof_fetcher,
            resolver=fake_resolver,
        )

        assert proof["ok"] is True
        assert proof["url"] == "https://domain-proof-relay.example.com/.well-known/tgsellbot-relay-claim.txt"
        assert seen["hostname"] == "domain-proof-relay.example.com"
        assert seen["missing_url"] == proof["url"]
        assert seen["proof_url"] == proof["url"]
        assert ok is True

        from bot.database.main import Database
        from bot.database.models.main import RelayClaims, RelayProviders
        from sqlalchemy import select

        async with Database().session() as s:
            stored_claim = (
                await s.execute(select(RelayClaims).where(RelayClaims.id == claim["id"]))
            ).scalars().one()
            provider = (
                await s.execute(select(RelayProviders).where(RelayProviders.id == relay["id"]))
            ).scalars().one()

        assert stored_claim.status == "approved"
        assert provider.owner_user_id == 230015

    async def test_relay_owner_profile_update_keeps_base_url_and_hash_stable(self, user_factory):
        await user_factory(telegram_id=230016)
        await user_factory(telegram_id=230017)
        relay = await submit_relay_provider(
            {
                "name": "Owner Profile Relay",
                "base_url": "https://owner-profile-relay.example.com/v1?debug=1",
                "protocol": "openai-compatible",
                "model_scope": "old scope",
            },
            submitter_id=230016,
        )
        await review_relay_provider(relay["id"], reviewer_id=230016, status="approved", risk_status="normal")
        claim = await create_relay_claim(relay["id"], 230017, method="manual")
        await verify_relay_claim(claim["id"], reviewer_id=230016, approved=True)
        before = await get_relay_provider_detail(relay["id"], user_id=230017)

        with pytest.raises(PermissionError):
            await update_relay_owner_profile(relay["id"], 230016, {"name": "Unauthorized Relay"})

        updated = await update_relay_owner_profile(
            relay["id"],
            230017,
            {
                "name": "Owner Edited Relay",
                "website_url": "https://relay-site.example.com/about?utm_source=owner",
                "protocol": "anthropic-compatible",
                "model_scope": "Claude-compatible endpoints",
                "region": "US",
                "pricing": "published usage tiers",
                "base_url": "https://evil.example.com/v1",
            },
        )
        after = await get_relay_provider_detail(relay["id"], user_id=230017)
        non_owner_after = await get_relay_provider_detail(relay["id"], user_id=230016)

        assert updated["name"] == "Owner Edited Relay"
        assert updated["website_url"] == "https://relay-site.example.com/about"
        assert updated["base_url"] == "https://owner-profile-relay.example.com/v1"
        assert updated["model_scope"] == "Claude-compatible endpoints"
        assert after["provider"]["base_url"] == before["provider"]["base_url"]
        assert after["provider"]["protocol"] == "anthropic-compatible"
        assert after["viewer"]["can_edit_profile"] is True
        assert non_owner_after["viewer"]["can_edit_profile"] is False
        assert "utm_source=owner" not in after["provider"]["website_url"]

    async def test_owner_dashboard_lists_only_owned_resources_with_public_metrics(self, user_factory):
        await user_factory(telegram_id=230030)
        await user_factory(telegram_id=230031)
        await user_factory(telegram_id=230032)

        owned_channel = await submit_channel(
            {
                "channel": "@owner_dashboard_channel",
                "category": "ai",
                "language": "zh",
                "title": "Owner Dashboard Channel",
                "reason": "owner dashboard owned channel",
            },
            submitter_id=230030,
        )
        other_channel = await submit_channel(
            {
                "channel": "@owner_dashboard_other_channel",
                "category": "ai",
                "language": "zh",
                "reason": "other owner channel",
            },
            submitter_id=230032,
        )
        await review_channel_submission(owned_channel["submission"]["id"], reviewer_id=230030, status="approved")
        await review_channel_submission(other_channel["submission"]["id"], reviewer_id=230032, status="approved")
        channel_claim = await create_channel_claim(owned_channel["channel"]["id"], 230031, method="manual")
        other_channel_claim = await create_channel_claim(other_channel["channel"]["id"], 230032, method="manual")
        await verify_channel_claim(channel_claim["id"], reviewer_id=230030, approved=True, notes="internal owner proof")
        await verify_channel_claim(other_channel_claim["id"], reviewer_id=230032, approved=True)
        await record_channel_interaction(230030, owned_channel["channel"]["id"], "favorite", source="mini_app")
        await record_channel_interaction(230032, owned_channel["channel"]["id"], "click", source="mini_app")
        await record_channel_interaction(230032, owned_channel["channel"]["id"], "report", source="mini_app")
        await review_channel_report(
            owned_channel["channel"]["id"],
            reviewer_id=230030,
            risk_status="under_review",
            notes="internal risk dashboard notes",
        )

        owned_relay = await submit_relay_provider(
            {
                "name": "Owner Dashboard Relay",
                "base_url": "https://owner-dashboard-relay.example.com/v1?debug=1",
                "protocol": "openai-compatible",
                "model_scope": "gpt models",
                "region": "SG",
            },
            submitter_id=230030,
        )
        other_relay = await submit_relay_provider(
            {
                "name": "Other Dashboard Relay",
                "base_url": "https://other-dashboard-relay.example.com/v1",
                "protocol": "openai-compatible",
            },
            submitter_id=230032,
        )
        await review_relay_provider(owned_relay["id"], reviewer_id=230030, status="approved", risk_status="normal")
        await review_relay_provider(other_relay["id"], reviewer_id=230032, status="approved", risk_status="normal")
        relay_claim = await create_relay_claim(owned_relay["id"], 230031, method="manual")
        other_relay_claim = await create_relay_claim(other_relay["id"], 230032, method="manual")
        await verify_relay_claim(relay_claim["id"], reviewer_id=230030, approved=True, notes="internal relay proof")
        await verify_relay_claim(other_relay_claim["id"], reviewer_id=230032, approved=True)
        rating = await add_relay_feedback(owned_relay["id"], 230030, "rating", text="works", rating=5)
        complaint = await add_relay_feedback(owned_relay["id"], 230032, "complaint", text="stream timeout")
        await review_relay_feedback(rating["id"], reviewer_id=230030, status="approved", notes="internal rating note")
        await review_relay_feedback(
            complaint["id"],
            reviewer_id=230030,
            status="approved",
            notes="internal complaint note",
            outcome="provider_fixed",
            followup_notes="internal followup",
        )

        dashboard = await owner_dashboard(230031)
        other_dashboard = await owner_dashboard(230032)
        admin_dashboards = await admin_owner_dashboards()

        assert dashboard["owner"]["user_id"] == 230031
        assert dashboard["channels"]["total"] == 1
        assert dashboard["channels"]["items"][0]["channel"]["username"] == "owner_dashboard_channel"
        assert dashboard["channels"]["items"][0]["interactions"]["favorite"] == 1
        assert dashboard["channels"]["items"][0]["interactions"]["click"] == 1
        assert dashboard["channels"]["items"][0]["interactions"]["report"] == 1
        assert dashboard["channels"]["items"][0]["latest_claim"]["status"] == "approved"
        assert dashboard["channels"]["items"][0]["latest_submission"]["status"] == "approved"
        assert dashboard["relays"]["total"] == 1
        assert dashboard["relays"]["items"][0]["provider"]["name"] == "Owner Dashboard Relay"
        assert dashboard["relays"]["items"][0]["provider"]["base_url"] == "https://owner-dashboard-relay.example.com/v1"
        assert dashboard["relays"]["items"][0]["feedback"]["counts"]["rating"] == 1
        assert dashboard["relays"]["items"][0]["feedback"]["counts"]["complaint"] == 1
        assert dashboard["relays"]["items"][0]["feedback"]["average_rating"] == 5.0
        assert dashboard["relays"]["items"][0]["latest_claim"]["status"] == "approved"
        assert other_dashboard["channels"]["items"][0]["channel"]["username"] == "owner_dashboard_other_channel"
        assert other_dashboard["relays"]["items"][0]["provider"]["name"] == "Other Dashboard Relay"
        assert admin_dashboards["total"] >= 2
        owner_rows = {row["owner_id"]: row for row in admin_dashboards["owners"]}
        assert owner_rows[230031]["resource_total"] == 2
        assert owner_rows[230031]["channels"]["total"] == 1
        assert owner_rows[230031]["channels"]["statuses"]["approved"] == 1
        assert owner_rows[230031]["channels"]["risk"]["under_review"] == 1
        assert owner_rows[230031]["channels"]["interactions"]["favorite"] == 1
        assert owner_rows[230031]["relays"]["total"] == 1
        assert owner_rows[230031]["relays"]["statuses"]["approved"] == 1
        assert owner_rows[230031]["relays"]["feedback"]["types"]["complaint"] == 1
        assert owner_rows[230031]["relays"]["feedback"]["average_rating"] == 5.0
        assert owner_rows[230031]["channels"]["recent"][0]["username"] == "owner_dashboard_channel"
        assert owner_rows[230031]["relays"]["recent"][0]["name"] == "Owner Dashboard Relay"

        serialized = str({"owner": dashboard, "admin": admin_dashboards})
        assert channel_claim["challenge"] not in serialized
        assert relay_claim["challenge"] not in serialized
        assert "internal risk dashboard notes" not in serialized
        assert "internal relay proof" not in serialized
        assert "internal followup" not in serialized
        assert "base_url_hash" not in serialized
        assert "base_url_normalized" not in serialized
        assert "debug=1" not in serialized

    async def test_admin_review_workload_metrics_track_assignments_thresholds_and_alerts(self, user_factory):
        await user_factory(telegram_id=230050)
        await user_factory(telegram_id=230051)
        await user_factory(telegram_id=230052)

        for index in range(5):
            submission = await submit_channel(
                {
                    "channel": f"@workload_channel_{index}",
                    "category": "ai",
                    "language": "zh",
                    "reason": "workload channel",
                },
                submitter_id=230050,
            )
            await review_channel_submission(submission["submission"]["id"], reviewer_id=230050, status="approved")
            await record_channel_interaction(230052, submission["channel"]["id"], "report", source="mini_app")
            await review_channel_report(
                submission["channel"]["id"],
                reviewer_id=230050,
                risk_status="under_review",
                notes="internal workload note",
                assigned_to=230051,
                escalation="urgent" if index == 0 else "operator",
            )

        relay = await submit_relay_provider(
            {
                "name": "Workload Relay",
                "base_url": "https://workload-relay.example.com/v1",
                "protocol": "openai-compatible",
            },
            submitter_id=230050,
        )
        await review_relay_provider(relay["id"], reviewer_id=230050, status="approved", risk_status="normal")
        for index in range(5):
            await add_relay_feedback(
                relay["id"],
                user_id=230052,
                feedback_type="complaint",
                text=f"complaint {index}",
            )

        workload = await admin_review_workload_metrics()

        assert workload["summary"]["open_total"] == 10
        assert workload["summary"]["unassigned_total"] == 5
        assert workload["summary"]["urgent_total"] == 1
        assert workload["summary"]["reviewer_count"] == 1
        assert workload["thresholds"]["open_warning_per_reviewer"] == 5
        assert workload["queues"]["channel_reports"]["open_total"] == 5
        assert workload["queues"]["channel_reports"]["by_status"]["under_review"] == 5
        assert workload["queues"]["channel_reports"]["by_escalation"]["urgent"] == 1
        assert workload["queues"]["channel_reports"]["by_escalation"]["operator"] == 4
        assert workload["queues"]["relay_feedback"]["open_total"] == 5
        assert workload["queues"]["relay_feedback"]["unassigned_total"] == 5
        assert workload["queues"]["relay_feedback"]["by_status"]["submitted"] == 5
        assert workload["queues"]["relay_feedback"]["by_feedback_type"]["complaint"] == 5
        reviewer_rows = {row["reviewer_id"]: row for row in workload["reviewers"]}
        assert reviewer_rows[230051]["open_total"] == 5
        assert reviewer_rows[230051]["queues"]["channel_reports"] == 5
        assert reviewer_rows[None]["open_total"] == 5
        assert reviewer_rows[None]["queues"]["relay_feedback"] == 5
        alert_types = {alert["type"] for alert in workload["alerts"]}
        assert {"unassigned_backlog", "urgent_escalation", "reviewer_over_threshold"} <= alert_types
        assert "channels.risk_assigned_to" in workload["coverage"]["assignment_sources"]
        assert "relay_feedback.assigned_to" in workload["coverage"]["assignment_sources"]
        assert "internal workload note" not in str(workload)

    async def test_platform_audit_logs_filter_page_and_redact_sensitive_details(self, user_factory):
        await user_factory(telegram_id=230070)
        await user_factory(telegram_id=230071)

        await log_audit(
            "channel_review",
            user_id=230070,
            resource_type="ChannelSubmission",
            resource_id="sub-1",
            details="status=approved api_key=plain-secret sk-test-audit-secret",
        )
        await log_audit(
            "relay_feedback_review",
            level="WARNING",
            user_id=230071,
            resource_type="RelayFeedback",
            resource_id="fb-1",
            details="Bearer relay-secret token=raw-token complaint followup",
        )
        await log_audit(
            "model_report_visibility",
            user_id=230070,
            resource_type="ModelTestReport",
            resource_id="report-1",
            details="visibility=public",
        )

        channel_logs = await list_platform_audit_logs(action="channel_review")
        relay_logs = await list_platform_audit_logs(level="WARNING", user_id=230071, query="complaint")
        paged = await list_platform_audit_logs(limit=1, offset=0)
        second_page = await list_platform_audit_logs(limit=1, offset=1)

        assert channel_logs["total"] == 1
        assert channel_logs["logs"][0]["action"] == "channel_review"
        assert channel_logs["logs"][0]["user_id"] == 230070
        assert channel_logs["logs"][0]["resource_type"] == "ChannelSubmission"
        assert "plain-secret" not in channel_logs["logs"][0]["details"]
        assert "sk-test-audit-secret" not in channel_logs["logs"][0]["details"]
        assert "api_key=[redacted]" in channel_logs["logs"][0]["details"]
        assert "sk-[redacted]" in channel_logs["logs"][0]["details"]
        assert "ip_address" not in channel_logs["logs"][0]
        assert relay_logs["total"] == 1
        assert relay_logs["logs"][0]["level"] == "WARNING"
        assert relay_logs["logs"][0]["resource_id"] == "fb-1"
        assert "relay-secret" not in relay_logs["logs"][0]["details"]
        assert "raw-token" not in relay_logs["logs"][0]["details"]
        assert relay_logs["filters"]["user_id"] == 230071
        assert paged["total"] == 3
        assert paged["limit"] == 1
        assert paged["has_more"] is True
        assert len(second_page["logs"]) == 1

    async def test_model_test_job_masks_key_and_report_has_limitation(self, user_factory):
        await user_factory(telegram_id=230002)
        job = await create_model_test_job(
            {
                "endpoint": "https://relay.example.com/v1",
                "protocol": "openai-compatible",
                "requested_model": "gpt-4.1",
                "api_key": "sk-test-secret-value",
                "idempotency_key": "job-230002-1",
            },
            user_id=230002,
        )

        assert job["key_fingerprint"] == fingerprint_secret("sk-test-secret-value")
        assert "sk-test-secret-value" not in str(job)
        assert job["key_masked"] == "sk-t...alue"

        duplicate = await create_model_test_job(
            {
                "endpoint": "https://relay.example.com/v1",
                "protocol": "openai-compatible",
                "api_key": "different-key",
                "idempotency_key": "job-230002-1",
            },
            user_id=230002,
        )
        assert duplicate["duplicate"] is True
        assert duplicate["id"] == job["id"]

        report = await create_model_test_report(
            job["id"],
            {
                "declared_model": "gpt-4.1",
                "returned_model": "gpt-4.1",
                "suite_version": "p0-2026-06-17",
                "scores": {"protocol": 1},
                "grade": "B",
                "evidence_json": {"authorization": "Bearer secret", "result": "ok"},
                "visibility": "private",
            },
        )
        assert report["visibility"] == "private"
        assert report["limitation_note"] == MODEL_REPORT_LIMITATION

        loaded_job = await get_model_test_job(job["id"], user_id=230002)
        loaded_report = await get_model_test_report(report["id"], user_id=230002)
        blocked_report = await get_model_test_report(report["id"], user_id=230001)

        assert loaded_job["status"] == "completed"
        assert loaded_job["report"]["id"] == report["id"]
        assert loaded_job["report"]["grade"] == "B"
        assert loaded_report["evidence_json"]["authorization"] != "Bearer secret"
        assert blocked_report is None

        job_list = await list_model_test_jobs(230002)
        report_list = await list_model_test_reports(230002)
        blocked_visibility = await set_report_visibility(report["id"], "public", user_id=230001)
        visibility_ok = await set_report_visibility(report["id"], "unlisted", user_id=230002)
        updated_report = await get_model_test_report(report["id"], user_id=230002)

        assert job_list["total"] == 1
        assert job_list["jobs"][0]["report"]["id"] == report["id"]
        assert report_list["total"] == 1
        assert report_list["reports"][0]["job"]["id"] == job["id"]
        assert blocked_visibility is False
        assert visibility_ok is True
        assert updated_report["visibility"] == "unlisted"

    async def test_model_test_job_claim_complete_and_failure_are_redacted(self, user_factory):
        await user_factory(telegram_id=230003)
        secret = "sk-claim-secret-value"
        job = await create_model_test_job(
            {
                "endpoint": "https://claim-relay.example.com/v1",
                "protocol": "openai-compatible",
                "requested_model": "gpt-claim",
                "api_key": secret,
                "idempotency_key": "job-230003-1",
            },
            user_id=230003,
        )

        with pytest.raises(ValueError):
            await claim_model_test_job(job["id"], "worker-a", "sk-wrong-secret-value")

        task = await claim_model_test_job(job["id"], "worker-a", secret)
        running = await get_model_test_job(job["id"], user_id=230003)

        assert task["api_key"] == secret
        assert task["endpoint"] == "https://claim-relay.example.com/v1"
        assert running["status"] == "running"
        assert running["worker_id"] == "worker-a"
        assert secret not in str(running)

        report = await complete_model_test_job(
            job["id"],
            "worker-a",
            {
                "declared_model": "gpt-claim",
                "returned_model": "gpt-claim",
                "suite_version": "model-lab-test",
                "scores": {"protocol_compatibility": 1},
                "grade": "A",
                "evidence_json": {
                    "nested": {
                        "authorization": f"Bearer {secret}",
                        "raw": secret,
                    }
                },
            },
        )
        loaded_report = await get_model_test_report(report["id"], user_id=230003)
        completed = await get_model_test_job(job["id"], user_id=230003)

        assert completed["status"] == "completed"
        assert secret not in str(loaded_report)
        assert loaded_report["evidence_json"]["nested"]["authorization"] != f"Bearer {secret}"
        assert loaded_report["evidence_json"]["nested"]["raw"] == "[redacted]"

        failed_job = await create_model_test_job(
            {
                "endpoint": "https://failed-relay.example.com/v1",
                "protocol": "openai-compatible",
                "requested_model": "gpt-fail",
                "api_key": secret,
                "idempotency_key": "job-230003-2",
            },
            user_id=230003,
        )
        await claim_model_test_job(failed_job["id"], "worker-b", secret)
        ok = await mark_model_test_job_failed(failed_job["id"], "worker-b", f"failure {secret}")
        failed = await get_model_test_job(failed_job["id"], user_id=230003)

        assert ok is True
        assert failed["status"] == "failed"
        assert secret not in failed["failure_reason"]

    async def test_model_test_dispatcher_runs_once_and_marks_failure(self, user_factory):
        await user_factory(telegram_id=230004)
        secret = "sk-dispatch-secret-value"
        job = await create_model_test_job(
            {
                "endpoint": "https://dispatch-relay.example.com/v1",
                "protocol": "openai-compatible",
                "requested_model": "gpt-dispatch",
                "api_key": secret,
                "idempotency_key": "job-230004-1",
            },
            user_id=230004,
        )
        seen = {}

        async def fake_runner(task):
            seen["task"] = task
            return {
                "declared_model": task["requested_model"],
                "returned_model": task["requested_model"],
                "suite_version": "model-lab-test",
                "scores": {"protocol_compatibility": 1, "observed_behavior": 1},
                "grade": "A",
                "evidence_json": {
                    "credential": {"api_key": task["api_key"]},
                    "suite": [
                        {
                            "name": "models_list",
                            "status": "passed",
                            "metadata": {"status_code": 200, "latency_ms": 10},
                        },
                        {
                            "name": "chat_basic",
                            "status": "passed",
                            "metadata": {
                                "status_code": 200,
                                "latency_ms": 20,
                                "usage": {"total_tokens": 6},
                            },
                        },
                    ],
                },
                "visibility": "private",
                "limitation_note": MODEL_REPORT_LIMITATION,
            }

        result = await run_model_test_job_once(job["id"], secret, worker_id="dispatcher-test", runner=fake_runner)
        loaded_job = await get_model_test_job(job["id"], user_id=230004)
        loaded_report = await get_model_test_report(result["id"], user_id=230004)

        assert seen["task"]["api_key"] == secret
        assert loaded_job["status"] == "completed"
        assert loaded_job["worker_id"] == "dispatcher-test"
        assert secret not in str(loaded_report)
        assert loaded_job["runs"][0]["status"] == "completed"
        assert loaded_job["runs"][0]["worker_id"] == "dispatcher-test"
        assert loaded_report["runs"][0]["status"] == "completed"
        assert loaded_report["runs"][0]["total_tokens"] == 6
        assert secret not in str(loaded_job["runs"])
        assert secret not in str(loaded_report["runs"])
        dashboard = await platform_dashboard_metrics()
        assert dashboard["model_lab"]["runs"]["run_total"] >= 1
        assert dashboard["model_lab"]["latency"]["status"] == "tracked"

        failing = await create_model_test_job(
            {
                "endpoint": "https://dispatch-fail.example.com/v1",
                "protocol": "openai-compatible",
                "requested_model": "gpt-dispatch",
                "api_key": secret,
                "idempotency_key": "job-230004-2",
            },
            user_id=230004,
        )

        async def failing_runner(task):
            raise RuntimeError(f"failed with {task['api_key']}")

        with pytest.raises(RuntimeError):
            await run_model_test_job_once(failing["id"], secret, worker_id="dispatcher-test", runner=failing_runner)
        failed = await get_model_test_job(failing["id"], user_id=230004)

        assert failed["status"] == "failed"
        assert secret not in failed["failure_reason"]
        assert failed["runs"][0]["status"] == "failed"
        assert failed["runs"][0]["error_type"] == "RuntimeError"
        assert secret not in str(failed["runs"])
        failed_dashboard = await platform_dashboard_metrics()
        assert failed_dashboard["model_lab"]["runs"]["statuses"]["failed"] >= 1
        assert secret not in str(failed_dashboard)

    async def test_model_test_drain_uses_ephemeral_key_manifest_and_skips_missing_keys(self, user_factory):
        await user_factory(telegram_id=230005)
        matched_secret = "sk-drain-secret-value"
        missing_secret = "sk-drain-missing-value"
        matched = await create_model_test_job(
            {
                "endpoint": "https://drain-relay.example.com/v1",
                "protocol": "openai-compatible",
                "requested_model": "gpt-drain",
                "api_key": matched_secret,
                "idempotency_key": "job-230005-1",
            },
            user_id=230005,
        )
        missing = await create_model_test_job(
            {
                "endpoint": "https://drain-missing.example.com/v1",
                "protocol": "openai-compatible",
                "requested_model": "gpt-drain-missing",
                "api_key": missing_secret,
                "idempotency_key": "job-230005-2",
            },
            user_id=230005,
        )
        seen = {}

        async def fake_runner(task):
            seen["api_key"] = task["api_key"]
            return {
                "declared_model": task["requested_model"],
                "returned_model": task["requested_model"],
                "suite_version": "model-lab-drain-test",
                "scores": {"protocol_compatibility": 1},
                "grade": "A",
                "evidence_json": {"credential": {"api_key": task["api_key"]}},
                "visibility": "private",
                "limitation_note": MODEL_REPORT_LIMITATION,
            }

        result = await drain_model_test_jobs(
            {"keys": [{"api_key": matched_secret}]},
            worker_id="drain-test",
            limit=10,
            runner=fake_runner,
        )
        matched_job = await get_model_test_job(matched["id"], user_id=230005)
        missing_job = await get_model_test_job(missing["id"], user_id=230005)

        assert result["processed"] == 1
        assert result["missing_key"] == 1
        assert seen["api_key"] == matched_secret
        assert matched_job["status"] == "completed"
        assert missing_job["status"] == "created"
        assert matched_secret not in str(result)
        assert missing_secret not in str(result)
        assert any(item["job_id"] == matched["id"] and item["status"] == "completed" for item in result["results"])
        assert any(item["job_id"] == missing["id"] and item["status"] == "missing_key" for item in result["results"])

    async def test_platform_dashboard_metrics_aggregate_current_foundation_without_fake_unavailable_values(self, user_factory):
        await user_factory(telegram_id=230006)
        invite_link = await get_or_create_group_invite_link(
            230006,
            -1003919149099,
            AsyncMock(return_value="https://t.me/+dashboard"),
        )
        await record_group_invite_join(230007, -1003919149099, invite_link)
        await perform_daily_checkin(230007, reward_amount=1, tickets_per_day=0)
        await reward_group_inviter_after_checkin(230007, -1003919149099, points=1)
        channel = await submit_channel(
            {
                "channel": "@dashboard_channel",
                "category": "ai",
                "language": "zh",
                "reason": "dashboard",
            },
            submitter_id=230006,
        )
        await review_channel_submission(
            channel["submission"]["id"],
            reviewer_id=230006,
            status="approved",
        )
        await record_channel_interaction(230006, channel["channel"]["id"], "favorite", source="test")
        relay = await submit_relay_provider(
            {
                "name": "Dashboard Relay",
                "base_url": "https://dashboard-relay.example.com/v1",
                "protocol": "openai-compatible",
                "model_scope": "gpt",
                "region": "SG",
            },
            submitter_id=230006,
        )
        await review_relay_provider(relay["id"], reviewer_id=230006, status="approved", risk_status="normal")
        feedback = await add_relay_feedback(relay["id"], user_id=230006, feedback_type="rating", text="ok", rating=5)
        await review_relay_feedback(feedback["id"], reviewer_id=230006, status="approved")
        job = await create_model_test_job(
            {
                "endpoint": "https://dashboard-test.example.com/v1",
                "provider_id": relay["id"],
                "protocol": "openai-compatible",
                "requested_model": "gpt-dashboard",
                "api_key": "sk-dashboard-secret",
                "idempotency_key": "job-230006-dashboard",
            },
            user_id=230006,
        )
        await create_model_test_report(
            job["id"],
            {
                "declared_model": "gpt-dashboard",
                "returned_model": "gpt-dashboard",
                "suite_version": "dashboard",
                "scores": {"protocol": 1},
                "grade": "A",
                "evidence_json": {},
                "visibility": "private",
            },
        )
        await create_ledger_entry(230006, "points", "dashboard_bonus", 3, idempotency_key="dashboard-ledger")
        await record_fraud_event("model_test", str(job["id"]), "ssrf_block", {"url": "https://example.com"}, score_delta=1)

        dashboard = await platform_dashboard_metrics()

        assert dashboard["channels"]["submission_total"] >= 1
        assert dashboard["channels"]["interactions"]["favorite"] >= 1
        assert dashboard["relays"]["approved_total"] >= 1
        assert dashboard["relays"]["feedback"]["average_rating"] == 5.0
        assert dashboard["model_lab"]["jobs"]["completed"] >= 1
        assert dashboard["model_lab"]["reports"]["grade"]["A"] >= 1
        assert dashboard["growth"]["ledger_entries"]["points"] >= 1
        assert dashboard["risk"]["ssrf_blocks"] >= 1
        assert dashboard["model_lab"]["average_cost"]["status"] == "unavailable"
        assert dashboard["model_lab"]["latency"]["status"] == "unavailable"
        assert dashboard["relays"]["availability"]["status"] == "unavailable"
        assert dashboard["growth"]["invite_retention"]["status"] == "tracked"
        assert dashboard["growth"]["invite_retention"]["snapshot_total"] >= 1
        assert dashboard["growth"]["invite_retention"]["retention_rate"] == 0.0
        assert dashboard["risk"]["appeals"] == 0
        assert "model_lab.average_cost" in dashboard["coverage"]["unavailable"]

        await record_model_test_run(
            job["id"],
            "dashboard-worker",
            "completed",
            duration_ms=1500,
            report_data={
                "estimated_cost": "0.001200",
                "evidence_json": {
                    "suite": [
                        {"name": "models_list", "status": "passed", "metadata": {"status_code": 200, "latency_ms": 120}},
                        {"name": "chat_basic", "status": "passed", "metadata": {"status_code": 200, "latency_ms": 220}},
                    ]
                },
            },
        )
        await record_relay_availability_sample(
            relay["id"],
            job_id=job["id"],
            status="available",
            http_status=200,
            latency_ms=180,
        )

        with_samples = await platform_dashboard_metrics()

        assert with_samples["model_lab"]["runs"]["run_total"] >= 1
        assert with_samples["model_lab"]["latency"]["status"] == "tracked"
        assert with_samples["model_lab"]["latency"]["sample_count"] >= 1
        assert with_samples["model_lab"]["average_cost"]["status"] == "tracked"
        assert with_samples["model_lab"]["average_cost"]["average_cost"] == "0.001200"
        assert with_samples["relays"]["availability"]["status"] == "tracked"
        assert with_samples["relays"]["availability"]["sample_count"] >= 2
        assert with_samples["relays"]["availability"]["availability_rate"] == 1.0
        assert "model_lab.average_cost" not in with_samples["coverage"]["unavailable"]
        assert "model_lab.latency" not in with_samples["coverage"]["unavailable"]
        assert "relay.availability" not in with_samples["coverage"]["unavailable"]
