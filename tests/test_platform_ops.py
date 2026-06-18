import asyncio
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.platform_ops import (
    _parse_now,
    _run,
    _run_with_audit,
    build_parser,
    evaluate_ledger_cutover_readiness,
    evaluate_platform_launch_readiness,
)
from scripts.platform_worker import build_parser as build_worker_parser


class TestPlatformOpsScript:
    def test_parser_accepts_ledger_commands(self):
        parser = build_parser()

        opening = parser.parse_args(["ledger-opening", "--limit", "50", "--offset", "10", "--dry-run"])
        reconcile = parser.parse_args(["ledger-reconcile"])
        cutover = parser.parse_args(["ledger-cutover-check", "--limit", "5000"])

        assert opening.command == "ledger-opening"
        assert opening.limit == 50
        assert opening.offset == 10
        assert opening.dry_run is True
        assert reconcile.command == "ledger-reconcile"
        assert cutover.command == "ledger-cutover-check"
        assert cutover.limit == 5000
        assert cutover.offset == 0

    def test_ledger_cutover_check_requires_full_clean_reconciliation(self):
        ready = evaluate_ledger_cutover_readiness({
            "checked": 18,
            "mismatch_count": 0,
            "mismatches": [],
            "limit": 5000,
            "offset": 0,
        })
        paged = evaluate_ledger_cutover_readiness({
            "checked": 5000,
            "mismatch_count": 0,
            "mismatches": [],
            "limit": 5000,
            "offset": 0,
        })
        mismatch = evaluate_ledger_cutover_readiness({
            "checked": 18,
            "mismatch_count": 1,
            "mismatches": [{"user_id": 210001}],
            "limit": 5000,
            "offset": 0,
        })

        assert ready["ok"] is True
        assert ready["allow_source_switch"] is True
        assert ready["checks"]["full_reconciliation_scan"]["ok"] is True
        assert ready["checks"]["no_mismatches"]["ok"] is True
        assert ready["rollback_plan"]
        assert "separate release decision" in ready["next_actions"][0]
        assert paged["ok"] is False
        assert paged["checks"]["full_reconciliation_scan"]["ok"] is False
        assert "full reconciliation" in paged["next_actions"][0]
        assert mismatch["ok"] is False
        assert mismatch["checks"]["no_mismatches"]["ok"] is False
        assert "Resolve ledger mismatches" in mismatch["next_actions"][0]

    async def test_ledger_cutover_command_wraps_reconciliation(self, monkeypatch):
        seen = {}

        async def fake_reconcile(*, limit, offset):
            seen["limit"] = limit
            seen["offset"] = offset
            return {
                "checked": 2,
                "mismatch_count": 0,
                "mismatches": [],
                "limit": limit,
                "offset": offset,
            }

        monkeypatch.setattr("bot.database.methods.platform.reconcile_ledger_balances", fake_reconcile)

        result = await _run(SimpleNamespace(command="ledger-cutover-check", limit=5000, offset=0))

        assert seen == {"limit": 5000, "offset": 0}
        assert result["ok"] is True
        assert result["allow_source_switch"] is True
        assert result["reconciliation"]["checked"] == 2

    def test_parser_accepts_invite_settlement(self):
        parser = build_parser()
        args = parser.parse_args([
            "invite-settle",
            "--default-points",
            "3",
            "--reward-tiers",
            "1=1,3=2",
            "--now",
            "2026-06-17T00:00:00+00:00",
            "--max-risk-score",
            "1",
            "--chat-id",
            "-1001",
        ])

        assert args.command == "invite-settle"
        assert args.default_points == 3
        assert args.reward_tiers == "1=1,3=2"
        assert args.max_risk_score == 1
        assert args.chat_id == "-1001"

    def test_parser_accepts_model_test_run_without_key_argument(self):
        parser = build_parser()
        args = parser.parse_args([
            "model-test-run",
            "42",
            "--api-key-file",
            "key.txt",
            "--worker-runner",
            "/usr/local/libexec/tgsellbot/run-isolated-worker.sh",
            "--worker-id",
            "ops-worker",
            "--process-timeout",
            "5",
            "--worker-timeout",
            "3",
            "--max-response-bytes",
            "4096",
            "--max-redirects",
            "1",
            "--max-concurrency",
            "1",
            "--max-tokens",
            "16",
        ])

        assert args.command == "model-test-run"
        assert args.job_id == 42
        assert args.api_key_file == "key.txt"
        assert args.worker_runner == "/usr/local/libexec/tgsellbot/run-isolated-worker.sh"
        assert args.worker_id == "ops-worker"
        assert args.process_timeout == 5
        assert args.worker_timeout == 3
        assert args.max_response_bytes == 4096
        assert args.max_redirects == 1
        assert args.max_concurrency == 1
        assert args.max_tokens == 16

    def test_parser_accepts_model_test_drain_manifest_without_key_argument(self):
        parser = build_parser()
        args = parser.parse_args([
            "model-test-drain",
            "--key-manifest-file",
            "keys.json",
            "--worker-runner",
            "/usr/local/libexec/tgsellbot/run-isolated-worker.sh",
            "--worker-id",
            "drain-worker",
            "--limit",
            "3",
            "--process-timeout",
            "5",
            "--worker-timeout",
            "3",
            "--max-response-bytes",
            "4096",
            "--max-redirects",
            "1",
            "--max-concurrency",
            "1",
            "--max-tokens",
            "16",
        ])

        assert args.command == "model-test-drain"
        assert args.key_manifest_file == "keys.json"
        assert args.worker_runner == "/usr/local/libexec/tgsellbot/run-isolated-worker.sh"
        assert args.worker_id == "drain-worker"
        assert args.limit == 3
        assert args.process_timeout == 5
        assert args.worker_timeout == 3
        assert args.max_response_bytes == 4096
        assert args.max_redirects == 1
        assert args.max_concurrency == 1
        assert args.max_tokens == 16

    def test_parser_accepts_model_sample_retention(self):
        parser = build_parser()
        args = parser.parse_args([
            "model-sample-retention",
            "--run-retention-days",
            "120",
            "--availability-retention-days",
            "45",
            "--limit",
            "250",
            "--dry-run",
            "--now",
            "2026-06-19T00:00:00+00:00",
        ])

        assert args.command == "model-sample-retention"
        assert args.run_retention_days == 120
        assert args.availability_retention_days == 45
        assert args.limit == 250
        assert args.dry_run is True
        assert args.now == "2026-06-19T00:00:00+00:00"

    def test_parser_accepts_platform_launch_check(self):
        parser = build_parser()
        args = parser.parse_args([
            "platform-launch-check",
            "--url",
            "https://example.com/platform/app",
            "--smoke",
            "--timeout",
            "2",
        ])

        assert args.command == "platform-launch-check"
        assert args.url == "https://example.com/platform/app"
        assert args.smoke is True
        assert args.timeout == 2

    def test_platform_launch_check_rejects_missing_or_unsafe_url(self):
        missing = evaluate_platform_launch_readiness({
            "platform_webapp_url": "",
            "platform_api_enabled": "0",
            "platform_menu_enabled": "0",
        })
        local = evaluate_platform_launch_readiness({
            "platform_webapp_url": "http://localhost:9090/platform/app",
            "platform_api_enabled": "0",
            "platform_menu_enabled": "0",
        })

        assert missing["ok"] is False
        assert missing["ready"]["public_entry"] is False
        assert "platform_webapp_url" in missing["next_actions"][0]
        assert local["ok"] is False
        assert local["checks"]["platform_webapp_url_public_https"]["ok"] is False
        assert "HTTPS" in local["checks"]["platform_webapp_url_public_https"]["error"]

    def test_platform_launch_check_requires_platform_app_path_and_api_before_menu(self):
        wrong_path = evaluate_platform_launch_readiness({
            "platform_webapp_url": "https://example.com/not-platform",
            "platform_api_enabled": "1",
            "platform_menu_enabled": "0",
        })
        ready = evaluate_platform_launch_readiness({
            "platform_webapp_url": "https://Example.com/platform/app?source=bot",
            "platform_api_enabled": "1",
            "platform_menu_enabled": "0",
        })
        live = evaluate_platform_launch_readiness({
            "platform_webapp_url": "https://example.com/platform/app",
            "platform_api_enabled": "1",
            "platform_menu_enabled": "1",
        }, smoke={"ok": True, "status": 200})
        unsafe_menu = evaluate_platform_launch_readiness({
            "platform_webapp_url": "https://example.com/platform/app",
            "platform_api_enabled": "0",
            "platform_menu_enabled": "1",
        })

        assert wrong_path["ready"]["public_entry"] is False
        assert wrong_path["checks"]["platform_webapp_url_path"]["actual"] == "/not-platform"
        assert ready["ok"] is True
        assert ready["ready"]["can_enable_api"] is True
        assert ready["ready"]["can_enable_menu"] is True
        assert ready["ready"]["current_launch_live"] is False
        assert ready["checks"]["platform_webapp_url_public_https"]["normalized"] == "https://example.com/platform/app?source=bot"
        assert ready["checks"]["bot_menu_webapp_markup"]["ok"] is True
        assert set(ready["checks"]["bot_menu_webapp_markup"]["tabs"]) == {"channels", "model_lab", "contribute"}
        assert all(
            "/platform/app" in url
            for url in ready["checks"]["bot_menu_webapp_markup"]["web_app_urls"]
        )
        assert live["ok"] is True
        assert live["ready"]["current_launch_live"] is True
        assert live["checks"]["bot_menu_webapp_markup"]["fallback_callbacks"] == []
        assert unsafe_menu["ok"] is False
        assert "Disable platform_menu_enabled" in unsafe_menu["next_actions"][0]

    def test_parse_now_normalizes_naive_datetime_to_utc(self):
        parsed = _parse_now("2026-06-17T00:00:00")

        assert parsed == datetime(2026, 6, 17, tzinfo=timezone.utc)

    def test_audited_model_ops_wrapper_records_success(self, monkeypatch):
        seen = []

        async def fake_run(args):
            return {"ok": True, "processed": 1}

        async def fake_record(command, result, *, ok, level=None):
            seen.append({"command": command, "result": result, "ok": ok, "level": level})

        monkeypatch.setattr("scripts.platform_ops._run", fake_run)
        monkeypatch.setattr("scripts.platform_ops._record_platform_ops_run", fake_record)

        result = asyncio.run(_run_with_audit(SimpleNamespace(command="model-test-drain")))

        assert result == {"ok": True, "processed": 1}
        assert seen == [{
            "command": "model-test-drain",
            "result": {"ok": True, "processed": 1},
            "ok": True,
            "level": None,
        }]

    def test_audited_model_ops_wrapper_records_failure(self, monkeypatch):
        seen = []

        async def fake_run(args):
            raise RuntimeError("boom sk-secret-value")

        async def fake_record(command, result, *, ok, level=None):
            seen.append({"command": command, "result": result, "ok": ok, "level": level})

        monkeypatch.setattr("scripts.platform_ops._run", fake_run)
        monkeypatch.setattr("scripts.platform_ops._record_platform_ops_run", fake_record)

        with pytest.raises(RuntimeError):
            asyncio.run(_run_with_audit(SimpleNamespace(command="model-sample-retention")))

        assert seen == [{
            "command": "model-sample-retention",
            "result": {
                "ok": False,
                "error_type": "RuntimeError",
                "error": "boom sk-secret-value",
            },
            "ok": False,
            "level": "ERROR",
        }]

    def test_audited_model_ops_wrapper_keeps_result_when_audit_write_fails(self, monkeypatch, capsys):
        async def fake_run(args):
            return {"ok": True, "processed": 1}

        async def fake_record(command, result, *, ok, level=None):
            raise RuntimeError("audit db down")

        monkeypatch.setattr("scripts.platform_ops._run", fake_run)
        monkeypatch.setattr("scripts.platform_ops._record_platform_ops_run", fake_record)

        result = asyncio.run(_run_with_audit(SimpleNamespace(command="model-test-drain")))

        assert result == {"ok": True, "processed": 1}
        assert "failed to write platform ops audit event" in capsys.readouterr().err

    def test_invite_settlement_systemd_templates_are_bounded(self):
        root = Path(__file__).resolve().parents[1]
        service = (root / "deploy" / "systemd" / "tgsellbot-invite-settle.service").read_text(encoding="utf-8")
        timer = (root / "deploy" / "systemd" / "tgsellbot-invite-settle.timer").read_text(encoding="utf-8")

        assert "Type=oneshot" in service
        assert "scripts/platform_ops.py invite-settle" in service
        assert "--limit 500" in service
        assert "--max-risk-score 0" in service
        assert "api-key" not in service.lower()
        assert "password" not in service.lower()
        assert "Unit=tgsellbot-invite-settle.service" in timer
        assert "OnUnitActiveSec=1h" in timer
        assert "Persistent=true" in timer

    def test_model_lab_systemd_templates_are_bounded_and_secret_safe(self):
        root = Path(__file__).resolve().parents[1]
        drain_service = (root / "deploy" / "systemd" / "tgsellbot-model-test-drain.service").read_text(encoding="utf-8")
        drain_timer = (root / "deploy" / "systemd" / "tgsellbot-model-test-drain.timer").read_text(encoding="utf-8")
        retention_service = (root / "deploy" / "systemd" / "tgsellbot-model-sample-retention.service").read_text(encoding="utf-8")
        retention_timer = (root / "deploy" / "systemd" / "tgsellbot-model-sample-retention.timer").read_text(encoding="utf-8")
        runner = (root / "deploy" / "model_lab" / "run-isolated-worker.sh").read_text(encoding="utf-8")
        sudoers = (root / "deploy" / "sudoers" / "tgsellbot-model-lab-worker").read_text(encoding="utf-8")

        assert "Type=oneshot" in drain_service
        assert "scripts/platform_ops.py model-test-drain" in drain_service
        assert "ExecCondition=/usr/bin/test -s ${MODEL_TEST_KEY_MANIFEST}" in drain_service
        assert "ExecCondition=/usr/bin/test -x ${MODEL_LAB_WORKER_RUNNER}" in drain_service
        assert "--worker-runner ${MODEL_LAB_WORKER_RUNNER}" in drain_service
        assert "--limit 10" in drain_service
        assert "--max-concurrency 2" in drain_service
        assert "api-key" not in drain_service.lower()
        assert "sk-" not in drain_service.lower()
        assert "bearer" not in drain_service.lower()
        assert "Unit=tgsellbot-model-test-drain.service" in drain_timer
        assert "OnUnitActiveSec=5min" in drain_timer
        assert "Persistent=false" in drain_timer
        assert "scripts/platform_ops.py model-sample-retention" in retention_service
        assert "--run-retention-days 90" in retention_service
        assert "--availability-retention-days 90" in retention_service
        assert "--limit 5000" in retention_service
        assert "Unit=tgsellbot-model-sample-retention.service" in retention_timer
        assert "OnUnitActiveSec=1d" in retention_timer
        assert "Persistent=true" in retention_timer
        assert "sudo" in runner
        assert "tgsellbot-worker" in runner
        assert "env -i" in runner
        assert "PYTHONPATH=\"$APP_DIR\"" in runner
        assert "platform_worker.py" in runner
        assert "POSTGRES" not in runner
        assert "TOKEN" not in runner
        assert "NOPASSWD" in sudoers
        assert "tgsellbot-worker" in sudoers
        assert "/usr/local/libexec/tgsellbot/run-isolated-worker.sh" in sudoers


class TestPlatformWorkerScript:
    def test_parser_accepts_worker_limits_without_env(self):
        parser = build_worker_parser()
        args = parser.parse_args([
            "--input",
            "task.json",
            "--timeout",
            "3",
            "--max-response-bytes",
            "2048",
            "--max-redirects",
            "1",
            "--max-concurrency",
            "1",
            "--max-tokens",
            "12",
        ])

        assert args.input == "task.json"
        assert args.timeout == 3
        assert args.max_response_bytes == 2048
        assert args.max_redirects == 1
        assert args.max_concurrency == 1
        assert args.max_tokens == 12
