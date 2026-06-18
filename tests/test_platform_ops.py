from datetime import datetime, timezone
from pathlib import Path

from scripts.platform_ops import _parse_now, build_parser
from scripts.platform_worker import build_parser as build_worker_parser


class TestPlatformOpsScript:
    def test_parser_accepts_ledger_commands(self):
        parser = build_parser()

        opening = parser.parse_args(["ledger-opening", "--limit", "50", "--offset", "10", "--dry-run"])
        reconcile = parser.parse_args(["ledger-reconcile"])

        assert opening.command == "ledger-opening"
        assert opening.limit == 50
        assert opening.offset == 10
        assert opening.dry_run is True
        assert reconcile.command == "ledger-reconcile"

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
        assert args.worker_id == "drain-worker"
        assert args.limit == 3
        assert args.process_timeout == 5
        assert args.worker_timeout == 3
        assert args.max_response_bytes == 4096
        assert args.max_redirects == 1
        assert args.max_concurrency == 1
        assert args.max_tokens == 16

    def test_parse_now_normalizes_naive_datetime_to_utc(self):
        parsed = _parse_now("2026-06-17T00:00:00")

        assert parsed == datetime(2026, 6, 17, tzinfo=timezone.utc)

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
