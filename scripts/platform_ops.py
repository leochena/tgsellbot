from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit
from urllib.request import Request, urlopen
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env", encoding="utf-8")

TRUTHY = {"1", "true", "yes", "on"}
MINI_APP_PATH = "/platform/app"
AUDITED_COMMANDS = {"model-test-drain", "model-sample-retention"}
EXPECTED_PLATFORM_MENU_TABS = ("channels", "model_lab", "contribute")


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


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in TRUTHY


def evaluate_platform_launch_readiness(
        settings: dict[str, str],
        *,
        smoke: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from bot.misc.url_safety import UnsafeURL, normalize_public_https_url

    raw_url = (settings.get("platform_webapp_url") or "").strip()
    api_enabled = _truthy(settings.get("platform_api_enabled"))
    menu_enabled = _truthy(settings.get("platform_menu_enabled"))
    checks: dict[str, dict[str, Any]] = {}

    checks["platform_webapp_url_present"] = {"ok": bool(raw_url)}
    normalized_url = ""
    public_url = ""
    url_ok = False
    url_error = ""
    if raw_url:
        try:
            safe_url = normalize_public_https_url(raw_url, allow_path=True)
            normalized_url = safe_url.normalized
            public_url = safe_url.public
            url_ok = True
        except UnsafeURL as exc:
            url_error = str(exc)
    checks["platform_webapp_url_public_https"] = {
        "ok": url_ok,
        "normalized": normalized_url,
        "public": public_url,
        "error": url_error,
    }

    path = urlsplit(normalized_url).path if normalized_url else ""
    path_ok = path.rstrip("/") == MINI_APP_PATH if path else False
    checks["platform_webapp_url_path"] = {
        "ok": path_ok,
        "expected": MINI_APP_PATH,
        "actual": path or "",
    }
    menu_markup = _platform_menu_markup_check(normalized_url or raw_url)
    checks["bot_menu_webapp_markup"] = menu_markup
    if smoke is not None:
        checks["platform_webapp_http_smoke"] = smoke

    smoke_ok = True if smoke is None else bool(smoke.get("ok"))
    public_entry_ready = bool(raw_url and url_ok and path_ok and smoke_ok)
    menu_markup_ready = bool(menu_markup.get("ok"))
    checks["platform_api_enabled"] = {"ok": api_enabled, "value": settings.get("platform_api_enabled", "")}
    checks["platform_menu_enabled"] = {"ok": menu_enabled, "value": settings.get("platform_menu_enabled", "")}

    return {
        "ok": public_entry_ready and (not menu_enabled or (api_enabled and menu_markup_ready)),
        "checks": checks,
        "ready": {
            "public_entry": public_entry_ready,
            "can_enable_api": public_entry_ready,
            "can_enable_menu": public_entry_ready and api_enabled and menu_markup_ready,
            "current_launch_live": public_entry_ready and api_enabled and menu_enabled and menu_markup_ready,
        },
        "current": {
            "platform_api_enabled": api_enabled,
            "platform_menu_enabled": menu_enabled,
        },
        "next_actions": _platform_launch_next_actions(
            public_entry_ready=public_entry_ready,
            api_enabled=api_enabled,
            menu_enabled=menu_enabled,
            raw_url=raw_url,
            path_ok=path_ok,
            smoke=smoke,
            menu_markup_ready=menu_markup_ready,
        ),
    }


def _platform_menu_markup_check(platform_webapp_url: str) -> dict[str, Any]:
    if not platform_webapp_url:
        return {
            "ok": False,
            "expected_tabs": list(EXPECTED_PLATFORM_MENU_TABS),
            "tabs": [],
            "web_app_urls": [],
            "fallback_callbacks": [],
            "error": "platform_webapp_url is required.",
        }
    try:
        from bot.keyboards.inline import main_menu

        markup = main_menu(role=1, platform_enabled=True, platform_webapp_url=platform_webapp_url)
        web_app_urls: list[str] = []
        fallback_callbacks: list[str] = []
        for row in markup.inline_keyboard:
            for button in row:
                web_app = getattr(button, "web_app", None)
                if web_app and getattr(web_app, "url", ""):
                    web_app_urls.append(str(web_app.url))
                callback_data = getattr(button, "callback_data", None)
                if callback_data in {"platform_channels", "platform_model_lab", "platform_contribute"}:
                    fallback_callbacks.append(str(callback_data))
    except Exception as exc:
        return {
            "ok": False,
            "expected_tabs": list(EXPECTED_PLATFORM_MENU_TABS),
            "tabs": [],
            "web_app_urls": [],
            "fallback_callbacks": [],
            "error": str(exc),
        }

    tabs: list[str] = []
    paths: list[str] = []
    for url in web_app_urls:
        parts = urlsplit(url)
        paths.append(parts.path)
        query = dict(parse_qsl(parts.query, keep_blank_values=True))
        tab = query.get("tab")
        if tab:
            tabs.append(tab)

    ok = (
        set(EXPECTED_PLATFORM_MENU_TABS).issubset(set(tabs))
        and all(path.rstrip("/") == MINI_APP_PATH for path in paths)
        and not fallback_callbacks
    )
    return {
        "ok": ok,
        "expected_tabs": list(EXPECTED_PLATFORM_MENU_TABS),
        "tabs": tabs,
        "web_app_urls": web_app_urls,
        "fallback_callbacks": fallback_callbacks,
        "error": "",
    }


def _platform_launch_next_actions(
        *,
        public_entry_ready: bool,
        api_enabled: bool,
        menu_enabled: bool,
        raw_url: str,
        path_ok: bool,
        smoke: dict[str, Any] | None,
        menu_markup_ready: bool,
) -> list[str]:
    actions: list[str] = []
    if menu_enabled and not api_enabled:
        actions.append("Disable platform_menu_enabled or enable platform_api_enabled only after public smoke passes.")
    if not raw_url:
        actions.append("Set bot_settings.platform_webapp_url to a public HTTPS /platform/app URL.")
    elif not path_ok:
        actions.append("Use a Mini App URL whose path is /platform/app.")
    if smoke is not None and not smoke.get("ok"):
        actions.append("Fix the public HTTPS reverse proxy before enabling platform_api_enabled.")
    if public_entry_ready and not api_enabled:
        actions.append("Enable bot_settings.platform_api_enabled after public URL smoke passes.")
    if public_entry_ready and api_enabled and not menu_markup_ready:
        actions.append("Fix Bot main-menu WebApp button markup before enabling platform_menu_enabled.")
    if public_entry_ready and api_enabled and menu_markup_ready and not menu_enabled:
        actions.append("Enable bot_settings.platform_menu_enabled after Bot menu smoke passes.")
    if not actions:
        actions.append("Launch checks pass for the current feature-flag state.")
    return actions


def _smoke_platform_webapp(url: str, timeout: float) -> dict[str, Any]:
    if not url:
        return {"ok": False, "status": 0, "error": "URL is required."}
    request = Request(url, headers={"user-agent": "tgsellbot-platform-launch-check/1.0"})
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read(256 * 1024).decode("utf-8", errors="replace")
            status = int(getattr(response, "status", 0) or response.getcode())
    except Exception as exc:  # pragma: no cover - exercised by production smoke, not unit tests.
        return {"ok": False, "status": 0, "error": str(exc)}
    return {
        "ok": status == 200 and "TGSellBot Platform" in body and "telegram-web-app.js" in body,
        "status": status,
        "contains_title": "TGSellBot Platform" in body,
        "contains_telegram_sdk": "telegram-web-app.js" in body,
        "bytes_read": len(body.encode("utf-8")),
    }


async def _platform_launch_settings(url_override: str | None = None) -> dict[str, str]:
    from bot.database.methods.group_invites import get_bot_setting

    return {
        "platform_webapp_url": (url_override if url_override is not None else await get_bot_setting("platform_webapp_url", "")),
        "platform_api_enabled": await get_bot_setting("platform_api_enabled", "0"),
        "platform_menu_enabled": await get_bot_setting("platform_menu_enabled", "0"),
    }


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
            worker_runner=args.worker_runner,
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
            worker_runner=args.worker_runner,
        )
    if args.command == "model-sample-retention":
        from bot.database.methods.platform import prune_model_lab_samples

        return await prune_model_lab_samples(
            run_retention_days=args.run_retention_days,
            availability_retention_days=args.availability_retention_days,
            limit=args.limit,
            dry_run=args.dry_run,
            now=_parse_now(args.now),
        )
    if args.command == "platform-launch-check":
        settings = await _platform_launch_settings(args.url)
        smoke = _smoke_platform_webapp(settings["platform_webapp_url"], args.timeout) if args.smoke else None
        return evaluate_platform_launch_readiness(settings, smoke=smoke)
    raise ValueError(f"unknown command: {args.command}")


