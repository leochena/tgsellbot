from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import socket
import ssl
import subprocess
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
CERT_DATE_FORMAT = "%b %d %H:%M:%S %Y %Z"
DEFAULT_MODEL_TEST_KEY_MANIFEST = "/etc/tgsellbot/model-test-keys.json"
DEFAULT_MODEL_LAB_WORKER_RUNNER = "/usr/local/libexec/tgsellbot/run-isolated-worker.sh"
DEFAULT_MODEL_TEST_DRAIN_TIMER = "tgsellbot-model-test-drain.timer"
LEDGER_CUTOVER_ROLLBACK_PLAN = [
    "Keep users.balance and users.points_balance as the read source until a separate release explicitly switches reads.",
    "If a future switch misbehaves, route reads back to users.balance/users.points_balance and leave ledger rows append-only.",
    "Run ledger-reconcile after rollback; correct drift with audited compensating ledger entries, not destructive edits.",
]
LEDGER_CUTOVER_CORRECTION_PLAN = [
    "Repeat ledger-opening --dry-run on a production-like copy and inspect the preview.",
    "Run ledger-opening on the approved copy or release window, then repeat ledger-reconcile.",
    "Investigate remaining mismatches per user/account and apply audited correction entries before any read-source switch.",
]
SHA256_HEX_RE = re.compile(r"^[0-9a-f]{64}$")


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


