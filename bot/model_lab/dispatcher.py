from __future__ import annotations

import asyncio
import inspect
import json
import logging
import re
import sys
import time
from pathlib import Path
from typing import Any, Awaitable, Callable

from bot.misc.url_safety import fingerprint_secret, mask_secret


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_WORKER_SCRIPT = ROOT / "scripts" / "platform_worker.py"
logger = logging.getLogger(__name__)

WorkerRunner = Callable[[dict[str, Any]], Awaitable[dict[str, Any]] | dict[str, Any]]


async def run_model_test_job_once(
        job_id: int,
        api_key: str,
        *,
        worker_id: str = "model-lab-dispatcher",
        runner: WorkerRunner | None = None,
        process_timeout_seconds: float = 90.0,
        worker_timeout_seconds: float = 20.0,
        max_response_bytes: int = 256 * 1024,
        max_redirects: int = 2,
        max_concurrency: int = 2,
        max_tokens: int = 64,
) -> dict[str, Any] | None:
    from bot.database.methods.platform import (
        claim_model_test_job,
        complete_model_test_job,
        mark_model_test_job_failed,
        record_model_test_run,
    )

    task = await claim_model_test_job(int(job_id), worker_id, api_key)
    if not task:
        return None

    started = time.monotonic()
    try:
        if runner is not None:
            report = runner(task)
            if inspect.isawaitable(report):
                report = await report
        else:
            report = await run_worker_subprocess(
                task,
                process_timeout_seconds=process_timeout_seconds,
                worker_timeout_seconds=worker_timeout_seconds,
                max_response_bytes=max_response_bytes,
                max_redirects=max_redirects,
                max_concurrency=max_concurrency,
                max_tokens=max_tokens,
            )
        if not isinstance(report, dict):
            raise RuntimeError("Worker returned a non-object report.")
        result = await complete_model_test_job(int(job_id), worker_id, report)
        try:
            await record_model_test_run(
                int(job_id),
                worker_id,
                "completed",
                duration_ms=int((time.monotonic() - started) * 1000),
                report_data=report,
            )
        except Exception:
            logger.exception("Failed to record completed model-test run metrics")
        return result
    except Exception as exc:
        safe_reason = _redact_text(f"{exc.__class__.__name__}: {exc}", api_key)[:255]
        await mark_model_test_job_failed(int(job_id), worker_id, safe_reason)
        await record_model_test_run(
            int(job_id),
            worker_id,
            "failed",
            duration_ms=int((time.monotonic() - started) * 1000),
            error_type=exc.__class__.__name__,
            error_summary=safe_reason,
        )
        raise


async def drain_model_test_jobs(
        key_manifest: dict[str, Any],
        *,
        worker_id: str = "model-lab-drain",
        limit: int = 10,
        runner: WorkerRunner | None = None,
        process_timeout_seconds: float = 90.0,
        worker_timeout_seconds: float = 20.0,
        max_response_bytes: int = 256 * 1024,
        max_redirects: int = 2,
        max_concurrency: int = 2,
        max_tokens: int = 64,
) -> dict[str, Any]:
    from bot.database.methods.platform import list_claimable_model_test_jobs

    limit = min(max(int(limit or 10), 1), 100)
    secrets_by_fingerprint = _key_manifest_to_fingerprints(key_manifest)
    claimable = await list_claimable_model_test_jobs(limit=limit)
    results: list[dict[str, Any]] = []
    processed = 0
    missing_key = 0

    for job in claimable["jobs"]:
        fingerprint = str(job.get("key_fingerprint") or "")
        api_key = secrets_by_fingerprint.get(fingerprint)
        if not api_key:
            missing_key += 1
            results.append({
                "job_id": job["id"],
                "status": "missing_key",
                "key_fingerprint": fingerprint,
                "key_masked": job.get("key_masked") or "",
            })
            continue
        try:
            report = await run_model_test_job_once(
                int(job["id"]),
                api_key,
                worker_id=worker_id,
                runner=runner,
                process_timeout_seconds=process_timeout_seconds,
                worker_timeout_seconds=worker_timeout_seconds,
                max_response_bytes=max_response_bytes,
                max_redirects=max_redirects,
                max_concurrency=max_concurrency,
                max_tokens=max_tokens,
            )
            processed += 1
            results.append({
                "job_id": job["id"],
                "status": "completed" if report else "not_found",
                "report_id": report.get("id") if isinstance(report, dict) else None,
                "key_fingerprint": fingerprint,
                "key_masked": mask_secret(api_key),
            })
        except Exception as exc:
            processed += 1
            results.append({
                "job_id": job["id"],
                "status": "failed",
                "error": _redact_text(f"{exc.__class__.__name__}: {exc}", api_key)[:255],
                "key_fingerprint": fingerprint,
                "key_masked": mask_secret(api_key),
            })

    return {
        "ok": True,
        "processed": processed,
        "missing_key": missing_key,
        "limit": limit,
        "results": results,
    }


