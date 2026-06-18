from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _json_default(value: Any) -> str:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _parse_now(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _read_secret(path: str | None) -> str:
    if path:
        return Path(path).read_text(encoding="utf-8").strip()
    if not sys.stdin.isatty():
        return sys.stdin.read().strip()
    raise SystemExit("API key is required on stdin or through --api-key-file.")


def _read_json_secret_manifest(path: str | None) -> dict[str, Any]:
    raw = _read_secret(path)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit("Key manifest must be valid JSON.") from exc
    if not isinstance(payload, dict):
        raise SystemExit("Key manifest must be a JSON object.")
    return payload


async def _run(args: argparse.Namespace) -> dict[str, Any]:
    if args.command == "ledger-opening":
        from bot.database.methods.platform import create_opening_ledger_entries

        return await create_opening_ledger_entries(limit=args.limit, offset=args.offset, dry_run=args.dry_run)
    if args.command == "ledger-reconcile":
        from bot.database.methods.platform import reconcile_ledger_balances

        return await reconcile_ledger_balances(limit=args.limit, offset=args.offset)
    if args.command == "invite-settle":
        from bot.database.methods.group_invites import (
            get_group_invite_reward_tiers_text,
            settle_mature_group_invite_rewards,
        )
        from bot.misc import EnvKeys

        tiers = args.reward_tiers
        if tiers is None:
            tiers = await get_group_invite_reward_tiers_text()
        default_points = args.default_points
        if default_points is None:
            default_points = int(EnvKeys.GROUP_INVITE_REWARD_POINTS or 0)
        return await settle_mature_group_invite_rewards(
            default_points=default_points,
            reward_tiers=tiers,
            now=_parse_now(args.now),
            limit=args.limit,
            max_risk_score=args.max_risk_score,
            chat_id=args.chat_id,
        )
    if args.command == "model-test-run":
        from bot.model_lab.dispatcher import run_model_test_job_once

        api_key = _read_secret(args.api_key_file)
        result = await run_model_test_job_once(
            args.job_id,
            api_key,
            worker_id=args.worker_id,
            process_timeout_seconds=args.process_timeout,
            worker_timeout_seconds=args.worker_timeout,
            max_response_bytes=args.max_response_bytes,
            max_redirects=args.max_redirects,
            max_concurrency=args.max_concurrency,
            max_tokens=args.max_tokens,
        )
        if result is None:
            return {"ok": False, "job_id": args.job_id, "status": "not_found"}
        return {"ok": True, "job_id": args.job_id, "report": result}
    if args.command == "model-test-drain":
        from bot.model_lab.dispatcher import drain_model_test_jobs

        return await drain_model_test_jobs(
            _read_json_secret_manifest(args.key_manifest_file),
            worker_id=args.worker_id,
            limit=args.limit,
            process_timeout_seconds=args.process_timeout,
            worker_timeout_seconds=args.worker_timeout,
            max_response_bytes=args.max_response_bytes,
            max_redirects=args.max_redirects,
            max_concurrency=args.max_concurrency,
            max_tokens=args.max_tokens,
        )
    raise ValueError(f"unknown command: {args.command}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="TGSellBot platform migration and settlement operations.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    opening = subparsers.add_parser("ledger-opening", help="Create idempotent opening ledger entries.")
    opening.add_argument("--limit", type=int, default=1000)
    opening.add_argument("--offset", type=int, default=0)
    opening.add_argument("--dry-run", action="store_true", help="Preview opening entries without writing ledger rows.")

    reconcile = subparsers.add_parser("ledger-reconcile", help="Compare current user fields with available ledger totals.")
    reconcile.add_argument("--limit", type=int, default=1000)
    reconcile.add_argument("--offset", type=int, default=0)

    settle = subparsers.add_parser("invite-settle", help="Credit mature qualified group invite rewards.")
    settle.add_argument("--default-points", type=int, default=None, help="Default points; omit to read GROUP_INVITE_REWARD_POINTS.")
    settle.add_argument("--reward-tiers", default=None, help="Override reward tiers; omit to read bot_settings.")
    settle.add_argument("--now", default=None, help="ISO timestamp for deterministic dry runs/tests.")
    settle.add_argument("--limit", type=int, default=100)
    settle.add_argument("--max-risk-score", type=int, default=0)
    settle.add_argument("--chat-id", default=None)

    model_test = subparsers.add_parser(
        "model-test-run",
        help="Claim one model-test job, run the isolated Worker, and write back a redacted report.",
    )
    model_test.add_argument("job_id", type=int)
    model_test.add_argument("--api-key-file", default=None, help="Read one-time API key from file; omit to read stdin.")
    model_test.add_argument("--worker-id", default="platform-ops")
    model_test.add_argument("--process-timeout", type=float, default=90.0)
    model_test.add_argument("--worker-timeout", type=float, default=20.0)
    model_test.add_argument("--max-response-bytes", type=int, default=256 * 1024)
    model_test.add_argument("--max-redirects", type=int, default=2)
    model_test.add_argument("--max-concurrency", type=int, default=2)
    model_test.add_argument("--max-tokens", type=int, default=64)

    drain = subparsers.add_parser(
        "model-test-drain",
        help="Run claimable model-test jobs using an ephemeral JSON key manifest from stdin or file.",
    )
    drain.add_argument("--key-manifest-file", default=None, help="Read JSON key manifest from file; omit to read stdin.")
    drain.add_argument("--worker-id", default="platform-drain")
    drain.add_argument("--limit", type=int, default=10)
    drain.add_argument("--process-timeout", type=float, default=90.0)
    drain.add_argument("--worker-timeout", type=float, default=20.0)
    drain.add_argument("--max-response-bytes", type=int, default=256 * 1024)
    drain.add_argument("--max-redirects", type=int, default=2)
    drain.add_argument("--max-concurrency", type=int, default=2)
    drain.add_argument("--max-tokens", type=int, default=64)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    result = asyncio.run(_run(args))
    print(json.dumps(result, ensure_ascii=False, default=_json_default, indent=2))


if __name__ == "__main__":
    main()