def evaluate_platform_certificate_readiness(
        target: dict[str, Any],
        certificate: dict[str, Any] | None,
        *,
        certbot: dict[str, Any] | None = None,
        systemd_timers: dict[str, Any] | None = None,
        min_valid_days: int = 21,
) -> dict[str, Any]:
    target_ok = bool(target.get("ok"))
    certificate = certificate or {"ok": False, "error": "certificate probe was not run."}
    cert_days = int(certificate.get("days_remaining") or 0)
    certificate_ok = bool(certificate.get("ok")) and cert_days >= int(min_valid_days)
    certbot_ok = True if certbot is None else bool(certbot.get("ok"))
    timers_ok = True if systemd_timers is None else bool(systemd_timers.get("ok"))

    next_actions: list[str] = []
    if not target_ok:
        next_actions.append("Set platform_webapp_url to a public HTTPS /platform/app URL before certificate checks.")
    if not certificate.get("ok"):
        next_actions.append("Fix the public TLS certificate or nginx HTTPS entry before launch.")
    elif cert_days < int(min_valid_days):
        next_actions.append(
            f"Renew the public TLS certificate; only {cert_days} days remain and the minimum is {int(min_valid_days)}."
        )
    if certbot is not None and not certbot_ok:
        next_actions.append("Fix certbot certificate inventory for the Mini App domain on the server.")
    if systemd_timers is not None and not timers_ok:
        next_actions.append("Enable or repair the certbot renewal timer on the server.")
    if not next_actions:
        next_actions.append("Certificate and renewal checks pass for the Mini App public entry.")

    return {
        "ok": target_ok and certificate_ok and certbot_ok and timers_ok,
        "target": {
            "url": target.get("url", ""),
            "host": target.get("host", ""),
            "port": target.get("port", 443),
            "error": target.get("error", ""),
        },
        "checks": {
            "public_tls_certificate": {
                **certificate,
                "ok": certificate_ok,
                "minimum_valid_days": int(min_valid_days),
            },
            "certbot_certificate_inventory": certbot if certbot is not None else {"ok": True, "skipped": True},
            "certbot_renewal_timer": systemd_timers if systemd_timers is not None else {"ok": True, "skipped": True},
        },
        "next_actions": next_actions,
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


def evaluate_ledger_cutover_readiness(reconciliation: dict[str, Any]) -> dict[str, Any]:
    checked = int(reconciliation.get("checked") or 0)
    limit = int(reconciliation.get("limit") or 0)
    offset = int(reconciliation.get("offset") or 0)
    mismatch_count = int(reconciliation.get("mismatch_count") or 0)
    full_scan = offset == 0 and limit > 0 and checked < limit
    no_mismatches = mismatch_count == 0
    allow_source_switch = full_scan and no_mismatches

    next_actions: list[str] = []
    if not full_scan:
        next_actions.append(
            "Run a full reconciliation from offset 0 with a limit above the active user count before any source switch."
        )
    if not no_mismatches:
        next_actions.append(
            "Resolve ledger mismatches and rerun ledger-cutover-check until mismatch_count is 0."
        )
    if allow_source_switch:
        next_actions.append(
            "Ledger totals reconcile for this full scan; a separate release decision can switch read paths with the rollback plan attached."
        )

    return {
        "ok": allow_source_switch,
        "allow_source_switch": allow_source_switch,
        "current_read_source": "users.balance/users.points_balance",
        "candidate_read_source": "ledger_entries available totals",
        "checks": {
            "full_reconciliation_scan": {
                "ok": full_scan,
                "checked": checked,
                "limit": limit,
                "offset": offset,
            },
            "no_mismatches": {
                "ok": no_mismatches,
                "mismatch_count": mismatch_count,
            },
        },
        "reconciliation": reconciliation,
        "next_actions": next_actions,
        "rollback_plan": list(LEDGER_CUTOVER_ROLLBACK_PLAN),
        "correction_plan": list(LEDGER_CUTOVER_CORRECTION_PLAN),
    }


def evaluate_model_key_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    from bot.misc.url_safety import fingerprint_secret, mask_secret
    from bot.model_lab.dispatcher import _key_manifest_to_fingerprints

    try:
        mapping = _key_manifest_to_fingerprints(manifest)
    except ValueError as exc:
        return {
            "ok": False,
            "key_count": 0,
            "unique_fingerprint_count": 0,
            "duplicate_fingerprint_count": 0,
            "keys": [],
            "error": str(exc),
            "next_actions": ["Fix the server-local Model Lab key manifest before enabling the drain timer."],
        }

    entries = _collect_model_key_manifest_entries(manifest)
    duplicate_count = max(0, len(entries) - len(mapping))
    safe_keys = [
        {
            "fingerprint": _safe_fingerprint_for_output(fingerprint),
            "fingerprint_format": "sha256" if SHA256_HEX_RE.match(fingerprint) else "custom_masked",
            "fingerprint_hash": fingerprint_secret(fingerprint),
            "key_masked": mask_secret(api_key),
        }
        for fingerprint, api_key in sorted(mapping.items())
    ]

    next_actions = [
        "Keep the manifest server-local and unreadable by the isolated worker user.",
        "Run model-test-drain manually with approval before enabling tgsellbot-model-test-drain.timer.",
    ]
    if duplicate_count:
        next_actions.insert(0, "Remove duplicate manifest fingerprints so each API key maps to one claimable key fingerprint.")

    return {
        "ok": duplicate_count == 0,
        "key_count": len(entries),
        "unique_fingerprint_count": len(mapping),
        "duplicate_fingerprint_count": duplicate_count,
        "keys": safe_keys,
        "next_actions": next_actions,
    }


def evaluate_model_drain_readiness(
        runner: dict[str, Any],
        manifest: dict[str, Any],
        timer: dict[str, Any],
) -> dict[str, Any]:
    runner_ok = bool(runner.get("ok"))
    manifest_ok = bool(manifest.get("ok"))
    timer_ok = bool(timer.get("ok"))
    timer_installed = bool(timer.get("installed"))
    timer_active = bool(timer.get("active"))
    timer_enabled = bool(timer.get("enabled"))

    ready_for_manual_drain = runner_ok and manifest_ok
    ready_for_timer_enablement = ready_for_manual_drain and timer_ok and timer_installed and not timer_active
    scheduled_drain_live = ready_for_manual_drain and timer_ok and timer_installed and timer_enabled and timer_active

    next_actions: list[str] = []
    if not runner_ok:
        next_actions.append("Install and verify the root-owned isolated Worker runner before any batch drain.")
    if not manifest_ok:
        next_actions.append("Install a server-local 0600 Model Lab key manifest and rerun the readiness check.")
    if not timer_ok or not timer_installed:
        next_actions.append("Install the tgsellbot-model-test-drain systemd service/timer before scheduling drains.")
    if ready_for_timer_enablement:
        next_actions.append("Run an approved manual model-test-drain before enabling the drain timer.")
    if scheduled_drain_live:
        next_actions.append("Scheduled Model Lab drain appears live; monitor redacted Model ops dashboard readouts.")
    if ready_for_manual_drain and timer_ok and timer_installed and timer_active and not timer_enabled:
        next_actions.append("Investigate the active drain timer because systemd reports it active but not enabled.")

    return {
        "ok": ready_for_manual_drain and timer_ok and timer_installed,
        "ready": {
            "manual_drain": ready_for_manual_drain,
            "timer_enablement": ready_for_timer_enablement,
            "scheduled_drain_live": scheduled_drain_live,
        },
        "checks": {
            "isolated_worker_runner": runner,
            "server_local_key_manifest": manifest,
            "model_test_drain_timer": timer,
        },
        "next_actions": next_actions,
    }


def _model_lab_runner_check(path: str) -> dict[str, Any]:
    return _local_file_check(path, require_executable=True, require_root_owner=True)


def _model_lab_manifest_check(path: str) -> dict[str, Any]:
    file_check = _local_file_check(path, require_non_empty=True, require_secret_permissions=True)
    manifest_check: dict[str, Any] = {
        "ok": False,
        "skipped": True,
        "error": "manifest file was not read because the file check failed.",
    }
    if file_check.get("exists") and file_check.get("is_file") and file_check.get("non_empty"):
        try:
            manifest_check = evaluate_model_key_manifest(_read_json_secret_manifest(path))
        except SystemExit as exc:
            manifest_check = {
                "ok": False,
                "key_count": 0,
                "unique_fingerprint_count": 0,
                "duplicate_fingerprint_count": 0,
                "keys": [],
                "error": str(exc),
                "next_actions": ["Fix the server-local Model Lab key manifest before enabling the drain timer."],
            }
    return {
        **file_check,
        "manifest": manifest_check,
        "ok": bool(file_check.get("ok")) and bool(manifest_check.get("ok")),
    }


def _local_file_check(
        path: str,
        *,
        require_non_empty: bool = False,
        require_executable: bool = False,
        require_root_owner: bool = False,
        require_secret_permissions: bool = False,
) -> dict[str, Any]:
    target = Path(path)
    result: dict[str, Any] = {
        "ok": False,
        "path": str(target),
        "exists": False,
        "is_file": False,
        "non_empty": False,
        "executable": False,
        "mode": "",
        "owner_uid": None,
        "root_owner": False,
        "secret_permissions": False,
        "posix_checks_skipped": os.name != "posix",
        "error": "",
    }
    try:
        stat_result = target.stat()
    except FileNotFoundError:
        result["error"] = "file does not exist."
        return result
    except OSError as exc:
        result["error"] = str(exc)
        return result

    is_file = target.is_file()
    mode = stat_result.st_mode & 0o777
    non_empty = stat_result.st_size > 0
    executable = os.access(target, os.X_OK)
    root_owner = os.name != "posix" or getattr(stat_result, "st_uid", None) == 0
    secret_permissions = os.name != "posix" or (mode & 0o077) == 0

    errors: list[str] = []
    if not is_file:
        errors.append("path is not a file")
    if require_non_empty and not non_empty:
        errors.append("file is empty")
    if require_executable and not executable:
        errors.append("file is not executable")
    if require_root_owner and not root_owner:
        errors.append("file is not owned by root")
    if require_secret_permissions and not secret_permissions:
        errors.append("secret file must not be group/world readable or executable")

    result.update({
        "exists": True,
        "is_file": is_file,
        "non_empty": non_empty,
        "executable": executable,
        "mode": f"{mode:04o}",
        "owner_uid": getattr(stat_result, "st_uid", None),
        "root_owner": root_owner,
        "secret_permissions": secret_permissions,
        "ok": not errors,
        "error": "; ".join(errors),
    })
    return result


def _run_systemd_unit_state(unit_name: str, timeout: float) -> dict[str, Any]:
    enabled = _run_read_only_command(["systemctl", "is-enabled", unit_name], timeout=timeout)
    active = _run_read_only_command(["systemctl", "is-active", unit_name], timeout=timeout)
    enabled_state = _systemctl_state_output(enabled)
    active_state = _systemctl_state_output(active)
    systemctl_available = enabled["returncode"] != 127 and active["returncode"] != 127
    combined_output = " ".join([
        str(enabled.get("stdout") or ""),
        str(enabled.get("stderr") or ""),
        str(active.get("stdout") or ""),
        str(active.get("stderr") or ""),
    ]).lower()
    not_found = any(token in combined_output for token in (
        "not-found",
        "not found",
        "could not be found",
        "does not exist",
        "no such file",
    ))
    installed = systemctl_available and not not_found and enabled_state not in {"", "not-found"}
    query_ok = systemctl_available and installed

    return {
        "ok": query_ok,
        "unit": unit_name,
        "installed": installed,
        "enabled": enabled_state in {"enabled", "enabled-runtime", "linked", "linked-runtime"},
        "active": active_state == "active",
        "enabled_state": enabled_state,
        "active_state": active_state,
        "enabled_returncode": enabled["returncode"],
        "active_returncode": active["returncode"],
        "error": "" if query_ok else (enabled["error"] or active["error"] or "systemd unit was not found."),
    }


def _systemctl_state_output(completed: dict[str, Any]) -> str:
    output = str(completed.get("stdout") or completed.get("stderr") or "").strip().splitlines()
    if not output:
        return ""
    return output[0].strip().split()[0]


def _collect_model_key_manifest_entries(manifest: dict[str, Any]) -> list[tuple[str, str]]:
    from bot.misc.url_safety import fingerprint_secret

    items = manifest.get("keys", manifest) if isinstance(manifest, dict) else {}
    entries: list[tuple[str, str]] = []
    if isinstance(items, list):
        for item in items:
            if not isinstance(item, dict):
                continue
            api_key = str(item.get("api_key") or item.get("key") or "").strip()
            fingerprint = str(item.get("fingerprint") or fingerprint_secret(api_key)).strip()
            if api_key and fingerprint:
                entries.append((fingerprint, api_key))
    elif isinstance(items, dict):
        for raw_fingerprint, raw_key in items.items():
            api_key = str(raw_key or "").strip()
            fingerprint = str(raw_fingerprint or fingerprint_secret(api_key)).strip()
            if api_key and fingerprint:
                entries.append((fingerprint, api_key))
    return entries


def _safe_fingerprint_for_output(fingerprint: str) -> str:
    from bot.misc.url_safety import mask_secret

    value = str(fingerprint or "").strip()
    if SHA256_HEX_RE.match(value):
        return value
    return mask_secret(value)


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


def _platform_certificate_target_from_url(url: str) -> dict[str, Any]:
    from bot.misc.url_safety import UnsafeURL, normalize_public_https_url

    if not url:
        return {"ok": False, "url": "", "host": "", "port": 443, "error": "platform_webapp_url is required."}
    try:
        safe_url = normalize_public_https_url(url, allow_path=True)
    except UnsafeURL as exc:
        return {"ok": False, "url": url, "host": "", "port": 443, "error": str(exc)}
    parts = urlsplit(safe_url.normalized)
    host = parts.hostname or ""
    return {
        "ok": bool(host),
        "url": safe_url.normalized,
        "host": host,
        "port": int(parts.port or 443),
        "error": "" if host else "URL host is required.",
    }


def _probe_https_certificate(host: str, port: int, timeout: float, *, now: datetime | None = None) -> dict[str, Any]:
    if not host:
        return {"ok": False, "host": "", "port": port, "error": "host is required."}
    now = now or datetime.now(timezone.utc)
    try:
        context = ssl.create_default_context()
        with socket.create_connection((host, int(port)), timeout=timeout) as sock:
            with context.wrap_socket(sock, server_hostname=host) as tls:
                cert = tls.getpeercert()
        not_after_raw = str(cert.get("notAfter") or "")
        expires_at = datetime.strptime(not_after_raw, CERT_DATE_FORMAT).replace(tzinfo=timezone.utc)
    except Exception as exc:  # pragma: no cover - exercised by production smoke, not unit tests.
        return {"ok": False, "host": host, "port": int(port), "error": str(exc)}

    seconds_remaining = int((expires_at - now).total_seconds())
    subject_alt_names = [
        str(value)
        for key, value in cert.get("subjectAltName", ())
        if key == "DNS"
    ]
    return {
        "ok": seconds_remaining > 0,
        "host": host,
        "port": int(port),
        "not_after": expires_at.isoformat(),
        "days_remaining": seconds_remaining // 86400,
        "subject_common_name": _certificate_name_value(cert.get("subject", ()), "commonName"),
        "issuer_common_name": _certificate_name_value(cert.get("issuer", ()), "commonName"),
        "subject_alt_names": subject_alt_names,
        "error": "",
    }


def _certificate_name_value(name: Any, key: str) -> str:
    for group in name or ():
        for item_key, value in group:
            if item_key == key:
                return str(value)
    return ""


def _run_certbot_certificate_check(domain: str, timeout: float) -> dict[str, Any]:
    command = ["certbot", "certificates", "-d", domain]
    completed = _run_read_only_command(command, timeout=timeout)
    if completed["returncode"] != 0:
        return {
            "ok": False,
            "domain": domain,
            "domain_found": False,
            "domains": [],
            "expiry": "",
            "returncode": completed["returncode"],
            "error": completed["error"] or "certbot certificates failed.",
        }

    lines = completed["stdout"].splitlines()
    domains: list[str] = []
    expiry = ""
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("Domains:"):
            domains.extend(stripped.split(":", 1)[1].split())
        elif stripped.startswith("Expiry Date:"):
            expiry = stripped.split(":", 1)[1].strip()
    domain_found = domain in domains
    return {
        "ok": domain_found,
        "domain": domain,
        "domain_found": domain_found,
        "domains": domains,
        "expiry": expiry,
        "returncode": completed["returncode"],
        "error": "" if domain_found else "certbot did not report the Mini App domain.",
    }


def _run_certbot_timer_check(timeout: float) -> dict[str, Any]:
    completed = _run_read_only_command(
        ["systemctl", "list-timers", "certbot*", "snap.certbot*", "--all", "--no-pager"],
        timeout=timeout,
    )
    if completed["returncode"] != 0:
        return {
            "ok": False,
            "timer_count": 0,
            "timers": [],
            "returncode": completed["returncode"],
            "error": completed["error"] or "systemctl list-timers failed.",
        }

    timers = [
        line.strip()[:240]
        for line in completed["stdout"].splitlines()
        if "certbot" in line.lower() and ".timer" in line
    ]
    return {
        "ok": bool(timers),
        "timer_count": len(timers),
        "timers": timers,
        "returncode": completed["returncode"],
        "error": "" if timers else "No certbot renewal timer was listed.",
    }


def _run_read_only_command(command: list[str], *, timeout: float) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        return {"returncode": 127, "stdout": "", "stderr": "", "error": str(exc)}
    except subprocess.TimeoutExpired:
        return {"returncode": 124, "stdout": "", "stderr": "", "error": f"Command timed out after {timeout} seconds."}
    stderr = (completed.stderr or "").strip().replace("\n", " ")[:500]
    return {
        "returncode": int(completed.returncode),
        "stdout": completed.stdout or "",
        "stderr": stderr,
        "error": stderr if completed.returncode else "",
    }


async def _platform_certificate_url(url_override: str | None = None) -> str:
    if url_override is not None:
        return url_override
    from bot.database.methods.group_invites import get_bot_setting

    return await get_bot_setting("platform_webapp_url", "")


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
    if args.command == "ledger-cutover-check":
        from bot.database.methods.platform import reconcile_ledger_balances

        reconciliation = await reconcile_ledger_balances(limit=args.limit, offset=args.offset)
        return evaluate_ledger_cutover_readiness(reconciliation)
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
    if args.command == "model-key-manifest-check":
        return evaluate_model_key_manifest(_read_json_secret_manifest(args.key_manifest_file))
    if args.command == "model-drain-readiness-check":
        return evaluate_model_drain_readiness(
            _model_lab_runner_check(args.worker_runner),
            _model_lab_manifest_check(args.key_manifest_file),
            _run_systemd_unit_state(args.timer_name, args.timeout),
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
    if args.command == "platform-cert-check":
        url = await _platform_certificate_url(args.url)
        target = _platform_certificate_target_from_url(url)
        certificate = None
        certbot = None
        systemd_timers = None
        if target.get("ok"):
            certificate = _probe_https_certificate(target["host"], target["port"], args.timeout)
            if args.certbot:
                certbot = _run_certbot_certificate_check(target["host"], args.timeout)
            if args.systemd_timers:
                systemd_timers = _run_certbot_timer_check(args.timeout)
        return evaluate_platform_certificate_readiness(
            target,
            certificate,
            certbot=certbot,
            systemd_timers=systemd_timers,
            min_valid_days=args.min_valid_days,
        )
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

    cutover = subparsers.add_parser("ledger-cutover-check", help="Read-only gate for a future ledger source-of-truth switch.")
    cutover.add_argument("--limit", type=int, default=5000)
    cutover.add_argument("--offset", type=int, default=0)

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

    manifest_check = subparsers.add_parser(
        "model-key-manifest-check",
        help="Validate an ephemeral Model Lab key manifest without printing raw keys.",
    )
    manifest_check.add_argument("--key-manifest-file", default=None, help="Read JSON key manifest from file; omit to read stdin.")

    drain_readiness = subparsers.add_parser(
        "model-drain-readiness-check",
        help="Read-only gate for Model Lab drain runner, server-local key manifest, and systemd timer wiring.",
    )
    drain_readiness.add_argument(
        "--key-manifest-file",
        default=DEFAULT_MODEL_TEST_KEY_MANIFEST,
        help="Server-local JSON key manifest path to validate without printing raw keys.",
    )
    drain_readiness.add_argument(
        "--worker-runner",
        default=DEFAULT_MODEL_LAB_WORKER_RUNNER,
        help="Root-owned executable wrapper for the isolated Worker.",
    )
    drain_readiness.add_argument(
        "--timer-name",
        default=DEFAULT_MODEL_TEST_DRAIN_TIMER,
        help="Systemd timer unit that schedules model-test-drain.",
    )
    drain_readiness.add_argument("--timeout", type=float, default=5.0, help="Read-only systemctl timeout in seconds.")

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

    cert = subparsers.add_parser(
        "platform-cert-check",
        help="Check the Mini App public TLS certificate and optional certbot renewal wiring.",
    )
    cert.add_argument("--url", default=None, help="Override bot_settings.platform_webapp_url for a dry-run check.")
    cert.add_argument("--min-valid-days", type=int, default=21, help="Minimum acceptable TLS certificate days remaining.")
    cert.add_argument("--timeout", type=float, default=5.0, help="Network or command timeout in seconds.")
    cert.add_argument("--certbot", action="store_true", help="Also run certbot certificates -d <host> and summarize it.")
    cert.add_argument("--systemd-timers", action="store_true", help="Also verify a certbot renewal timer is listed by systemd.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    result = asyncio.run(_run_with_audit(args))
    print(json.dumps(result, ensure_ascii=False, default=_json_default, indent=2))


if __name__ == "__main__":
    main()