async def _run_with_audit(args: argparse.Namespace) -> dict[str, Any]:
    command = str(getattr(args, "command", "") or "")
    try:
        result = await _run(args)
    except Exception as exc:
        if command in AUDITED_COMMANDS:
            await _safe_record_platform_ops_run(
                command,
                {
                    "ok": False,
                    "error_type": exc.__class__.__name__,
                    "error": str(exc),
                },
                ok=False,
                level="ERROR",
            )
        raise

    if command in AUDITED_COMMANDS:
        result_ok = bool(result.get("ok", True)) if isinstance(result, dict) else True
        await _safe_record_platform_ops_run(command, result if isinstance(result, dict) else {"value": result}, ok=result_ok)
    return result


async def _safe_record_platform_ops_run(
        command: str,
        result: dict[str, Any],
        *,
        ok: bool,
        level: str | None = None,
) -> None:
    try:
        await _record_platform_ops_run(command, result, ok=ok, level=level)
    except Exception as exc:  # pragma: no cover - defensive guard for production ops.
        print(f"warning: failed to write platform ops audit event: {exc}", file=sys.stderr)


async def _record_platform_ops_run(
        command: str,
        result: dict[str, Any],
        *,
        ok: bool,
        level: str | None = None,
) -> None:
    from bot.database.methods.platform import record_platform_ops_run

    await record_platform_ops_run(command, result, ok=ok, level=level)


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
    model_test.add_argument("--worker-runner", default=None, help="Executable wrapper for the isolated Worker; receives Worker args and task JSON on stdin.")

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
    drain.add_argument("--worker-runner", default=None, help="Executable wrapper for the isolated Worker; receives Worker args and task JSON on stdin.")

    retention = subparsers.add_parser(
        "model-sample-retention",
        help="Prune old Model Lab run and relay availability samples.",
    )
    retention.add_argument("--run-retention-days", type=int, default=90)
    retention.add_argument("--availability-retention-days", type=int, default=90)
    retention.add_argument("--limit", type=int, default=5000)
    retention.add_argument("--dry-run", action="store_true")
    retention.add_argument("--now", default=None, help="ISO timestamp for deterministic dry runs/tests.")

    launch = subparsers.add_parser(
        "platform-launch-check",
        help="Check whether the Telegram Mini App public URL and feature flags are safe to launch.",
    )
    launch.add_argument("--url", default=None, help="Override bot_settings.platform_webapp_url for a dry-run check.")
    launch.add_argument("--smoke", action="store_true", help="Fetch the public Mini App URL and verify the HTML entrypoint.")
    launch.add_argument("--timeout", type=float, default=5.0, help="HTTP timeout in seconds for --smoke.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    result = asyncio.run(_run_with_audit(args))
    print(json.dumps(result, ensure_ascii=False, default=_json_default, indent=2))


if __name__ == "__main__":
    main()