def _key_manifest_to_fingerprints(manifest: dict[str, Any]) -> dict[str, str]:
    if not isinstance(manifest, dict):
        raise ValueError("key manifest must be a JSON object")
    items = manifest.get("keys", manifest)
    result: dict[str, str] = {}
    if isinstance(items, list):
        for item in items:
            if not isinstance(item, dict):
                continue
            api_key = str(item.get("api_key") or item.get("key") or "").strip()
            fingerprint = str(item.get("fingerprint") or fingerprint_secret(api_key)).strip()
            if api_key and fingerprint:
                result[fingerprint] = api_key
    elif isinstance(items, dict):
        for raw_fingerprint, raw_key in items.items():
            api_key = str(raw_key or "").strip()
            fingerprint = str(raw_fingerprint or fingerprint_secret(api_key)).strip()
            if api_key and fingerprint:
                result[fingerprint] = api_key
    else:
        raise ValueError("key manifest must contain keys as an object or list")
    if not result:
        raise ValueError("key manifest does not contain usable API keys")
    return result


async def run_worker_subprocess(
        task: dict[str, Any],
        *,
        process_timeout_seconds: float = 90.0,
        worker_timeout_seconds: float = 20.0,
        max_response_bytes: int = 256 * 1024,
        max_redirects: int = 2,
        max_concurrency: int = 2,
        max_tokens: int = 64,
        python_executable: str | None = None,
        worker_script: Path | None = None,
) -> dict[str, Any]:
    api_key = str(task.get("api_key") or "")
    command = [
        python_executable or sys.executable,
        str(worker_script or DEFAULT_WORKER_SCRIPT),
        "--timeout",
        str(worker_timeout_seconds),
        "--max-response-bytes",
        str(max_response_bytes),
        "--max-redirects",
        str(max_redirects),
        "--max-concurrency",
        str(max_concurrency),
        "--max-tokens",
        str(max_tokens),
    ]
    proc = await asyncio.create_subprocess_exec(
        *command,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdin_payload = json.dumps(task, ensure_ascii=False).encode("utf-8")
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(stdin_payload), timeout=process_timeout_seconds)
    except asyncio.TimeoutError as exc:
        proc.kill()
        await proc.communicate()
        raise RuntimeError("Worker process timed out.") from exc

    if proc.returncode != 0:
        stderr_text = _redact_text(stderr.decode("utf-8", errors="replace"), api_key)
        raise RuntimeError(f"Worker process failed with exit code {proc.returncode}: {stderr_text[:240]}")

    try:
        payload = json.loads(stdout.decode("utf-8"))
    except json.JSONDecodeError as exc:
        stdout_text = _redact_text(stdout.decode("utf-8", errors="replace"), api_key)
        raise RuntimeError(f"Worker process returned invalid JSON: {stdout_text[:240]}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("Worker process returned a non-object payload.")
    return payload


def _redact_text(value: str, secret: str = "") -> str:
    text = str(value or "")
    if secret:
        text = text.replace(secret, "[redacted]")
    text = re.sub(r"Bearer\s+[A-Za-z0-9._~+/=-]+", "Bearer [redacted]", text, flags=re.IGNORECASE)
    if "..." not in text:
        text = re.sub(r"sk-[A-Za-z0-9._~+/=-]{6,}", "sk-[redacted]", text)
    text = re.sub(r"(?i)(api[_-]?key|access_token|token|secret|password)=([^&\s]+)", r"\1=[redacted]", text)
    return text
