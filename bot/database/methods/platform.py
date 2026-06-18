from __future__ import annotations

import asyncio
import datetime
import ipaddress
import re
import secrets
import socket
from decimal import Decimal
from typing import Any
from urllib.parse import urlunsplit

import aiohttp
from sqlalchemy import Integer, and_, func, or_, select
from sqlalchemy.exc import IntegrityError

from bot.database import Database
from bot.database.methods.audit import log_audit
from bot.database.methods.create import create_user
from bot.database.methods.read import invalidate_user_cache
from bot.database.models import User
from bot.database.models.main import (
    AuditLog,
    ChannelClaims,
    ChannelInteractions,
    ChannelSubmissions,
    Channels,
    FraudEvents,
    GroupInviteRewards,
    InviteRetentionSnapshots,
    LedgerEntries,
    ModelTestJobs,
    ModelTestReports,
    ModelTestRuns,
    RelayAvailabilitySamples,
    RelayClaims,
    RelayFeedback,
    RelayProviders,
)
from bot.misc.url_safety import (
    UnsafeURL,
    fingerprint_secret,
    mask_secret,
    normalize_public_https_url,
    stable_hash,
)


CHANNEL_STATUSES = {
    "draft",
    "submitted",
    "auto_checked",
    "human_review",
    "approved",
    "needs_changes",
    "rejected",
    "risk_blocked",
}
CHANNEL_RISK_STATUSES = {"normal", "reported", "under_review", "dismissed", "risk_blocked"}
CHANNEL_INTERACTIONS = {"favorite", "hide", "click", "report", "rating"}
CHANNEL_CLAIM_METHODS = {"bot_admin", "challenge", "manual"}
RELAY_CLAIM_METHODS = {"domain", "challenge", "manual"}
RELAY_PROTOCOLS = {"openai", "anthropic", "openai-compatible", "anthropic-compatible"}
REPORT_VISIBILITY = {"private", "unlisted", "public", "under_review", "withdrawn"}
PUBLIC_REPORT_VISIBILITY = {"public", "unlisted"}
MODEL_TEST_STATUSES = {"created", "validating", "queued", "running", "scoring", "completed", "failed", "cancelled", "expired"}
FRAUD_EVENT_STATUSES = {"open", "under_review", "approved", "rejected", "resolved", "dismissed"}
REVIEW_ESCALATIONS = {"none", "watch", "operator", "risk", "urgent"}
RELAY_FEEDBACK_OUTCOMES = {
    "none",
    "acknowledged",
    "resolved",
    "provider_fixed",
    "user_error",
    "duplicate",
    "invalid",
    "escalated",
    "monitoring",
}
RELAY_CLAIM_WELL_KNOWN_PATH = "/.well-known/tgsellbot-relay-claim.txt"
RELAY_CLAIM_FETCH_TIMEOUT_SECONDS = 5
RELAY_CLAIM_FETCH_MAX_BYTES = 4096
REVIEW_WORKLOAD_OPEN_CHANNEL_RISKS = {"reported", "under_review"}
REVIEW_WORKLOAD_OPEN_FEEDBACK_STATUSES = {"submitted", "under_review"}
REVIEW_WORKLOAD_OPEN_WARNING_THRESHOLD = 5
REVIEW_WORKLOAD_URGENT_THRESHOLD = 1
MODEL_REPORT_LIMITATION = (
    "This report evaluates protocol compatibility, declared-model consistency, observed behavior, "
    "and degradation risk. Black-box testing cannot prove the real upstream model with certainty."
)


def model_test_report_share_token(report_id: int, user_id: int, job_id: int, token_secret: str) -> str:
    secret_text = (token_secret or "").strip()
    if not secret_text:
        return ""
    payload = f"model-report-share:{secret_text}:{int(report_id)}:{int(job_id)}:{int(user_id)}"
    return stable_hash(payload)[:40]


async def _recent_model_test_runs(s, job_id: int, *, limit: int = 10) -> list[dict[str, Any]]:
    rows = (await s.execute(
        select(ModelTestRuns)
        .where(ModelTestRuns.job_id == int(job_id))
        .order_by(ModelTestRuns.created_at.desc(), ModelTestRuns.id.desc())
        .limit(min(max(int(limit or 10), 1), 25))
    )).scalars().all()
    return [_model_test_run_to_dict(row) for row in rows]


def normalize_channel_username(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        raise ValueError("channel is required")
    text = text.replace("https://", "").replace("http://", "")
    if text.startswith("t.me/"):
        text = text[5:]
    if text.startswith("telegram.me/"):
        text = text[12:]
    text = text.split("/", 1)[0].split("?", 1)[0].strip()
    if text.startswith("@"):
        text = text[1:]
    username = text.lower()
    if not username or len(username) > 64 or not username.replace("_", "").isalnum():
        raise ValueError("invalid channel username")
    return username


async def ensure_platform_user(user_id: int) -> None:
    await create_user(
        telegram_id=int(user_id),
        registration_date=datetime.datetime.now(datetime.timezone.utc),
        referral_id=None,
        role=1,
    )


def _ip_is_public(ip_text: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_text)
    except ValueError:
        return False
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


async def _resolve_public_host(hostname: str) -> list[str]:
    def _resolve() -> list[str]:
        infos = socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)
        return sorted({item[4][0] for item in infos})

    try:
        addresses = await asyncio.to_thread(_resolve)
    except OSError as exc:
        raise UnsafeURL("Relay claim verification DNS resolution failed.") from exc
    if not addresses or any(not _ip_is_public(address) for address in addresses):
        raise UnsafeURL("Relay claim verification target resolved to an unsafe address.")
    return addresses


async def _fetch_text_no_redirect(url: str, *, timeout_seconds: int = RELAY_CLAIM_FETCH_TIMEOUT_SECONDS) -> str:
    timeout = aiohttp.ClientTimeout(total=timeout_seconds)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url, allow_redirects=False) as response:
            if response.status != 200:
                raise ValueError(f"relay claim proof returned HTTP {response.status}")
            content_type = response.headers.get("content-type", "")
            if content_type and not (
                    content_type.startswith("text/")
                    or content_type.startswith("application/json")
                    or content_type.startswith("application/octet-stream")
            ):
                raise ValueError("relay claim proof content type is not text")
            body = await response.content.read(RELAY_CLAIM_FETCH_MAX_BYTES + 1)
            if len(body) > RELAY_CLAIM_FETCH_MAX_BYTES:
                raise ValueError("relay claim proof is too large")
    return body.decode("utf-8", errors="replace")


async def verify_relay_claim_domain_control(
        claim: RelayClaims,
        provider: RelayProviders,
        *,
        fetcher=None,
        resolver=None,
) -> dict[str, Any]:
    safe = normalize_public_https_url(provider.public_base_url or provider.base_url_normalized, allow_path=False)
    host_resolver = resolver or _resolve_public_host
    addresses = await host_resolver(safe.hostname)
    if not addresses or any(not _ip_is_public(address) for address in addresses):
        raise UnsafeURL("Relay claim verification target resolved to an unsafe address.")
    proof_url = urlunsplit(("https", safe.hostname, RELAY_CLAIM_WELL_KNOWN_PATH, "", ""))
    expected_text = f"tgsellbot-relay-claim={claim.challenge}"
    text_fetcher = fetcher or _fetch_text_no_redirect
    body = await text_fetcher(proof_url)
    found = expected_text in body
    return {
        "ok": found,
        "url": proof_url,
        "expected_text": expected_text,
        "found": found,
    }


def _optional_positive_int(value: Any) -> int | None:
    if value in (None, "", 0, "0"):
        return None
    parsed = int(value)
    return parsed if parsed > 0 else None


async def create_ledger_entry(
        user_id: int,
        account_type: str,
        entry_type: str,
        amount: Decimal | int | str,
        *,
        status: str = "available",
        reference_type: str | None = None,
        reference_id: str | None = None,
        idempotency_key: str | None = None,
        available_at: datetime.datetime | None = None,
) -> dict[str, Any]:
    account_type = account_type.strip().lower()
    if account_type not in {"balance", "points"}:
        raise ValueError("account_type must be balance or points")
    if status not in {"pending", "available", "spent", "reversed", "expired"}:
        raise ValueError("invalid ledger status")
    amount_decimal = Decimal(str(amount)).quantize(Decimal("0.01"))

    await ensure_platform_user(user_id)
    async with Database().session() as s:
        if idempotency_key:
            existing = (await s.execute(
                select(LedgerEntries).where(LedgerEntries.idempotency_key == idempotency_key)
            )).scalars().one_or_none()
            if existing:
                return _ledger_to_dict(existing)

        entry = LedgerEntries(
            user_id=int(user_id),
            account_type=account_type,
            entry_type=entry_type,
            amount=amount_decimal,
            status=status,
            reference_type=reference_type,
            reference_id=reference_id,
            idempotency_key=idempotency_key,
            available_at=available_at,
        )
        s.add(entry)
        await s.flush()
        result = _ledger_to_dict(entry)

    await log_audit(
        "ledger_entry_create",
        user_id=int(user_id),
        resource_type="LedgerEntry",
        resource_id=str(result["id"]),
        details=f"{account_type}:{entry_type}:{amount_decimal}:{status}",
    )
    return result


async def create_ledger_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    created: list[dict[str, Any]] = []
    for entry in entries:
        created.append(await create_ledger_entry(**entry))
    return created


async def create_opening_ledger_entries(limit: int = 1000, offset: int = 0, *, dry_run: bool = False) -> dict[str, Any]:
    limit = min(max(int(limit or 1000), 1), 5000)
    offset = max(int(offset or 0), 0)
    created = 0
    skipped = 0
    would_create = 0
    preview: list[dict[str, Any]] = []
    async with Database().session() as s:
        users = (await s.execute(
            select(User).order_by(User.telegram_id.asc()).offset(offset).limit(limit)
        )).scalars().all()
        for user in users:
            entries = [
                ("balance", Decimal(str(user.balance or 0)).quantize(Decimal("0.01"))),
                ("points", Decimal(str(user.points_balance or 0)).quantize(Decimal("0.01"))),
            ]
            for account_type, expected_amount in entries:
                idempotency_key = f"opening:{user.telegram_id}:{account_type}"
                exists = (await s.execute(
                    select(LedgerEntries.id).where(LedgerEntries.idempotency_key == idempotency_key)
                )).scalar_one_or_none()
                if exists:
                    skipped += 1
                    continue
                ledger_total = Decimal(str((await s.execute(
                    select(func.coalesce(func.sum(LedgerEntries.amount), 0)).where(
                        LedgerEntries.user_id == int(user.telegram_id),
                        LedgerEntries.account_type == account_type,
                        LedgerEntries.status == "available",
                    )
                )).scalar_one() or 0)).quantize(Decimal("0.01"))
                amount = (expected_amount - ledger_total).quantize(Decimal("0.01"))
                if amount == Decimal("0.00"):
                    continue
                if dry_run:
                    would_create += 1
                    preview.append({
                        "user_id": int(user.telegram_id),
                        "account_type": account_type,
                        "amount": str(amount),
                        "idempotency_key": idempotency_key,
                    })
                    continue
                s.add(LedgerEntries(
                    user_id=int(user.telegram_id),
                    account_type=account_type,
                    entry_type="opening_balance",
                    amount=amount,
                    status="available",
                    reference_type="user",
                    reference_id=str(user.telegram_id),
                    idempotency_key=idempotency_key,
                ))
                created += 1
    return {
        "dry_run": bool(dry_run),
        "created": created,
        "would_create": would_create,
        "skipped": skipped,
        "preview": preview,
        "limit": limit,
        "offset": offset,
    }


async def reconcile_ledger_balances(limit: int = 1000, offset: int = 0) -> dict[str, Any]:
    limit = min(max(int(limit or 1000), 1), 5000)
    offset = max(int(offset or 0), 0)
    mismatches = []
    async with Database().session() as s:
        users = (await s.execute(
            select(User).order_by(User.telegram_id.asc()).offset(offset).limit(limit)
        )).scalars().all()
        for user in users:
            expected_balance = Decimal(str(user.balance or 0)).quantize(Decimal("0.01"))
            expected_points = Decimal(str(user.points_balance or 0)).quantize(Decimal("0.01"))
            ledger_balance_total = Decimal(str((await s.execute(
                select(func.coalesce(func.sum(LedgerEntries.amount), 0)).where(
                    LedgerEntries.user_id == int(user.telegram_id),
                    LedgerEntries.account_type == "balance",
                    LedgerEntries.status == "available",
                )
            )).scalar_one() or 0)).quantize(Decimal("0.01"))
            ledger_points_total = Decimal(str((await s.execute(
                select(func.coalesce(func.sum(LedgerEntries.amount), 0)).where(
                    LedgerEntries.user_id == int(user.telegram_id),
                    LedgerEntries.account_type == "points",
                    LedgerEntries.status == "available",
                )
            )).scalar_one() or 0)).quantize(Decimal("0.01"))
            if expected_balance != ledger_balance_total or expected_points != ledger_points_total:
                mismatches.append({
                    "user_id": int(user.telegram_id),
                    "expected_balance": str(expected_balance),
                    "ledger_balance": str(ledger_balance_total),
                    "expected_points": str(expected_points),
                    "ledger_points": str(ledger_points_total),
                })
    return {
        "checked": len(users),
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
        "limit": limit,
        "offset": offset,
    }


async def ledger_balance(user_id: int, account_type: str) -> Decimal:
    account_type = account_type.strip().lower()
    async with Database().session() as s:
        total = (await s.execute(
            select(func.coalesce(func.sum(LedgerEntries.amount), 0)).where(
                LedgerEntries.user_id == int(user_id),
                LedgerEntries.account_type == account_type,
                LedgerEntries.status == "available",
            )
        )).scalar_one()
    return Decimal(str(total or 0)).quantize(Decimal("0.01"))


async def list_ledger_entries(
        user_id: int,
        account_type: str = "",
        *,
        limit: int = 50,
        offset: int = 0,
) -> dict[str, Any]:
    limit = min(max(int(limit or 50), 1), 100)
    offset = max(int(offset or 0), 0)
    account_type = account_type.strip().lower()
    if account_type and account_type not in {"balance", "points"}:
        raise ValueError("account_type must be balance or points")

    async with Database().session() as s:
        filters = [LedgerEntries.user_id == int(user_id)]
        if account_type:
            filters.append(LedgerEntries.account_type == account_type)
        rows = (await s.execute(
            select(LedgerEntries)
            .where(*filters)
            .order_by(LedgerEntries.created_at.desc(), LedgerEntries.id.desc())
            .offset(offset)
            .limit(limit)
        )).scalars().all()
        balance_total = await _ledger_total(s, int(user_id), "balance")
        points_total = await _ledger_total(s, int(user_id), "points")
    return {
        "user_id": int(user_id),
        "balances": {
            "balance": str(balance_total),
            "points": str(points_total),
        },
        "entries": [_ledger_to_dict(row) for row in rows],
        "limit": limit,
        "offset": offset,
    }


async def _ledger_total(session, user_id: int, account_type: str) -> Decimal:
    total = (await session.execute(
        select(func.coalesce(func.sum(LedgerEntries.amount), 0)).where(
            LedgerEntries.user_id == int(user_id),
            LedgerEntries.account_type == account_type,
            LedgerEntries.status == "available",
        )
    )).scalar_one()
    return Decimal(str(total or 0)).quantize(Decimal("0.01"))


def _ledger_to_dict(entry: LedgerEntries) -> dict[str, Any]:
    return {
        "id": entry.id,
        "user_id": entry.user_id,
        "account_type": entry.account_type,
        "entry_type": entry.entry_type,
        "amount": str(entry.amount),
        "status": entry.status,
        "reference_type": entry.reference_type,
        "reference_id": entry.reference_id,
        "idempotency_key": entry.idempotency_key,
        "created_at": entry.created_at.isoformat() if entry.created_at else "",
    }


async def submit_channel(data: dict[str, Any], submitter_id: int) -> dict[str, Any]:
    username = normalize_channel_username(str(data.get("channel") or data.get("username") or ""))
    category = _clean_text(data.get("category"), "category", 64)
    language = _clean_text(data.get("language"), "language", 16)
    reason = _clean_text(data.get("reason"), "reason", 1000)
    title = _clean_text(data.get("title", username), "title", 255, allow_empty=True) or username
    description = _clean_text(data.get("description", ""), "description", 4000, allow_empty=True)
    commercial_content = _clean_text(data.get("commercial_content", "unknown"), "commercial_content", 32, allow_empty=True) or "unknown"
    submitter_relation = _clean_text(data.get("submitter_relation", "recommender"), "submitter_relation", 32, allow_empty=True) or "recommender"

    await ensure_platform_user(submitter_id)
    async with Database().session() as s:
        channel = (await s.execute(
            select(Channels).where(Channels.username == username).with_for_update()
        )).scalars().one_or_none()
        if not channel:
            channel = Channels(
                username=username,
                title=title,
                category=category,
                language=language,
                description=description,
                status="submitted",
            )
            s.add(channel)
            await s.flush()
        else:
            channel.title = channel.title or title
            channel.category = category or channel.category
            channel.language = language or channel.language
            channel.description = channel.description or description

        existing = (await s.execute(
            select(ChannelSubmissions).where(
                ChannelSubmissions.submitter_id == int(submitter_id),
                ChannelSubmissions.channel_id == channel.id,
            )
        )).scalars().one_or_none()
        if existing:
            return _channel_submission_to_dict(channel, existing, duplicate=True)

        submission = ChannelSubmissions(
            submitter_id=int(submitter_id),
            channel_id=channel.id,
            reason=reason,
            commercial_content=commercial_content,
            submitter_relation=submitter_relation,
            status="submitted",
        )
        s.add(submission)
        await s.flush()
        result = _channel_submission_to_dict(channel, submission, duplicate=False)

    await log_audit("channel_submit", user_id=int(submitter_id), resource_type="Channel", resource_id=username)
    return result


async def discover_channels(
        query: str = "",
        *,
        category: str = "",
        language: str = "",
        limit: int = 20,
        offset: int = 0,
) -> dict[str, Any]:
    limit = min(max(int(limit or 20), 1), 100)
    offset = max(int(offset or 0), 0)
    async with Database().session() as s:
        stmt = select(Channels).where(
            Channels.status == "approved",
            Channels.risk_status.notin_(("risk_blocked",)),
        )
        if query:
            like = f"%{query.strip().lower()}%"
            stmt = stmt.where(or_(func.lower(Channels.username).like(like), func.lower(Channels.title).like(like), func.lower(Channels.description).like(like)))
        if category:
            stmt = stmt.where(Channels.category == category)
        if language:
            stmt = stmt.where(Channels.language == language)
        total = (await s.execute(
            select(func.count()).select_from(stmt.subquery())
        )).scalar_one()
        rows = (await s.execute(
            stmt.order_by(Channels.quality_score.desc(), Channels.updated_at.desc()).offset(offset).limit(limit)
        )).scalars().all()
    return {
        "channels": [_channel_to_dict(row) for row in rows],
        "total": int(total or 0),
        "has_more": offset + len(rows) < int(total or 0),
        "limit": limit,
        "offset": offset,
    }


async def get_channel_detail(channel_id: int, user_id: int | None = None) -> dict[str, Any] | None:
    async with Database().session() as s:
        channel = (await s.execute(
            select(Channels).where(
                Channels.id == int(channel_id),
                Channels.status == "approved",
                Channels.risk_status.notin_(("risk_blocked",)),
            )
        )).scalars().one_or_none()
        if not channel:
            return None

        action_counts = (await s.execute(
            select(ChannelInteractions.action, func.count(ChannelInteractions.id))
            .where(ChannelInteractions.channel_id == int(channel_id))
            .group_by(ChannelInteractions.action)
        )).all()
        my_actions: set[str] = set()
        if user_id is not None:
            my_actions = {
                str(action)
                for action in (await s.execute(
                    select(ChannelInteractions.action).where(
                        ChannelInteractions.channel_id == int(channel_id),
                        ChannelInteractions.user_id == int(user_id),
                    )
                )).scalars().all()
            }
        can_edit_profile = user_id is not None and channel.owner_user_id == int(user_id)
        owner_claim = (await s.execute(
            select(ChannelClaims)
            .where(
                ChannelClaims.channel_id == int(channel_id),
                ChannelClaims.status == "approved",
            )
            .order_by(ChannelClaims.verified_at.desc(), ChannelClaims.id.desc())
            .limit(1)
        )).scalars().one_or_none()
        submissions = (await s.execute(
            select(ChannelSubmissions)
            .where(ChannelSubmissions.channel_id == int(channel_id))
            .order_by(ChannelSubmissions.created_at.desc(), ChannelSubmissions.id.desc())
            .limit(5)
        )).scalars().all()
        claims = (await s.execute(
            select(ChannelClaims)
            .where(ChannelClaims.channel_id == int(channel_id))
            .order_by(ChannelClaims.created_at.desc(), ChannelClaims.id.desc())
            .limit(5)
        )).scalars().all()
        audits = (await s.execute(
            select(AuditLog)
            .where(
                AuditLog.resource_type.in_(("Channel", "ChannelSubmission", "ChannelClaim")),
                or_(
                    AuditLog.resource_id == str(channel_id),
                    AuditLog.resource_id == channel.username,
                    AuditLog.resource_id == str(channel.id),
                ),
            )
            .order_by(AuditLog.timestamp.desc(), AuditLog.id.desc())
            .limit(10)
        )).scalars().all()

    return {
        "channel": _channel_to_public_detail_dict(channel),
        "interactions": {str(action): int(count or 0) for action, count in action_counts},
        "viewer": {
            "user_id": int(user_id) if user_id is not None else None,
            "actions": sorted(my_actions),
            "favorite": "favorite" in my_actions,
            "hidden": "hide" in my_actions,
            "reported": "report" in my_actions,
            "can_edit_profile": can_edit_profile,
        },
        "claim": _channel_claim_public_status(owner_claim),
        "submissions": [_channel_submission_detail_to_dict(row) for row in submissions],
        "claims": [_channel_claim_public_detail_to_dict(row) for row in claims],
        "audit_trail": [_audit_log_public_to_dict(row) for row in audits],
    }


async def get_channel_admin_detail(channel_id: int) -> dict[str, Any] | None:
    async with Database().session() as s:
        channel = (await s.execute(
            select(Channels).where(Channels.id == int(channel_id))
        )).scalars().one_or_none()
        if not channel:
            return None

        action_counts = (await s.execute(
            select(ChannelInteractions.action, func.count(ChannelInteractions.id))
            .where(ChannelInteractions.channel_id == int(channel_id))
            .group_by(ChannelInteractions.action)
        )).all()
        report_summary = (await s.execute(
            select(
                func.count(ChannelInteractions.id),
                func.min(ChannelInteractions.created_at),
                func.max(ChannelInteractions.created_at),
            ).where(
                ChannelInteractions.channel_id == int(channel_id),
                ChannelInteractions.action == "report",
            )
        )).one()
        submissions = (await s.execute(
            select(ChannelSubmissions)
            .where(ChannelSubmissions.channel_id == int(channel_id))
            .order_by(ChannelSubmissions.created_at.desc(), ChannelSubmissions.id.desc())
            .limit(10)
        )).scalars().all()
        claims = (await s.execute(
            select(ChannelClaims)
            .where(ChannelClaims.channel_id == int(channel_id))
            .order_by(ChannelClaims.created_at.desc(), ChannelClaims.id.desc())
            .limit(10)
        )).scalars().all()
        audits = (await s.execute(
            select(AuditLog)
            .where(or_(
                and_(
                    AuditLog.resource_type == "Channel",
                    AuditLog.resource_id.in_([str(channel_id), channel.username, str(channel.id)]),
                ),
                and_(
                    AuditLog.resource_type == "ChannelSubmission",
                    AuditLog.resource_id.in_([str(row.id) for row in submissions]),
                ),
                and_(
                    AuditLog.resource_type == "ChannelClaim",
                    AuditLog.resource_id.in_([str(row.id) for row in claims]),
                ),
            ))
            .order_by(AuditLog.timestamp.desc(), AuditLog.id.desc())
            .limit(20)
        )).scalars().all()

    report_count, first_reported_at, last_reported_at = report_summary
    return {
        "channel": _channel_admin_to_dict(channel),
        "interactions": {str(action): int(count or 0) for action, count in action_counts},
        "report": {
            "channel_id": channel.id,
            "report_count": int(report_count or 0),
            "status": channel.risk_status,
            "notes": channel.risk_notes,
            "reviewed_by": channel.risk_reviewed_by,
            "reviewed_at": channel.risk_reviewed_at.isoformat() if channel.risk_reviewed_at else "",
            "assigned_to": channel.risk_assigned_to,
            "escalation": channel.risk_escalation,
            "first_reported_at": first_reported_at.isoformat() if first_reported_at else "",
            "last_reported_at": last_reported_at.isoformat() if last_reported_at else "",
        },
        "submissions": [_channel_submission_detail_to_dict(row) for row in submissions],
        "claims": [_channel_claim_detail_to_dict(row) for row in claims],
        "audit_trail": [_audit_log_public_to_dict(row) for row in audits],
    }


async def list_channel_submissions(
        status: str = "",
        *,
        limit: int = 50,
        offset: int = 0,
) -> dict[str, Any]:
    limit = min(max(int(limit or 50), 1), 100)
    offset = max(int(offset or 0), 0)
    status = status.strip()
    async with Database().session() as s:
        stmt = (
            select(ChannelSubmissions, Channels)
            .join(Channels, Channels.id == ChannelSubmissions.channel_id)
        )
        if status:
            stmt = stmt.where(ChannelSubmissions.status == status)
        rows = (await s.execute(
            stmt.order_by(ChannelSubmissions.created_at.asc(), ChannelSubmissions.id.asc())
            .offset(offset)
            .limit(limit)
        )).all()
    return {
        "submissions": [
            {
                "submission": _channel_submission_row_to_dict(submission),
                "channel": _channel_to_dict(channel),
            }
            for submission, channel in rows
        ],
        "limit": limit,
        "offset": offset,
    }


async def review_channel_submission(submission_id: int, reviewer_id: int, status: str, notes: str = "") -> bool:
    if status not in CHANNEL_STATUSES:
        raise ValueError("invalid channel status")
    async with Database().session() as s:
        submission = (await s.execute(
            select(ChannelSubmissions).where(ChannelSubmissions.id == submission_id).with_for_update()
        )).scalars().one_or_none()
        if not submission:
            return False
        channel = (await s.execute(select(Channels).where(Channels.id == submission.channel_id).with_for_update())).scalars().one()
        submission.status = status
        submission.review_notes = notes
        submission.reviewed_by = int(reviewer_id)
        submission.reviewed_at = datetime.datetime.now(datetime.timezone.utc)
        channel.status = status
    await log_audit("channel_review", user_id=int(reviewer_id), resource_type="ChannelSubmission", resource_id=str(submission_id), details=status)
    return True


async def list_channel_claims(
        status: str = "",
        *,
        limit: int = 50,
        offset: int = 0,
) -> dict[str, Any]:
    limit = min(max(int(limit or 50), 1), 100)
    offset = max(int(offset or 0), 0)
    status = status.strip()
    async with Database().session() as s:
        stmt = (
            select(ChannelClaims, Channels)
            .join(Channels, Channels.id == ChannelClaims.channel_id)
        )
        if status:
            stmt = stmt.where(ChannelClaims.status == status)
        rows = (await s.execute(
            stmt.order_by(ChannelClaims.created_at.asc(), ChannelClaims.id.asc())
            .offset(offset)
            .limit(limit)
        )).all()
    return {
        "claims": [
            {
                "claim": _channel_claim_to_dict(claim),
                "channel": _channel_to_dict(channel),
            }
            for claim, channel in rows
        ],
        "limit": limit,
        "offset": offset,
    }


async def get_channel_claim_review_context(claim_id: int) -> dict[str, Any] | None:
    async with Database().session() as s:
        row = (await s.execute(
            select(ChannelClaims, Channels)
            .join(Channels, Channels.id == ChannelClaims.channel_id)
            .where(ChannelClaims.id == int(claim_id))
        )).one_or_none()
        if not row:
            return None
        claim, channel = row
        return {
            "claim": _channel_claim_detail_to_dict(claim),
            "channel": _channel_admin_to_dict(channel),
        }


async def create_channel_claim(channel_id: int, claimant_id: int, method: str = "challenge") -> dict[str, Any]:
    method = _clean_text(method, "method", 32).lower()
    if method not in CHANNEL_CLAIM_METHODS:
        raise ValueError("unsupported channel claim method")
    await ensure_platform_user(claimant_id)
    challenge = secrets.token_urlsafe(16) if method in {"challenge", "manual"} else ""
    async with Database().session() as s:
        channel = (await s.execute(select(Channels).where(Channels.id == int(channel_id)))).scalars().one_or_none()
        if not channel:
            raise ValueError("channel not found")
        claim = ChannelClaims(
            channel_id=int(channel_id),
            claimant_id=int(claimant_id),
            method=method,
            challenge=challenge,
            status="pending",
        )
        s.add(claim)
        await s.flush()
        result = {
            "id": claim.id,
            "channel_id": claim.channel_id,
            "claimant_id": claim.claimant_id,
            "method": claim.method,
            "challenge": claim.challenge,
            "status": claim.status,
            "verification": _channel_claim_verification_to_dict(claim, channel),
        }
    return result


def _validate_channel_bot_admin_proof(
        claim: ChannelClaims,
        proof: dict[str, Any] | None,
) -> dict[str, Any]:
    if not proof or not proof.get("verified"):
        raise ValueError("Bot admin verification is required before approving this channel claim.")
    try:
        proof_channel_id = int(proof.get("channel_id") or 0)
        proof_claimant_id = int(proof.get("claimant_id") or 0)
    except (TypeError, ValueError) as exc:
        raise ValueError("Bot admin verification proof is invalid.") from exc
    if proof_channel_id != int(claim.channel_id) or proof_claimant_id != int(claim.claimant_id):
        raise ValueError("Bot admin verification proof does not match this channel claim.")
    return {
        "telegram_status": _clean_text(str(proof.get("telegram_status") or ""), "telegram_status", 32),
        "telegram_chat": _clean_text(str(proof.get("telegram_chat") or ""), "telegram_chat", 128),
    }


async def verify_channel_claim(
        claim_id: int,
        reviewer_id: int,
        approved: bool,
        notes: str = "",
        bot_admin_verification: dict[str, Any] | None = None,
) -> bool:
    proof_summary: dict[str, Any] = {}
    async with Database().session() as s:
        claim = (await s.execute(
            select(ChannelClaims).where(ChannelClaims.id == int(claim_id)).with_for_update()
        )).scalars().one_or_none()
        if not claim:
            return False
        channel = (await s.execute(
            select(Channels).where(Channels.id == claim.channel_id).with_for_update()
        )).scalars().one_or_none()
        if not channel:
            return False
        if approved and claim.method == "bot_admin":
            proof_summary = _validate_channel_bot_admin_proof(claim, bot_admin_verification)
        claim.status = "approved" if approved else "rejected"
        claim.verified_at = datetime.datetime.now(datetime.timezone.utc)
        if approved:
            channel.owner_user_id = int(claim.claimant_id)
        result_status = claim.status

    await log_audit(
        "channel_claim_review",
        user_id=int(reviewer_id),
        resource_type="ChannelClaim",
        resource_id=str(claim_id),
        details=(
            f"status={result_status}, method={claim.method}, "
            f"bot_admin_verified={bool(proof_summary)}, "
            f"telegram_status={proof_summary.get('telegram_status', '')}, "
            f"notes={notes[:200]}"
        ),
    )
    return True


async def record_channel_interaction(user_id: int, channel_id: int, action: str, source: str = "") -> dict[str, Any]:
    if action not in CHANNEL_INTERACTIONS:
        raise ValueError("invalid channel interaction")
    await ensure_platform_user(user_id)
    async with Database().session() as s:
        channel = (await s.execute(
            select(Channels).where(Channels.id == int(channel_id)).with_for_update()
        )).scalars().one_or_none()
        if not channel:
            raise ValueError("channel not found")
        existing = (await s.execute(
            select(ChannelInteractions).where(
                ChannelInteractions.user_id == int(user_id),
                ChannelInteractions.channel_id == int(channel_id),
                ChannelInteractions.action == action,
            )
        )).scalars().one_or_none()
        if existing:
            existing.source = source or existing.source
            if action == "report" and channel.risk_status in {"normal", "dismissed"}:
                channel.risk_status = "reported"
            return {"id": existing.id, "already_recorded": True}
        interaction = ChannelInteractions(user_id=int(user_id), channel_id=int(channel_id), action=action, source=source)
        s.add(interaction)
        if action == "report" and channel.risk_status in {"normal", "dismissed"}:
            channel.risk_status = "reported"
        await s.flush()
        return {"id": interaction.id, "already_recorded": False}


async def list_channel_reports(
        status: str = "",
        *,
        assigned_to: int | str | None = None,
        reviewed_by: int | str | None = None,
        escalation: str = "",
        limit: int = 50,
        offset: int = 0,
) -> dict[str, Any]:
    limit = min(max(int(limit or 50), 1), 100)
    offset = max(int(offset or 0), 0)
    status = status.strip()
    assigned_filter = str(assigned_to or "").strip().lower()
    reviewed_filter = str(reviewed_by or "").strip().lower()
    escalation = str(escalation or "").strip().lower()
    if escalation and escalation not in REVIEW_ESCALATIONS:
        raise ValueError("invalid escalation")
    async with Database().session() as s:
        stmt = (
            select(
                Channels,
                func.count(ChannelInteractions.id).label("report_count"),
                func.min(ChannelInteractions.created_at).label("first_reported_at"),
                func.max(ChannelInteractions.created_at).label("last_reported_at"),
            )
            .join(ChannelInteractions, ChannelInteractions.channel_id == Channels.id)
            .where(ChannelInteractions.action == "report")
            .group_by(Channels.id)
        )
        if status:
            stmt = stmt.where(Channels.risk_status == status)
        if assigned_filter in {"unassigned", "none", "null"}:
            stmt = stmt.where(Channels.risk_assigned_to.is_(None))
        elif assigned_filter:
            stmt = stmt.where(Channels.risk_assigned_to == _optional_positive_int(assigned_filter))
        if reviewed_filter in {"unreviewed", "none", "null"}:
            stmt = stmt.where(Channels.risk_reviewed_by.is_(None))
        elif reviewed_filter:
            stmt = stmt.where(Channels.risk_reviewed_by == _optional_positive_int(reviewed_filter))
        if escalation:
            stmt = stmt.where(Channels.risk_escalation == escalation)
        rows = (await s.execute(
            stmt.order_by(func.max(ChannelInteractions.created_at).desc(), Channels.id.asc())
            .offset(offset)
            .limit(limit)
        )).all()
    return {
        "reports": [
            {
                "channel": _channel_to_dict(channel),
                "report": {
                    "channel_id": channel.id,
                    "report_count": int(report_count or 0),
                    "status": channel.risk_status,
                    "notes": channel.risk_notes,
                    "reviewed_by": channel.risk_reviewed_by,
                    "reviewed_at": channel.risk_reviewed_at.isoformat() if channel.risk_reviewed_at else "",
                    "assigned_to": channel.risk_assigned_to,
                    "escalation": channel.risk_escalation,
                    "first_reported_at": first_reported_at.isoformat() if first_reported_at else "",
                    "last_reported_at": last_reported_at.isoformat() if last_reported_at else "",
                },
            }
            for channel, report_count, first_reported_at, last_reported_at in rows
        ],
        "limit": limit,
        "offset": offset,
    }


async def review_channel_report(
        channel_id: int,
        reviewer_id: int,
        risk_status: str,
        notes: str = "",
        *,
        assigned_to: int | None = None,
        escalation: str = "none",
) -> bool:
    risk_status = _clean_text(risk_status, "risk_status", 32)
    if risk_status not in CHANNEL_RISK_STATUSES:
        raise ValueError("invalid channel risk status")
    escalation = _clean_text(escalation or "none", "escalation", 32).lower()
    if escalation not in REVIEW_ESCALATIONS:
        raise ValueError("invalid escalation")
    assigned_to = _optional_positive_int(assigned_to)
    async with Database().session() as s:
        channel = (await s.execute(
            select(Channels).where(Channels.id == int(channel_id)).with_for_update()
        )).scalars().one_or_none()
        if not channel:
            return False
        has_report = (await s.execute(
            select(ChannelInteractions.id).where(
                ChannelInteractions.channel_id == int(channel_id),
                ChannelInteractions.action == "report",
            ).limit(1)
        )).scalar_one_or_none()
        if not has_report:
            return False
        channel.risk_status = risk_status
        channel.risk_notes = _clean_text(notes, "notes", 1000, allow_empty=True)
        channel.risk_reviewed_by = int(reviewer_id)
        channel.risk_reviewed_at = datetime.datetime.now(datetime.timezone.utc)
        channel.risk_assigned_to = assigned_to
        channel.risk_escalation = escalation
    await log_audit(
        "channel_report_review",
        user_id=int(reviewer_id),
        resource_type="Channel",
        resource_id=str(channel_id),
        details=f"risk={risk_status}, assigned_to={assigned_to or ''}, escalation={escalation}, notes={notes[:200]}",
    )
    return True


async def update_channel_owner_profile(channel_id: int, owner_id: int, data: dict[str, Any]) -> dict[str, Any] | None:
    title = _clean_text(data.get("title", ""), "title", 255, allow_empty=True)
    category = _clean_text(data.get("category", ""), "category", 64, allow_empty=True)
    language = _clean_text(data.get("language", ""), "language", 16, allow_empty=True)
    description = _clean_text(data.get("description", ""), "description", 4000, allow_empty=True)
    async with Database().session() as s:
        channel = (await s.execute(
            select(Channels).where(Channels.id == int(channel_id)).with_for_update()
        )).scalars().one_or_none()
        if not channel:
            return None
        if channel.owner_user_id != int(owner_id):
            raise PermissionError("channel owner required")
        if title:
            channel.title = title
        if category:
            channel.category = category
        if language:
            channel.language = language
        if description or "description" in data:
            channel.description = description
        await s.flush()
        await s.refresh(channel)
        result = _channel_to_public_detail_dict(channel)
    await log_audit(
        "channel_owner_profile_update",
        user_id=int(owner_id),
        resource_type="Channel",
        resource_id=str(channel_id),
        details="owner profile updated",
    )
    return result


async def submit_relay_provider(data: dict[str, Any], submitter_id: int) -> dict[str, Any]:
    name = _clean_text(data.get("name"), "name", 128)
    base = normalize_public_https_url(str(data.get("base_url") or data.get("api_base_url") or ""))
    website = str(data.get("website_url") or "").strip()
    website_public = normalize_public_https_url(website).public if website else ""
    protocol = _clean_text(data.get("protocol"), "protocol", 32).lower()
    if protocol not in RELAY_PROTOCOLS:
        raise ValueError("unsupported relay protocol")
    await ensure_platform_user(submitter_id)
    async with Database().session() as s:
        existing = (await s.execute(
            select(RelayProviders).where(RelayProviders.base_url_hash == base.url_hash).with_for_update()
        )).scalars().one_or_none()
        if existing:
            return _relay_to_dict(existing, duplicate=True)
        provider = RelayProviders(
            name=name,
            website_url=website_public,
            base_url_normalized=base.normalized,
            base_url_hash=base.url_hash,
            public_base_url=base.public,
            owner_user_id=None,
            protocol=protocol,
            model_scope=_clean_text(data.get("model_scope", ""), "model_scope", 1000, allow_empty=True),
            region=_clean_text(data.get("region", ""), "region", 64, allow_empty=True),
            pricing=_clean_text(data.get("pricing", ""), "pricing", 1000, allow_empty=True),
            status="submitted",
            risk_status="new",
        )
        s.add(provider)
        await s.flush()
        result = _relay_to_dict(provider, duplicate=False)
    await log_audit("relay_submit", user_id=int(submitter_id), resource_type="RelayProvider", resource_id=str(result["id"]))
    return result


async def update_relay_owner_profile(provider_id: int, owner_id: int, data: dict[str, Any]) -> dict[str, Any] | None:
    name = _clean_text(data.get("name", ""), "name", 128, allow_empty=True)
    protocol = _clean_text(data.get("protocol", ""), "protocol", 32, allow_empty=True).lower()
    if protocol and protocol not in RELAY_PROTOCOLS:
        raise ValueError("unsupported relay protocol")
    model_scope = _clean_text(data.get("model_scope", ""), "model_scope", 1000, allow_empty=True)
    region = _clean_text(data.get("region", ""), "region", 64, allow_empty=True)
    pricing = _clean_text(data.get("pricing", ""), "pricing", 1000, allow_empty=True)
    website = str(data.get("website_url") or "").strip()
    website_public = normalize_public_https_url(website).public if website else ""
    async with Database().session() as s:
        provider = (await s.execute(
            select(RelayProviders).where(RelayProviders.id == int(provider_id)).with_for_update()
        )).scalars().one_or_none()
        if not provider:
            return None
        if provider.owner_user_id != int(owner_id):
            raise PermissionError("relay owner required")
        if name:
            provider.name = name
        if website or "website_url" in data:
            provider.website_url = website_public
        if protocol:
            provider.protocol = protocol
        if model_scope or "model_scope" in data:
            provider.model_scope = model_scope
        if region or "region" in data:
            provider.region = region
        if pricing or "pricing" in data:
            provider.pricing = pricing
        await s.flush()
        await s.refresh(provider)
        result = _relay_public_detail_to_dict(provider)
    await log_audit(
        "relay_owner_profile_update",
        user_id=int(owner_id),
        resource_type="RelayProvider",
        resource_id=str(provider_id),
        details="owner profile updated",
    )
    return result


async def list_relay_providers(
        status: str = "",
        *,
        limit: int = 50,
        offset: int = 0,
) -> dict[str, Any]:
    limit = min(max(int(limit or 50), 1), 100)
    offset = max(int(offset or 0), 0)
    status = status.strip()
    async with Database().session() as s:
        stmt = select(RelayProviders)
        if status:
            stmt = stmt.where(RelayProviders.status == status)
        rows = (await s.execute(
            stmt.order_by(RelayProviders.created_at.asc(), RelayProviders.id.asc())
            .offset(offset)
            .limit(limit)
        )).scalars().all()
    return {"providers": [_relay_to_dict(row, duplicate=False) for row in rows], "limit": limit, "offset": offset}


async def discover_relay_providers(
        query: str = "",
        *,
        protocol: str = "",
        region: str = "",
        limit: int = 20,
        offset: int = 0,
) -> dict[str, Any]:
    limit = min(max(int(limit or 20), 1), 100)
    offset = max(int(offset or 0), 0)
    query = query.strip().lower()
    protocol = protocol.strip().lower()
    region = region.strip()
    async with Database().session() as s:
        stmt = select(RelayProviders).where(
            RelayProviders.status == "approved",
            RelayProviders.risk_status.notin_(("risk_blocked", "blocked")),
        )
        if query:
            like = f"%{query}%"
            stmt = stmt.where(or_(
                func.lower(RelayProviders.name).like(like),
                func.lower(RelayProviders.model_scope).like(like),
                func.lower(RelayProviders.region).like(like),
            ))
        if protocol:
            stmt = stmt.where(RelayProviders.protocol == protocol)
        if region:
            stmt = stmt.where(RelayProviders.region == region)
        total = (await s.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
        rows = (await s.execute(
            stmt.order_by(RelayProviders.reputation_score.desc(), RelayProviders.updated_at.desc())
            .offset(offset)
            .limit(limit)
        )).scalars().all()
    return {
        "providers": [_relay_public_to_dict(row) for row in rows],
        "total": int(total or 0),
        "has_more": offset + len(rows) < int(total or 0),
        "limit": limit,
        "offset": offset,
    }


async def get_relay_provider_detail(provider_id: int, user_id: int | None = None) -> dict[str, Any] | None:
    async with Database().session() as s:
        provider = (await s.execute(
            select(RelayProviders).where(
                RelayProviders.id == int(provider_id),
                RelayProviders.status == "approved",
                RelayProviders.risk_status.notin_(("risk_blocked", "blocked")),
            )
        )).scalars().one_or_none()
        if not provider:
            return None
        can_edit_profile = user_id is not None and provider.owner_user_id == int(user_id)

        feedback_counts = (await s.execute(
            select(RelayFeedback.feedback_type, func.count(RelayFeedback.id))
            .where(
                RelayFeedback.provider_id == int(provider_id),
                RelayFeedback.status == "approved",
            )
            .group_by(RelayFeedback.feedback_type)
        )).all()
        avg_rating = (await s.execute(
            select(func.avg(RelayFeedback.rating)).where(
                RelayFeedback.provider_id == int(provider_id),
                RelayFeedback.status == "approved",
                RelayFeedback.rating.is_not(None),
            )
        )).scalar_one()
        owner_claim = (await s.execute(
            select(RelayClaims)
            .where(
                RelayClaims.provider_id == int(provider_id),
                RelayClaims.status == "approved",
            )
            .order_by(RelayClaims.verified_at.desc(), RelayClaims.id.desc())
            .limit(1)
        )).scalars().one_or_none()
        feedback_rows = (await s.execute(
            select(RelayFeedback)
            .where(
                RelayFeedback.provider_id == int(provider_id),
                RelayFeedback.status == "approved",
            )
            .order_by(RelayFeedback.created_at.desc(), RelayFeedback.id.desc())
            .limit(5)
        )).scalars().all()
        claims = (await s.execute(
            select(RelayClaims)
            .where(RelayClaims.provider_id == int(provider_id))
            .order_by(RelayClaims.created_at.desc(), RelayClaims.id.desc())
            .limit(5)
        )).scalars().all()
        audits = (await s.execute(
            select(AuditLog)
            .where(
                AuditLog.resource_type.in_(("RelayProvider", "RelayClaim", "RelayFeedback")),
                or_(
                    AuditLog.resource_id == str(provider_id),
                    AuditLog.resource_id == provider.name,
                    AuditLog.resource_id == str(provider.id),
                ),
            )
            .order_by(AuditLog.timestamp.desc(), AuditLog.id.desc())
            .limit(10)
        )).scalars().all()

    return {
        "provider": _relay_public_detail_to_dict(provider),
        "feedback": {
            "counts": {str(feedback_type): int(count or 0) for feedback_type, count in feedback_counts},
            "average_rating": float(avg_rating or 0),
            "recent": [_relay_feedback_public_to_dict(row) for row in feedback_rows],
        },
        "viewer": {
            "user_id": int(user_id) if user_id is not None else None,
            "can_edit_profile": can_edit_profile,
        },
        "claim": _relay_claim_public_status(owner_claim),
        "claims": [_relay_claim_public_detail_to_dict(row) for row in claims],
        "audit_trail": [_audit_log_public_to_dict(row) for row in audits],
    }


async def review_relay_provider(provider_id: int, reviewer_id: int, status: str, risk_status: str = "", notes: str = "") -> bool:
    if status not in CHANNEL_STATUSES:
        raise ValueError("invalid relay status")
    async with Database().session() as s:
        provider = (await s.execute(
            select(RelayProviders).where(RelayProviders.id == int(provider_id)).with_for_update()
        )).scalars().one_or_none()
        if not provider:
            return False
        provider.status = status
        if risk_status:
            provider.risk_status = _clean_text(risk_status, "risk_status", 32)
    await log_audit(
        "relay_review",
        user_id=int(reviewer_id),
        resource_type="RelayProvider",
        resource_id=str(provider_id),
        details=f"status={status}, risk={risk_status}, notes={notes[:200]}",
    )
    return True


async def create_relay_claim(provider_id: int, claimant_id: int, method: str = "challenge") -> dict[str, Any]:
    method = _clean_text(method, "method", 32).lower()
    if method not in RELAY_CLAIM_METHODS:
        raise ValueError("unsupported relay claim method")
    await ensure_platform_user(claimant_id)
    challenge = secrets.token_urlsafe(16) if method in {"challenge", "manual", "domain"} else ""
    async with Database().session() as s:
        provider = (await s.execute(select(RelayProviders).where(RelayProviders.id == int(provider_id)))).scalars().one_or_none()
        if not provider:
            raise ValueError("provider not found")
        claim = RelayClaims(provider_id=int(provider_id), claimant_id=int(claimant_id), method=method, challenge=challenge, status="pending")
        s.add(claim)
        await s.flush()
        return {
            "id": claim.id,
            "provider_id": provider_id,
            "claimant_id": claimant_id,
            "method": claim.method,
            "challenge": claim.challenge,
            "status": claim.status,
            "verification": _relay_claim_verification_to_dict(claim, provider),
        }


async def list_relay_claims(
        status: str = "",
        *,
        limit: int = 50,
        offset: int = 0,
) -> dict[str, Any]:
    limit = min(max(int(limit or 50), 1), 100)
    offset = max(int(offset or 0), 0)
    status = status.strip()
    async with Database().session() as s:
        stmt = (
            select(RelayClaims, RelayProviders)
            .join(RelayProviders, RelayProviders.id == RelayClaims.provider_id)
        )
        if status:
            stmt = stmt.where(RelayClaims.status == status)
        rows = (await s.execute(
            stmt.order_by(RelayClaims.created_at.asc(), RelayClaims.id.asc())
            .offset(offset)
            .limit(limit)
        )).all()
    return {
        "claims": [
            {
                "claim": _relay_claim_to_dict(claim),
                "provider": _relay_to_dict(provider, duplicate=False),
            }
            for claim, provider in rows
        ],
        "limit": limit,
        "offset": offset,
    }


async def verify_relay_claim(
        claim_id: int,
        reviewer_id: int,
        approved: bool,
        notes: str = "",
        *,
        fetcher=None,
        resolver=None,
) -> bool:
    verification_result: dict[str, Any] | None = None
    if approved:
        async with Database().session() as s:
            claim_for_check = (await s.execute(
                select(RelayClaims).where(RelayClaims.id == int(claim_id))
            )).scalars().one_or_none()
            if not claim_for_check:
                return False
            provider_for_check = (await s.execute(
                select(RelayProviders).where(RelayProviders.id == claim_for_check.provider_id)
            )).scalars().one_or_none()
            if not provider_for_check:
                return False
            if claim_for_check.method == "domain":
                verification_result = await verify_relay_claim_domain_control(
                    claim_for_check,
                    provider_for_check,
                    fetcher=fetcher,
                    resolver=resolver,
                )
                if not verification_result["ok"]:
                    raise ValueError("relay claim domain proof not found")

    async with Database().session() as s:
        claim = (await s.execute(
            select(RelayClaims).where(RelayClaims.id == int(claim_id)).with_for_update()
        )).scalars().one_or_none()
        if not claim:
            return False
        provider = (await s.execute(
            select(RelayProviders).where(RelayProviders.id == claim.provider_id).with_for_update()
        )).scalars().one_or_none()
        if not provider:
            return False
        claim.status = "approved" if approved else "rejected"
        claim.verified_at = datetime.datetime.now(datetime.timezone.utc)
        if approved:
            provider.owner_user_id = int(claim.claimant_id)
        result_status = claim.status

    await log_audit(
        "relay_claim_review",
        user_id=int(reviewer_id),
        resource_type="RelayClaim",
        resource_id=str(claim_id),
        details=(
            f"status={result_status}, domain_url={(verification_result or {}).get('url', '')}, "
            f"notes={notes[:200]}"
        ),
    )
    return True


async def add_relay_feedback(provider_id: int, user_id: int, feedback_type: str, text: str = "", rating: int | None = None) -> dict[str, Any]:
    await ensure_platform_user(user_id)
    if rating is not None and not (1 <= int(rating) <= 5):
        raise ValueError("rating must be 1..5")
    async with Database().session() as s:
        feedback = RelayFeedback(
            provider_id=int(provider_id),
            user_id=int(user_id),
            feedback_type=feedback_type,
            rating=rating,
            text=_clean_text(text, "text", 4000, allow_empty=True),
            status="submitted",
        )
        s.add(feedback)
        await s.flush()
        return {"id": feedback.id, "provider_id": provider_id, "user_id": user_id, "feedback_type": feedback_type}


async def list_relay_feedback(
        status: str = "",
        feedback_type: str = "",
        outcome: str = "",
        *,
        assigned_to: int | str | None = None,
        reviewed_by: int | str | None = None,
        escalation: str = "",
        limit: int = 50,
        offset: int = 0,
) -> dict[str, Any]:
    limit = min(max(int(limit or 50), 1), 100)
    offset = max(int(offset or 0), 0)
    status = status.strip()
    feedback_type = feedback_type.strip()
    outcome = outcome.strip()
    assigned_filter = str(assigned_to or "").strip().lower()
    reviewed_filter = str(reviewed_by or "").strip().lower()
    escalation = str(escalation or "").strip().lower()
    if escalation and escalation not in REVIEW_ESCALATIONS:
        raise ValueError("invalid escalation")
    async with Database().session() as s:
        stmt = (
            select(RelayFeedback, RelayProviders)
            .join(RelayProviders, RelayProviders.id == RelayFeedback.provider_id)
        )
        if status:
            stmt = stmt.where(RelayFeedback.status == status)
        if feedback_type:
            stmt = stmt.where(RelayFeedback.feedback_type == feedback_type)
        if outcome:
            stmt = stmt.where(RelayFeedback.outcome == outcome)
        if assigned_filter in {"unassigned", "none", "null"}:
            stmt = stmt.where(RelayFeedback.assigned_to.is_(None))
        elif assigned_filter:
            stmt = stmt.where(RelayFeedback.assigned_to == _optional_positive_int(assigned_filter))
        if reviewed_filter in {"unreviewed", "none", "null"}:
            stmt = stmt.where(RelayFeedback.reviewed_by.is_(None))
        elif reviewed_filter:
            stmt = stmt.where(RelayFeedback.reviewed_by == _optional_positive_int(reviewed_filter))
        if escalation:
            stmt = stmt.where(RelayFeedback.escalation == escalation)
        rows = (await s.execute(
            stmt.order_by(RelayFeedback.created_at.asc(), RelayFeedback.id.asc())
            .offset(offset)
            .limit(limit)
        )).all()
    return {
        "feedback": [
            {
                "feedback": _relay_feedback_to_dict(feedback),
                "provider": _relay_to_dict(provider, duplicate=False),
            }
            for feedback, provider in rows
        ],
        "limit": limit,
        "offset": offset,
    }


async def review_relay_feedback(
        feedback_id: int,
        reviewer_id: int,
        status: str,
        notes: str = "",
        *,
        assigned_to: int | None = None,
        escalation: str = "none",
        outcome: str = "none",
        followup_notes: str = "",
) -> bool:
    if status not in {"submitted", "under_review", "approved", "rejected", "risk_blocked"}:
        raise ValueError("invalid feedback status")
    escalation = _clean_text(escalation or "none", "escalation", 32).lower()
    if escalation not in REVIEW_ESCALATIONS:
        raise ValueError("invalid escalation")
    outcome = _clean_text(outcome or "none", "outcome", 32).lower()
    if outcome not in RELAY_FEEDBACK_OUTCOMES:
        raise ValueError("invalid feedback outcome")
    followup_notes = _clean_text(followup_notes, "followup_notes", 2000, allow_empty=True)
    assigned_to = _optional_positive_int(assigned_to)
    resolved_by: int | None = None
    resolved_at: datetime.datetime | None = None
    if outcome != "none" or followup_notes:
        resolved_by = int(reviewer_id)
        resolved_at = datetime.datetime.now(datetime.timezone.utc)
    async with Database().session() as s:
        feedback = (await s.execute(
            select(RelayFeedback).where(RelayFeedback.id == int(feedback_id)).with_for_update()
        )).scalars().one_or_none()
        if not feedback:
            return False
        feedback.status = status
        feedback.review_notes = _clean_text(notes, "notes", 1000, allow_empty=True)
        feedback.reviewed_by = int(reviewer_id)
        feedback.reviewed_at = datetime.datetime.now(datetime.timezone.utc)
        feedback.assigned_to = assigned_to
        feedback.escalation = escalation
        feedback.outcome = outcome
        feedback.followup_notes = followup_notes
        feedback.resolved_by = resolved_by
        feedback.resolved_at = resolved_at
    await log_audit(
        "relay_feedback_review",
        user_id=int(reviewer_id),
        resource_type="RelayFeedback",
        resource_id=str(feedback_id),
        details=(
            f"status={status}, assigned_to={assigned_to or ''}, escalation={escalation}, "
            f"outcome={outcome}, notes={notes[:200]}"
        ),
    )
    return True


async def create_model_test_job(data: dict[str, Any], user_id: int) -> dict[str, Any]:
    await ensure_platform_user(user_id)
    endpoint = normalize_public_https_url(str(data.get("endpoint") or data.get("base_url") or ""))
    protocol = _clean_text(data.get("protocol"), "protocol", 32).lower()
    if protocol not in RELAY_PROTOCOLS:
        raise ValueError("unsupported protocol")
    idempotency_key = _clean_text(data.get("idempotency_key"), "idempotency_key", 128)
    raw_key = str(data.get("api_key") or "")
    async with Database().session() as s:
        existing = (await s.execute(
            select(ModelTestJobs).where(ModelTestJobs.idempotency_key == idempotency_key)
        )).scalars().one_or_none()
        if existing:
            return _job_to_dict(existing, duplicate=True)
        job = ModelTestJobs(
            user_id=int(user_id),
            provider_id=data.get("provider_id"),
            endpoint_hash=endpoint.url_hash,
            endpoint_normalized=endpoint.normalized,
            endpoint_public=endpoint.public,
            protocol=protocol,
            requested_model=_clean_text(data.get("requested_model", ""), "requested_model", 128, allow_empty=True),
            status="created",
            idempotency_key=idempotency_key,
            key_fingerprint=fingerprint_secret(raw_key),
            key_masked=mask_secret(raw_key),
        )
        s.add(job)
        await s.flush()
        result = _job_to_dict(job, duplicate=False)
    await log_audit("model_test_job_create", user_id=int(user_id), resource_type="ModelTestJob", resource_id=str(result["id"]), details=f"endpoint={endpoint.public}")
    return result


async def get_model_test_job(job_id: int, user_id: int | None = None) -> dict[str, Any] | None:
    async with Database().session() as s:
        stmt = (
            select(ModelTestJobs, ModelTestReports)
            .outerjoin(ModelTestReports, ModelTestReports.job_id == ModelTestJobs.id)
            .where(ModelTestJobs.id == int(job_id))
        )
        if user_id is not None:
            stmt = stmt.where(ModelTestJobs.user_id == int(user_id))
        row = (await s.execute(stmt)).one_or_none()
        if not row:
            return None
        job, report = row
        runs = await _recent_model_test_runs(s, job.id)
    result = _job_to_dict(job, duplicate=False, report=report)
    result["runs"] = list(reversed(runs))
    return result


async def list_model_test_jobs(
        user_id: int,
        status: str = "",
        *,
        limit: int = 20,
        offset: int = 0,
) -> dict[str, Any]:
    limit = min(max(int(limit or 20), 1), 100)
    offset = max(int(offset or 0), 0)
    status = status.strip()
    if status and status not in MODEL_TEST_STATUSES:
        raise ValueError("invalid model test status")
    async with Database().session() as s:
        base_stmt = select(ModelTestJobs).where(ModelTestJobs.user_id == int(user_id))
        if status:
            base_stmt = base_stmt.where(ModelTestJobs.status == status)
        total = (await s.execute(
            select(func.count()).select_from(base_stmt.subquery())
        )).scalar_one()
        stmt = (
            select(ModelTestJobs, ModelTestReports)
            .outerjoin(ModelTestReports, ModelTestReports.job_id == ModelTestJobs.id)
            .where(ModelTestJobs.user_id == int(user_id))
        )
        if status:
            stmt = stmt.where(ModelTestJobs.status == status)
        rows = (await s.execute(
            stmt.order_by(ModelTestJobs.created_at.desc(), ModelTestJobs.id.desc())
            .offset(offset)
            .limit(limit)
        )).all()
    return {
        "jobs": [
            _job_to_dict(job, duplicate=False, report=report)
            for job, report in rows
        ],
        "total": int(total or 0),
        "has_more": offset + len(rows) < int(total or 0),
        "limit": limit,
        "offset": offset,
    }


async def list_claimable_model_test_jobs(
        *,
        limit: int = 20,
        statuses: tuple[str, ...] = ("created", "queued", "failed"),
) -> dict[str, Any]:
    limit = min(max(int(limit or 20), 1), 100)
    safe_statuses = tuple(status for status in statuses if status in MODEL_TEST_STATUSES)
    if not safe_statuses:
        raise ValueError("no claimable statuses")
    async with Database().session() as s:
        rows = (await s.execute(
            select(ModelTestJobs)
            .where(ModelTestJobs.status.in_(safe_statuses))
            .order_by(ModelTestJobs.created_at.asc(), ModelTestJobs.id.asc())
            .limit(limit)
        )).scalars().all()
    return {
        "jobs": [_job_to_dict(row, duplicate=False) for row in rows],
        "limit": limit,
        "statuses": list(safe_statuses),
    }


async def claim_model_test_job(job_id: int, worker_id: str, api_key: str) -> dict[str, Any] | None:
    worker_id = _clean_text(worker_id or "model-lab-worker", "worker_id", 64)
    raw_key = str(api_key or "").strip()
    key_fingerprint = fingerprint_secret(raw_key)
    if not key_fingerprint:
        raise ValueError("api_key is required")

    async with Database().session() as s:
        job = (await s.execute(
            select(ModelTestJobs).where(ModelTestJobs.id == int(job_id)).with_for_update()
        )).scalars().one_or_none()
        if not job:
            return None
        if job.status not in {"created", "queued", "failed"}:
            raise ValueError("job is not claimable")
        if job.key_fingerprint and job.key_fingerprint != key_fingerprint:
            raise ValueError("api_key fingerprint does not match job")
        job.status = "running"
        job.worker_id = worker_id
        job.failure_reason = ""
        task = {
            "job_id": job.id,
            "endpoint": job.endpoint_normalized,
            "protocol": job.protocol,
            "requested_model": job.requested_model,
            "api_key": raw_key,
            "visibility": "private",
        }

    await log_audit(
        "model_test_job_claim",
        user_id=None,
        resource_type="ModelTestJob",
        resource_id=str(job_id),
        details=f"worker={worker_id}",
    )
    return task


async def complete_model_test_job(job_id: int, worker_id: str, report_data: dict[str, Any]) -> dict[str, Any]:
    worker_id = _clean_text(worker_id or "model-lab-worker", "worker_id", 64)
    visibility = _clean_text(report_data.get("visibility", "private"), "visibility", 16)
    if visibility not in REPORT_VISIBILITY:
        raise ValueError("invalid visibility")

    async with Database().session() as s:
        job = (await s.execute(
            select(ModelTestJobs).where(ModelTestJobs.id == int(job_id)).with_for_update()
        )).scalars().one_or_none()
        if not job:
            raise ValueError("job not found")
        if job.worker_id and job.worker_id != worker_id:
            raise ValueError("job is claimed by another worker")
        report = (await s.execute(
            select(ModelTestReports).where(ModelTestReports.job_id == int(job_id)).with_for_update()
        )).scalars().one_or_none()
        if not report:
            report = ModelTestReports(job_id=int(job_id))
            s.add(report)
        report.declared_model = _clean_text(report_data.get("declared_model", job.requested_model), "declared_model", 128, allow_empty=True)
        report.returned_model = _clean_text(report_data.get("returned_model", ""), "returned_model", 128, allow_empty=True)
        report.suite_version = _clean_text(report_data.get("suite_version", ""), "suite_version", 64, allow_empty=True)
        report.scores = report_data.get("scores") or {}
        report.grade = _clean_text(report_data.get("grade", "F"), "grade", 8, allow_empty=True) or "F"
        report.evidence_json = _redact_evidence(report_data.get("evidence_json") or {})
        report.visibility = visibility
        report.limitation_note = report_data.get("limitation_note") or MODEL_REPORT_LIMITATION
        job.status = "completed"
        job.failure_reason = ""
        await s.flush()
        result = {"id": report.id, "job_id": report.job_id, "visibility": report.visibility, "limitation_note": report.limitation_note}

    await log_audit(
        "model_test_job_complete",
        user_id=None,
        resource_type="ModelTestJob",
        resource_id=str(job_id),
        details=f"worker={worker_id}, report={result['id']}",
    )
    return result


async def mark_model_test_job_failed(job_id: int, worker_id: str, reason: str) -> bool:
    worker_id = _clean_text(worker_id or "model-lab-worker", "worker_id", 64)
    safe_reason = _redact_text(_clean_text(reason, "reason", 255, allow_empty=True))
    async with Database().session() as s:
        job = (await s.execute(
            select(ModelTestJobs).where(ModelTestJobs.id == int(job_id)).with_for_update()
        )).scalars().one_or_none()
        if not job:
            return False
        if job.worker_id and job.worker_id != worker_id:
            raise ValueError("job is claimed by another worker")
        job.status = "failed"
        job.worker_id = worker_id
        job.failure_reason = safe_reason

    await log_audit(
        "model_test_job_fail",
        user_id=None,
        resource_type="ModelTestJob",
        resource_id=str(job_id),
        details=f"worker={worker_id}, reason={safe_reason[:120]}",
    )
    return True


async def record_model_test_run(
        job_id: int,
        worker_id: str,
        status: str,
        *,
        duration_ms: int = 0,
        report_data: dict[str, Any] | None = None,
        error_type: str = "",
        error_summary: str = "",
        estimated_cost: Decimal | int | str | None = None,
) -> dict[str, Any] | None:
    if status not in {"completed", "failed", "cancelled", "timeout"}:
        raise ValueError("invalid model test run status")
    worker_id = _clean_text(worker_id or "model-lab-worker", "worker_id", 64, allow_empty=True)
    safe_error_type = _clean_text(error_type, "error_type", 64, allow_empty=True)
    safe_error_summary = _safe_summary(error_summary)
    metrics = _extract_model_run_metrics(report_data or {})
    cost = estimated_cost
    if cost is None:
        cost = metrics.get("estimated_cost")
    cost_decimal = None
    if cost not in (None, ""):
        cost_decimal = Decimal(str(cost)).quantize(Decimal("0.000001"))
    async with Database().session() as s:
        job = (await s.execute(
            select(ModelTestJobs).where(ModelTestJobs.id == int(job_id))
        )).scalars().one_or_none()
        if not job:
            return None
        duration = max(0, int(duration_ms or 0))
        run = ModelTestRuns(
            job_id=int(job_id),
            provider_id=job.provider_id,
            worker_id=worker_id,
            status=status,
            duration_ms=duration,
            request_count=int(metrics.get("request_count") or 0),
            total_tokens=int(metrics.get("total_tokens") or 0),
            estimated_cost=cost_decimal,
            error_type=safe_error_type,
            error_summary=safe_error_summary,
        )
        s.add(run)
        await s.flush()
        result = _model_test_run_to_dict(run)
        if job.provider_id:
            availability = _extract_relay_availability_metrics(
                report_data or {},
                fallback_latency_ms=duration,
                status=status,
                error_type=safe_error_type,
                error_summary=safe_error_summary,
            )
            sample = RelayAvailabilitySamples(
                provider_id=int(job.provider_id),
                job_id=int(job_id),
                source="model_test",
                status=str(availability["status"]),
                http_status=availability.get("http_status"),
                latency_ms=int(availability.get("latency_ms") or 0),
                error_type=str(availability.get("error_type") or ""),
                error_summary=str(availability.get("error_summary") or ""),
            )
            s.add(sample)
            await s.flush()
            result["availability_sample"] = _relay_availability_sample_to_dict(sample)
    return result


async def record_relay_availability_sample(
        provider_id: int,
        *,
        job_id: int | None = None,
        source: str = "model_test",
        status: str,
        http_status: int | None = None,
        latency_ms: int = 0,
        error_type: str = "",
        error_summary: str = "",
) -> dict[str, Any]:
    if status not in {"available", "degraded", "failed", "unknown"}:
        raise ValueError("invalid relay availability status")
    safe_source = _clean_text(source or "model_test", "source", 64)
    safe_error_type = _clean_text(error_type, "error_type", 64, allow_empty=True)
    safe_error_summary = _safe_summary(error_summary)
    async with Database().session() as s:
        provider = (await s.execute(
            select(RelayProviders).where(RelayProviders.id == int(provider_id))
        )).scalars().one_or_none()
        if not provider:
            raise ValueError("relay provider not found")
        sample = RelayAvailabilitySamples(
            provider_id=int(provider_id),
            job_id=int(job_id) if job_id else None,
            source=safe_source,
            status=status,
            http_status=int(http_status) if http_status is not None else None,
            latency_ms=max(0, int(latency_ms or 0)),
            error_type=safe_error_type,
            error_summary=safe_error_summary,
        )
        s.add(sample)
        await s.flush()
        result = _relay_availability_sample_to_dict(sample)
    return result


async def create_model_test_report(job_id: int, data: dict[str, Any]) -> dict[str, Any]:
    visibility = _clean_text(data.get("visibility", "private"), "visibility", 16)
    if visibility not in REPORT_VISIBILITY:
        raise ValueError("invalid visibility")
    async with Database().session() as s:
        job = (await s.execute(select(ModelTestJobs).where(ModelTestJobs.id == int(job_id)).with_for_update())).scalars().one_or_none()
        if not job:
            raise ValueError("job not found")
        report = (await s.execute(select(ModelTestReports).where(ModelTestReports.job_id == int(job_id)).with_for_update())).scalars().one_or_none()
        if not report:
            report = ModelTestReports(job_id=int(job_id))
            s.add(report)
        report.declared_model = _clean_text(data.get("declared_model", job.requested_model), "declared_model", 128, allow_empty=True)
        report.returned_model = _clean_text(data.get("returned_model", ""), "returned_model", 128, allow_empty=True)
        report.suite_version = _clean_text(data.get("suite_version", ""), "suite_version", 64, allow_empty=True)
        report.scores = data.get("scores") or {}
        report.grade = _clean_text(data.get("grade", "F"), "grade", 8, allow_empty=True) or "F"
        report.evidence_json = _redact_evidence(data.get("evidence_json") or {})
        report.visibility = visibility
        report.limitation_note = data.get("limitation_note") or MODEL_REPORT_LIMITATION
        job.status = "completed"
        await s.flush()
        return {"id": report.id, "job_id": report.job_id, "visibility": report.visibility, "limitation_note": report.limitation_note}


async def get_model_test_report(report_id: int, user_id: int | None = None) -> dict[str, Any] | None:
    async with Database().session() as s:
        stmt = (
            select(ModelTestReports, ModelTestJobs)
            .join(ModelTestJobs, ModelTestJobs.id == ModelTestReports.job_id)
            .where(ModelTestReports.id == int(report_id))
        )
        if user_id is not None:
            stmt = stmt.where(ModelTestJobs.user_id == int(user_id))
        row = (await s.execute(stmt)).one_or_none()
        if not row:
            return None
        report, job = row
        runs = await _recent_model_test_runs(s, job.id)
    return _report_to_dict(report, job, runs=list(reversed(runs)))


async def get_public_model_test_report(
        report_id: int,
        *,
        share_token: str = "",
        token_secret: str = "",
) -> dict[str, Any] | None:
    async with Database().session() as s:
        row = (await s.execute(
            select(ModelTestReports, ModelTestJobs)
            .join(ModelTestJobs, ModelTestJobs.id == ModelTestReports.job_id)
            .where(ModelTestReports.id == int(report_id))
        )).one_or_none()
        if not row:
            return None
        report, job = row
        if report.visibility == "unlisted":
            expected = model_test_report_share_token(report.id, job.user_id, job.id, token_secret)
            if not expected or str(share_token or "") != expected:
                return None
        elif report.visibility != "public":
            return None
        runs = await _recent_model_test_runs(s, job.id)
    return _public_report_to_dict(report, job, token_secret=token_secret, runs=list(reversed(runs)))


async def list_model_test_reports(
        user_id: int,
        visibility: str = "",
        *,
        limit: int = 20,
        offset: int = 0,
) -> dict[str, Any]:
    limit = min(max(int(limit or 20), 1), 100)
    offset = max(int(offset or 0), 0)
    visibility = visibility.strip()
    if visibility and visibility not in REPORT_VISIBILITY:
        raise ValueError("invalid visibility")
    async with Database().session() as s:
        stmt = (
            select(ModelTestReports, ModelTestJobs)
            .join(ModelTestJobs, ModelTestJobs.id == ModelTestReports.job_id)
            .where(ModelTestJobs.user_id == int(user_id))
        )
        if visibility:
            stmt = stmt.where(ModelTestReports.visibility == visibility)
        total = (await s.execute(
            select(func.count()).select_from(stmt.subquery())
        )).scalar_one()
        rows = (await s.execute(
            stmt.order_by(ModelTestReports.created_at.desc(), ModelTestReports.id.desc())
            .offset(offset)
            .limit(limit)
        )).all()
    return {
        "reports": [
            _report_to_dict(report, job)
            for report, job in rows
        ],
        "total": int(total or 0),
        "has_more": offset + len(rows) < int(total or 0),
        "limit": limit,
        "offset": offset,
    }


async def list_public_model_test_reports(
        *,
        limit: int = 20,
        offset: int = 0,
        token_secret: str = "",
) -> dict[str, Any]:
    limit = min(max(int(limit or 20), 1), 100)
    offset = max(int(offset or 0), 0)
    async with Database().session() as s:
        stmt = (
            select(ModelTestReports, ModelTestJobs)
            .join(ModelTestJobs, ModelTestJobs.id == ModelTestReports.job_id)
            .where(ModelTestReports.visibility == "public")
        )
        total = (await s.execute(
            select(func.count()).select_from(stmt.subquery())
        )).scalar_one()
        rows = (await s.execute(
            stmt.order_by(ModelTestReports.created_at.desc(), ModelTestReports.id.desc())
            .offset(offset)
            .limit(limit)
        )).all()
    return {
        "reports": [
            _public_report_to_dict(report, job, token_secret=token_secret)
            for report, job in rows
        ],
        "total": int(total or 0),
        "has_more": offset + len(rows) < int(total or 0),
        "limit": limit,
        "offset": offset,
    }


async def set_report_visibility(report_id: int, visibility: str, user_id: int | None = None) -> bool:
    if visibility not in REPORT_VISIBILITY:
        raise ValueError("invalid visibility")
    async with Database().session() as s:
        stmt = (
            select(ModelTestReports, ModelTestJobs)
            .join(ModelTestJobs, ModelTestJobs.id == ModelTestReports.job_id)
            .where(ModelTestReports.id == int(report_id))
            .with_for_update()
        )
        if user_id is not None:
            stmt = stmt.where(ModelTestJobs.user_id == int(user_id))
        row = (await s.execute(stmt)).one_or_none()
        if not row:
            return False
        report, _job = row
        report.visibility = visibility
    await log_audit("model_report_visibility", user_id=user_id, resource_type="ModelTestReport", resource_id=str(report_id), details=visibility)
    return True


async def record_fraud_event(subject_type: str, subject_id: str, event_type: str, evidence: dict[str, Any], score_delta: int = 0) -> dict[str, Any]:
    async with Database().session() as s:
        event = FraudEvents(subject_type=subject_type, subject_id=subject_id, event_type=event_type, evidence=_redact_evidence(evidence), score_delta=score_delta)
        s.add(event)
        await s.flush()
        return {"id": event.id, "subject_type": subject_type, "subject_id": subject_id}


async def list_fraud_events(
        event_type: str = "",
        status: str = "",
        *,
        limit: int = 50,
        offset: int = 0,
) -> dict[str, Any]:
    limit = min(max(int(limit or 50), 1), 100)
    offset = max(int(offset or 0), 0)
    event_type = event_type.strip()
    status = status.strip()
    async with Database().session() as s:
        stmt = select(FraudEvents)
        if event_type:
            stmt = stmt.where(FraudEvents.event_type == event_type)
        if status:
            stmt = stmt.where(FraudEvents.status == status)
        rows = (await s.execute(
            stmt.order_by(FraudEvents.created_at.asc(), FraudEvents.id.asc())
            .offset(offset)
            .limit(limit)
        )).scalars().all()
    return {
        "events": [_fraud_event_to_dict(row) for row in rows],
        "limit": limit,
        "offset": offset,
    }


async def review_fraud_event(event_id: int, reviewer_id: int, status: str, notes: str = "") -> bool:
    if status not in FRAUD_EVENT_STATUSES:
        raise ValueError("invalid fraud event status")
    async with Database().session() as s:
        event = (await s.execute(
            select(FraudEvents).where(FraudEvents.id == int(event_id)).with_for_update()
        )).scalars().one_or_none()
        if not event:
            return False
        evidence = dict(event.evidence or {})
        review = dict(evidence.get("review") or {})
        review.update({
            "reviewer_id": int(reviewer_id),
            "notes": _safe_summary(notes, max_len=1000),
            "reviewed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        })
        evidence["review"] = review
        event.evidence = _redact_evidence(evidence)
        event.status = status
        event_type = event.event_type
        subject_type = event.subject_type
        subject_id = event.subject_id

    await log_audit(
        "fraud_event_review",
        user_id=int(reviewer_id),
        resource_type="FraudEvent",
        resource_id=str(event_id),
        details=f"type={event_type}, subject={subject_type}:{subject_id}, status={status}",
    )
    return True


async def list_invite_retention_snapshots(
        *,
        limit: int = 50,
        offset: int = 0,
) -> dict[str, Any]:
    limit = min(max(int(limit or 50), 1), 100)
    offset = max(int(offset or 0), 0)
    async with Database().session() as s:
        rows = (await s.execute(
            select(InviteRetentionSnapshots)
            .order_by(InviteRetentionSnapshots.activity_at.desc(), InviteRetentionSnapshots.id.desc())
            .offset(offset)
            .limit(limit)
        )).scalars().all()
    return {
        "snapshots": [_invite_retention_snapshot_to_dict(row) for row in rows],
        "limit": limit,
        "offset": offset,
    }


async def platform_dashboard_metrics() -> dict[str, Any]:
    async with Database().session() as s:
        channel_submission_status = await _count_by(s, ChannelSubmissions.status)
        channel_status = await _count_by(s, Channels.status)
        channel_claim_status = await _count_by(s, ChannelClaims.status)
        channel_interaction_action = await _count_by(s, ChannelInteractions.action)
        channel_risk_status = await _count_by(s, Channels.risk_status)
        relay_status = await _count_by(s, RelayProviders.status)
        relay_claim_status = await _count_by(s, RelayClaims.status)
        relay_feedback_type = await _count_by(s, RelayFeedback.feedback_type)
        relay_feedback_status = await _count_by(s, RelayFeedback.status)
        relay_risk_status = await _count_by(s, RelayProviders.risk_status)
        model_job_status = await _count_by(s, ModelTestJobs.status)
        model_report_visibility = await _count_by(s, ModelTestReports.visibility)
        model_report_grade = await _count_by(s, ModelTestReports.grade)
        model_run_status = await _count_by(s, ModelTestRuns.status)
        relay_availability_status = await _count_by(s, RelayAvailabilitySamples.status)
        ledger_account_type = await _count_by(s, LedgerEntries.account_type)
        fraud_status = await _count_by(s, FraudEvents.status)
        fraud_event_type = await _count_by(s, FraudEvents.event_type)
        retention_activity_type = await _count_by(s, InviteRetentionSnapshots.activity_type)
        retention_retained_rows = (await s.execute(
            select(
                func.count(InviteRetentionSnapshots.id),
                func.coalesce(func.sum(func.cast(InviteRetentionSnapshots.retained_7d, Integer)), 0),
            )
        )).one()
        invite_reward_status = await _count_by(s, GroupInviteRewards.status)
        relay_feedback_avg = (await s.execute(
            select(func.avg(RelayFeedback.rating)).where(RelayFeedback.rating.is_not(None))
        )).scalar_one()
        relay_availability_avg_latency = (await s.execute(
            select(func.avg(RelayAvailabilitySamples.latency_ms))
        )).scalar_one()
        relay_availability_http_status = await _count_by(s, RelayAvailabilitySamples.http_status)
        model_run_avg_duration = (await s.execute(
            select(func.avg(ModelTestRuns.duration_ms))
        )).scalar_one()
        model_run_avg_cost = (await s.execute(
            select(func.avg(ModelTestRuns.estimated_cost)).where(ModelTestRuns.estimated_cost.is_not(None))
        )).scalar_one()
        model_run_cost_count = (await s.execute(
            select(func.count(ModelTestRuns.estimated_cost))
        )).scalar_one()
        model_run_totals = (await s.execute(
            select(
                func.coalesce(func.sum(ModelTestRuns.request_count), 0),
                func.coalesce(func.sum(ModelTestRuns.total_tokens), 0),
            )
        )).one()
        ledger_rows = (await s.execute(
            select(LedgerEntries.account_type, LedgerEntries.status, func.coalesce(func.sum(LedgerEntries.amount), 0))
            .group_by(LedgerEntries.account_type, LedgerEntries.status)
        )).all()

    model_total = sum(model_job_status.values())
    model_completed = int(model_job_status.get("completed", 0))
    model_failed = int(model_job_status.get("failed", 0))
    model_run_total = sum(model_run_status.values())
    relay_availability_total = sum(relay_availability_status.values())
    relay_available_total = int(relay_availability_status.get("available", 0))
    channel_submission_total = sum(channel_submission_status.values())
    channel_approved_total = int(channel_status.get("approved", 0))
    relay_total = sum(relay_status.values())
    relay_approved_total = int(relay_status.get("approved", 0))
    coverage_unavailable: list[str] = []
    if relay_availability_total <= 0:
        coverage_unavailable.append("relay.availability")
    if int(model_run_cost_count or 0) <= 0:
        coverage_unavailable.append("model_lab.average_cost")
    if model_run_total <= 0:
        coverage_unavailable.append("model_lab.latency")
    invite_retention_total = int(retention_retained_rows[0] or 0)
    invite_retention_retained = int(retention_retained_rows[1] or 0)
    if invite_retention_total <= 0:
        coverage_unavailable.append("growth.invite_retention")

    return {
        "channels": {
            "submissions": channel_submission_status,
            "submission_total": channel_submission_total,
            "approved_total": channel_approved_total,
            "approval_rate": _ratio(channel_approved_total, channel_submission_total),
            "claims": channel_claim_status,
            "interactions": channel_interaction_action,
            "risk": channel_risk_status,
        },
        "relays": {
            "providers": relay_status,
            "provider_total": relay_total,
            "approved_total": relay_approved_total,
            "approval_rate": _ratio(relay_approved_total, relay_total),
            "claims": relay_claim_status,
            "feedback": {
                "types": relay_feedback_type,
                "statuses": relay_feedback_status,
                "average_rating": float(relay_feedback_avg or 0),
            },
            "risk": relay_risk_status,
            "availability": _relay_availability_metric(
                statuses=relay_availability_status,
                http_statuses=relay_availability_http_status,
                average_latency=relay_availability_avg_latency,
                total=relay_availability_total,
                available=relay_available_total,
            ),
        },
        "model_lab": {
            "jobs": model_job_status,
            "runs": {
                "statuses": model_run_status,
                "run_total": model_run_total,
                "request_count": int(model_run_totals[0] or 0),
                "total_tokens": int(model_run_totals[1] or 0),
            },
            "reports": {
                "visibility": model_report_visibility,
                "grade": model_report_grade,
            },
            "success_rate": _ratio(model_completed, model_total),
            "failure_rate": _ratio(model_failed, model_total),
            "average_cost": _model_average_cost_metric(model_run_avg_cost, int(model_run_cost_count or 0)),
            "latency": _model_latency_metric(model_run_avg_duration, model_run_total),
        },
        "growth": {
            "ledger_entries": ledger_account_type,
            "ledger_totals": [
                {"account_type": account_type, "status": status, "amount": str(Decimal(str(total or 0)).quantize(Decimal("0.01")))}
                for account_type, status, total in ledger_rows
            ],
            "invite_rewards": invite_reward_status,
            "invite_retention": _invite_retention_metric(
                total=invite_retention_total,
                retained=invite_retention_retained,
                activity_type=retention_activity_type,
            ),
        },
        "risk": {
            "fraud_events": {
                "status": fraud_status,
                "event_type": fraud_event_type,
            },
            "ssrf_blocks": int(fraud_event_type.get("ssrf_block", 0)),
            "key_misuse": int(fraud_event_type.get("key_misuse", 0)),
            "bans": int(fraud_event_type.get("ban", 0)),
            "appeals": int(fraud_event_type.get("appeal", 0)),
        },
        "coverage": {
            "unavailable": coverage_unavailable,
        },
    }


async def owner_dashboard(user_id: int) -> dict[str, Any]:
    owner_id = int(user_id)
    if owner_id <= 0:
        raise ValueError("user_id is required")

    async with Database().session() as s:
        channels = (await s.execute(
            select(Channels)
            .where(Channels.owner_user_id == owner_id)
            .order_by(Channels.updated_at.desc(), Channels.id.desc())
        )).scalars().all()
        relays = (await s.execute(
            select(RelayProviders)
            .where(RelayProviders.owner_user_id == owner_id)
            .order_by(RelayProviders.updated_at.desc(), RelayProviders.id.desc())
        )).scalars().all()

        channel_ids = [int(row.id) for row in channels]
        relay_ids = [int(row.id) for row in relays]
        channel_interactions: dict[int, dict[str, int]] = {}
        latest_channel_claims: dict[int, ChannelClaims] = {}
        latest_channel_submissions: dict[int, ChannelSubmissions] = {}
        relay_feedback_counts: dict[int, dict[str, int]] = {}
        relay_average_ratings: dict[int, float] = {}
        latest_relay_claims: dict[int, RelayClaims] = {}

        if channel_ids:
            interaction_rows = (await s.execute(
                select(
                    ChannelInteractions.channel_id,
                    ChannelInteractions.action,
                    func.count(ChannelInteractions.id),
                )
                .where(ChannelInteractions.channel_id.in_(channel_ids))
                .group_by(ChannelInteractions.channel_id, ChannelInteractions.action)
            )).all()
            for channel_id, action, count in interaction_rows:
                channel_interactions.setdefault(int(channel_id), {})[str(action)] = int(count or 0)

            claim_rows = (await s.execute(
                select(ChannelClaims)
                .where(ChannelClaims.channel_id.in_(channel_ids))
                .order_by(ChannelClaims.channel_id.asc(), ChannelClaims.created_at.desc(), ChannelClaims.id.desc())
            )).scalars().all()
            for claim in claim_rows:
                latest_channel_claims.setdefault(int(claim.channel_id), claim)

            submission_rows = (await s.execute(
                select(ChannelSubmissions)
                .where(ChannelSubmissions.channel_id.in_(channel_ids))
                .order_by(ChannelSubmissions.channel_id.asc(), ChannelSubmissions.created_at.desc(), ChannelSubmissions.id.desc())
            )).scalars().all()
            for submission in submission_rows:
                latest_channel_submissions.setdefault(int(submission.channel_id), submission)

        if relay_ids:
            feedback_rows = (await s.execute(
                select(
                    RelayFeedback.provider_id,
                    RelayFeedback.feedback_type,
                    func.count(RelayFeedback.id),
                )
                .where(RelayFeedback.provider_id.in_(relay_ids))
                .group_by(RelayFeedback.provider_id, RelayFeedback.feedback_type)
            )).all()
            for provider_id, feedback_type, count in feedback_rows:
                relay_feedback_counts.setdefault(int(provider_id), {})[str(feedback_type)] = int(count or 0)

            rating_rows = (await s.execute(
                select(RelayFeedback.provider_id, func.avg(RelayFeedback.rating))
                .where(
                    RelayFeedback.provider_id.in_(relay_ids),
                    RelayFeedback.status == "approved",
                    RelayFeedback.rating.is_not(None),
                )
                .group_by(RelayFeedback.provider_id)
            )).all()
            for provider_id, average_rating in rating_rows:
                relay_average_ratings[int(provider_id)] = float(average_rating or 0)

            claim_rows = (await s.execute(
                select(RelayClaims)
                .where(RelayClaims.provider_id.in_(relay_ids))
                .order_by(RelayClaims.provider_id.asc(), RelayClaims.created_at.desc(), RelayClaims.id.desc())
            )).scalars().all()
            for claim in claim_rows:
                latest_relay_claims.setdefault(int(claim.provider_id), claim)

    return {
        "owner": {"user_id": owner_id},
        "channels": {
            "total": len(channels),
            "items": [
                _owner_channel_dashboard_item(
                    row,
                    interactions=channel_interactions.get(int(row.id), {}),
                    claim=latest_channel_claims.get(int(row.id)),
                    submission=latest_channel_submissions.get(int(row.id)),
                )
                for row in channels
            ],
        },
        "relays": {
            "total": len(relays),
            "items": [
                _owner_relay_dashboard_item(
                    row,
                    feedback_counts=relay_feedback_counts.get(int(row.id), {}),
                    average_rating=relay_average_ratings.get(int(row.id), 0),
                    claim=latest_relay_claims.get(int(row.id)),
                )
                for row in relays
            ],
        },
    }


async def admin_owner_dashboards(*, limit: int = 50, offset: int = 0) -> dict[str, Any]:
    limit = min(max(int(limit or 50), 1), 100)
    offset = max(int(offset or 0), 0)

    async with Database().session() as s:
        channel_count_rows = (await s.execute(
            select(Channels.owner_user_id, func.count(Channels.id))
            .where(Channels.owner_user_id.is_not(None))
            .group_by(Channels.owner_user_id)
        )).all()
        relay_count_rows = (await s.execute(
            select(RelayProviders.owner_user_id, func.count(RelayProviders.id))
            .where(RelayProviders.owner_user_id.is_not(None))
            .group_by(RelayProviders.owner_user_id)
        )).all()

        owner_totals: dict[int, dict[str, int]] = {}
        for owner_id, count in channel_count_rows:
            item = owner_totals.setdefault(int(owner_id), {"channels": 0, "relays": 0})
            item["channels"] = int(count or 0)
        for owner_id, count in relay_count_rows:
            item = owner_totals.setdefault(int(owner_id), {"channels": 0, "relays": 0})
            item["relays"] = int(count or 0)

        owner_ids = sorted(
            owner_totals,
            key=lambda item: (-(owner_totals[item]["channels"] + owner_totals[item]["relays"]), item),
        )
        selected_owner_ids = owner_ids[offset:offset + limit]
        owner_data = {
            owner_id: {
                "owner_id": owner_id,
                "resource_total": owner_totals[owner_id]["channels"] + owner_totals[owner_id]["relays"],
                "channels": {
                    "total": owner_totals[owner_id]["channels"],
                    "statuses": {},
                    "risk": {},
                    "interactions": {},
                    "recent": [],
                },
                "relays": {
                    "total": owner_totals[owner_id]["relays"],
                    "statuses": {},
                    "risk": {},
                    "feedback": {"types": {}, "average_rating": 0.0},
                    "recent": [],
                },
            }
            for owner_id in selected_owner_ids
        }

        if selected_owner_ids:
            for owner_id, status, count in (await s.execute(
                select(Channels.owner_user_id, Channels.status, func.count(Channels.id))
                .where(Channels.owner_user_id.in_(selected_owner_ids))
                .group_by(Channels.owner_user_id, Channels.status)
            )).all():
                owner_data[int(owner_id)]["channels"]["statuses"][str(status or "")] = int(count or 0)

            for owner_id, risk_status, count in (await s.execute(
                select(Channels.owner_user_id, Channels.risk_status, func.count(Channels.id))
                .where(Channels.owner_user_id.in_(selected_owner_ids))
                .group_by(Channels.owner_user_id, Channels.risk_status)
            )).all():
                owner_data[int(owner_id)]["channels"]["risk"][str(risk_status or "")] = int(count or 0)

            for owner_id, action, count in (await s.execute(
                select(Channels.owner_user_id, ChannelInteractions.action, func.count(ChannelInteractions.id))
                .select_from(ChannelInteractions)
                .join(Channels, ChannelInteractions.channel_id == Channels.id)
                .where(Channels.owner_user_id.in_(selected_owner_ids))
                .group_by(Channels.owner_user_id, ChannelInteractions.action)
            )).all():
                owner_data[int(owner_id)]["channels"]["interactions"][str(action or "")] = int(count or 0)

            for owner_id, status, count in (await s.execute(
                select(RelayProviders.owner_user_id, RelayProviders.status, func.count(RelayProviders.id))
                .where(RelayProviders.owner_user_id.in_(selected_owner_ids))
                .group_by(RelayProviders.owner_user_id, RelayProviders.status)
            )).all():
                owner_data[int(owner_id)]["relays"]["statuses"][str(status or "")] = int(count or 0)

            for owner_id, risk_status, count in (await s.execute(
                select(RelayProviders.owner_user_id, RelayProviders.risk_status, func.count(RelayProviders.id))
                .where(RelayProviders.owner_user_id.in_(selected_owner_ids))
                .group_by(RelayProviders.owner_user_id, RelayProviders.risk_status)
            )).all():
                owner_data[int(owner_id)]["relays"]["risk"][str(risk_status or "")] = int(count or 0)

            for owner_id, feedback_type, count in (await s.execute(
                select(RelayProviders.owner_user_id, RelayFeedback.feedback_type, func.count(RelayFeedback.id))
                .select_from(RelayFeedback)
                .join(RelayProviders, RelayFeedback.provider_id == RelayProviders.id)
                .where(RelayProviders.owner_user_id.in_(selected_owner_ids))
                .group_by(RelayProviders.owner_user_id, RelayFeedback.feedback_type)
            )).all():
                owner_data[int(owner_id)]["relays"]["feedback"]["types"][str(feedback_type or "")] = int(count or 0)

            for owner_id, average_rating in (await s.execute(
                select(RelayProviders.owner_user_id, func.avg(RelayFeedback.rating))
                .select_from(RelayFeedback)
                .join(RelayProviders, RelayFeedback.provider_id == RelayProviders.id)
                .where(
                    RelayProviders.owner_user_id.in_(selected_owner_ids),
                    RelayFeedback.status == "approved",
                    RelayFeedback.rating.is_not(None),
                )
                .group_by(RelayProviders.owner_user_id)
            )).all():
                owner_data[int(owner_id)]["relays"]["feedback"]["average_rating"] = round(float(average_rating or 0), 2)

            channels = (await s.execute(
                select(Channels)
                .where(Channels.owner_user_id.in_(selected_owner_ids))
                .order_by(Channels.owner_user_id.asc(), Channels.updated_at.desc(), Channels.id.desc())
            )).scalars().all()
            for channel in channels:
                recent = owner_data[int(channel.owner_user_id)]["channels"]["recent"]
                if len(recent) < 5:
                    recent.append(_channel_to_public_detail_dict(channel))

            relays = (await s.execute(
                select(RelayProviders)
                .where(RelayProviders.owner_user_id.in_(selected_owner_ids))
                .order_by(RelayProviders.owner_user_id.asc(), RelayProviders.updated_at.desc(), RelayProviders.id.desc())
            )).scalars().all()
            for provider in relays:
                recent = owner_data[int(provider.owner_user_id)]["relays"]["recent"]
                if len(recent) < 5:
                    recent.append(_relay_public_detail_to_dict(provider))

    return {
        "owners": [owner_data[owner_id] for owner_id in selected_owner_ids],
        "total": len(owner_ids),
        "limit": limit,
        "offset": offset,
        "has_more": offset + len(selected_owner_ids) < len(owner_ids),
    }


async def admin_review_workload_metrics() -> dict[str, Any]:
    reviewers: dict[str, dict[str, Any]] = {}
    queues = {
        "channel_reports": _empty_workload_queue(),
        "relay_feedback": _empty_workload_queue(),
    }

    async with Database().session() as s:
        channel_rows = (await s.execute(
            select(
                Channels.risk_assigned_to,
                Channels.risk_escalation,
                Channels.risk_status,
                func.count(Channels.id),
            )
            .where(Channels.risk_status.in_(tuple(REVIEW_WORKLOAD_OPEN_CHANNEL_RISKS)))
            .group_by(Channels.risk_assigned_to, Channels.risk_escalation, Channels.risk_status)
        )).all()
        feedback_rows = (await s.execute(
            select(
                RelayFeedback.assigned_to,
                RelayFeedback.escalation,
                RelayFeedback.status,
                RelayFeedback.feedback_type,
                func.count(RelayFeedback.id),
            )
            .where(RelayFeedback.status.in_(tuple(REVIEW_WORKLOAD_OPEN_FEEDBACK_STATUSES)))
            .group_by(RelayFeedback.assigned_to, RelayFeedback.escalation, RelayFeedback.status, RelayFeedback.feedback_type)
        )).all()

    for assigned_to, escalation, status, count in channel_rows:
        _accumulate_workload(
            queues["channel_reports"],
            reviewers,
            queue_id="channel_reports",
            assigned_to=assigned_to,
            escalation=escalation,
            status=status,
            count=count,
        )

    for assigned_to, escalation, status, feedback_type, count in feedback_rows:
        _accumulate_workload(
            queues["relay_feedback"],
            reviewers,
            queue_id="relay_feedback",
            assigned_to=assigned_to,
            escalation=escalation,
            status=status,
            count=count,
            feedback_type=feedback_type,
        )

    reviewer_rows = sorted(
        reviewers.values(),
        key=lambda item: (item["reviewer_id"] is not None, -int(item["open_total"]), str(item["reviewer_id"] or "")),
    )
    summary = {
        "open_total": sum(queue["open_total"] for queue in queues.values()),
        "unassigned_total": sum(queue["unassigned_total"] for queue in queues.values()),
        "urgent_total": sum(queue["by_escalation"].get("urgent", 0) for queue in queues.values()),
        "reviewer_count": sum(1 for item in reviewer_rows if item["reviewer_id"] is not None),
    }
    return {
        "summary": summary,
        "thresholds": {
            "open_warning_per_reviewer": REVIEW_WORKLOAD_OPEN_WARNING_THRESHOLD,
            "urgent_attention": REVIEW_WORKLOAD_URGENT_THRESHOLD,
        },
        "queues": queues,
        "reviewers": reviewer_rows,
        "alerts": _review_workload_alerts(summary, reviewer_rows),
        "coverage": {
            "assignment_sources": [
                "channels.risk_assigned_to",
                "channels.risk_escalation",
                "relay_feedback.assigned_to",
                "relay_feedback.escalation",
            ],
            "open_statuses": {
                "channel_reports": sorted(REVIEW_WORKLOAD_OPEN_CHANNEL_RISKS),
                "relay_feedback": sorted(REVIEW_WORKLOAD_OPEN_FEEDBACK_STATUSES),
            },
        },
    }


async def list_platform_audit_logs(
        *,
        action: str = "",
        resource_type: str = "",
        resource_id: str = "",
        user_id: int | str | None = None,
        level: str = "",
        query: str = "",
        limit: int = 50,
        offset: int = 0,
) -> dict[str, Any]:
    limit = min(max(int(limit or 50), 1), 100)
    offset = max(int(offset or 0), 0)
    action = _safe_summary(action, max_len=64).strip()
    resource_type = _safe_summary(resource_type, max_len=32).strip()
    resource_id = _safe_summary(resource_id, max_len=128).strip()
    level = _safe_summary(level, max_len=8).strip().upper()
    query = _safe_summary(query, max_len=120).strip()
    user_id_filter = _optional_positive_int(user_id)

    async with Database().session() as s:
        stmt = select(AuditLog)
        if action:
            stmt = stmt.where(AuditLog.action == action)
        if resource_type:
            stmt = stmt.where(AuditLog.resource_type == resource_type)
        if resource_id:
            stmt = stmt.where(AuditLog.resource_id == resource_id)
        if user_id_filter is not None:
            stmt = stmt.where(AuditLog.user_id == user_id_filter)
        if level:
            stmt = stmt.where(AuditLog.level == level)
        if query:
            like = f"%{query.lower()}%"
            stmt = stmt.where(or_(
                func.lower(AuditLog.action).like(like),
                func.lower(AuditLog.resource_type).like(like),
                func.lower(AuditLog.resource_id).like(like),
                func.lower(AuditLog.details).like(like),
            ))
        total = (await s.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
        rows = (await s.execute(
            stmt.order_by(AuditLog.timestamp.desc(), AuditLog.id.desc())
            .offset(offset)
            .limit(limit)
        )).scalars().all()

    return {
        "logs": [_audit_log_admin_to_dict(row) for row in rows],
        "total": int(total or 0),
        "limit": limit,
        "offset": offset,
        "has_more": offset + len(rows) < int(total or 0),
        "filters": {
            "action": action,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "user_id": user_id_filter,
            "level": level,
            "q": query,
        },
    }


def _clean_text(value: Any, field: str, max_len: int, *, allow_empty: bool = False) -> str:
    text = str(value or "").strip()
    if not text and not allow_empty:
        raise ValueError(f"{field} is required")
    if len(text) > max_len:
        raise ValueError(f"{field} exceeds {max_len} chars")
    return text


def _empty_workload_queue() -> dict[str, Any]:
    return {
        "open_total": 0,
        "unassigned_total": 0,
        "by_status": {},
        "by_escalation": {},
        "by_feedback_type": {},
    }


def _accumulate_workload(
        queue: dict[str, Any],
        reviewers: dict[str, dict[str, Any]],
        *,
        queue_id: str,
        assigned_to: Any,
        escalation: Any,
        status: Any,
        count: Any,
        feedback_type: Any = "",
) -> None:
    amount = int(count or 0)
    if amount <= 0:
        return
    escalation_key = str(escalation or "none")
    status_key = str(status or "")
    assigned_value = _optional_positive_int(assigned_to)
    reviewer_key = str(assigned_value) if assigned_value is not None else "unassigned"

    queue["open_total"] += amount
    if assigned_value is None:
        queue["unassigned_total"] += amount
    queue["by_status"][status_key] = int(queue["by_status"].get(status_key, 0)) + amount
    queue["by_escalation"][escalation_key] = int(queue["by_escalation"].get(escalation_key, 0)) + amount
    if feedback_type:
        feedback_key = str(feedback_type or "")
        queue["by_feedback_type"][feedback_key] = int(queue["by_feedback_type"].get(feedback_key, 0)) + amount

    reviewer = reviewers.setdefault(
        reviewer_key,
        {
            "reviewer_id": assigned_value,
            "open_total": 0,
            "queues": {},
            "escalations": {},
        },
    )
    reviewer["open_total"] += amount
    reviewer["queues"][queue_id] = int(reviewer["queues"].get(queue_id, 0)) + amount
    reviewer["escalations"][escalation_key] = int(reviewer["escalations"].get(escalation_key, 0)) + amount


def _review_workload_alerts(summary: dict[str, Any], reviewers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []
    unassigned_total = int(summary.get("unassigned_total") or 0)
    urgent_total = int(summary.get("urgent_total") or 0)
    if unassigned_total >= REVIEW_WORKLOAD_OPEN_WARNING_THRESHOLD:
        alerts.append({
            "type": "unassigned_backlog",
            "severity": "warning",
            "count": unassigned_total,
            "threshold": REVIEW_WORKLOAD_OPEN_WARNING_THRESHOLD,
        })
    if urgent_total >= REVIEW_WORKLOAD_URGENT_THRESHOLD:
        alerts.append({
            "type": "urgent_escalation",
            "severity": "urgent",
            "count": urgent_total,
            "threshold": REVIEW_WORKLOAD_URGENT_THRESHOLD,
        })
    for reviewer in reviewers:
        reviewer_id = reviewer.get("reviewer_id")
        if reviewer_id is None:
            continue
        open_total = int(reviewer.get("open_total") or 0)
        if open_total >= REVIEW_WORKLOAD_OPEN_WARNING_THRESHOLD:
            alerts.append({
                "type": "reviewer_over_threshold",
                "severity": "warning",
                "reviewer_id": reviewer_id,
                "count": open_total,
                "threshold": REVIEW_WORKLOAD_OPEN_WARNING_THRESHOLD,
            })
    return alerts


async def _count_by(session, column) -> dict[str, int]:
    rows = (await session.execute(
        select(column, func.count()).group_by(column)
    )).all()
    return {str(key or ""): int(count or 0) for key, count in rows}


def _ratio(numerator: int, denominator: int) -> float:
    denominator = int(denominator or 0)
    if denominator <= 0:
        return 0.0
    return round(int(numerator or 0) / denominator, 4)


def _metric_unavailable(reason: str) -> dict[str, str]:
    return {"status": "unavailable", "reason": reason}


def _invite_retention_metric(total: int, retained: int, activity_type: dict[str, int]) -> dict[str, Any]:
    if total <= 0:
        return _metric_unavailable("7-day invite retention needs persisted invite activity snapshots.")
    return {
        "status": "tracked",
        "snapshot_total": int(total),
        "retained_7d": int(retained),
        "retention_rate": _ratio(retained, total),
        "activity_type": activity_type,
    }


def _model_latency_metric(average_duration: Any, sample_count: int) -> dict[str, Any]:
    if int(sample_count or 0) <= 0:
        return _metric_unavailable("Worker latency samples are not stored yet.")
    return {
        "status": "tracked",
        "sample_count": int(sample_count or 0),
        "average_duration_ms": int(float(average_duration or 0)),
    }


def _model_average_cost_metric(average_cost: Any, sample_count: int) -> dict[str, Any]:
    if int(sample_count or 0) <= 0:
        return _metric_unavailable("Model-test cost accounting is not tracked yet.")
    return {
        "status": "tracked",
        "sample_count": int(sample_count or 0),
        "average_cost": str(Decimal(str(average_cost or 0)).quantize(Decimal("0.000001"))),
    }


def _relay_availability_metric(
        *,
        statuses: dict[str, int],
        http_statuses: dict[str, int],
        average_latency: Any,
        total: int,
        available: int,
) -> dict[str, Any]:
    if int(total or 0) <= 0:
        return _metric_unavailable("Relay availability history is not tracked yet.")
    return {
        "status": "tracked",
        "sample_count": int(total or 0),
        "availability_rate": _ratio(int(available or 0), int(total or 0)),
        "statuses": statuses,
        "http_statuses": http_statuses,
        "average_latency_ms": int(float(average_latency or 0)),
    }


def _extract_model_run_metrics(report_data: dict[str, Any]) -> dict[str, Any]:
    suite = _report_suite(report_data)
    request_count = sum(1 for item in suite if _item_http_status(item) is not None)
    total_tokens = 0
    for item in suite:
        metadata = item.get("metadata") if isinstance(item, dict) else None
        if not isinstance(metadata, dict):
            continue
        usage = metadata.get("usage") if isinstance(metadata.get("usage"), dict) else None
        if usage and isinstance(usage.get("total_tokens"), int | float):
            total_tokens += int(usage["total_tokens"])
    return {
        "request_count": request_count,
        "total_tokens": total_tokens,
        "estimated_cost": report_data.get("estimated_cost"),
    }


def _extract_relay_availability_metrics(
        report_data: dict[str, Any],
        *,
        fallback_latency_ms: int,
        status: str,
        error_type: str,
        error_summary: str,
) -> dict[str, Any]:
    suite = _report_suite(report_data)
    latencies = [_item_latency(item) for item in suite]
    latencies = [value for value in latencies if value is not None]
    statuses = [_item_http_status(item) for item in suite]
    statuses = [value for value in statuses if value is not None]
    failed_items = [
        item for item in suite
        if isinstance(item, dict) and item.get("status") == "failed"
    ]
    warning_items = [
        item for item in suite
        if isinstance(item, dict) and item.get("status") == "warning"
    ]
    if status == "completed" and suite:
        if failed_items:
            availability_status = "failed"
        elif warning_items:
            availability_status = "degraded"
        else:
            availability_status = "available"
    elif status == "completed":
        availability_status = "unknown"
    else:
        availability_status = "failed"
    summary = error_summary
    if not summary and failed_items:
        summary = _safe_summary(failed_items[0].get("summary", ""))
    return {
        "status": availability_status,
        "http_status": statuses[0] if statuses else None,
        "latency_ms": int(sum(latencies) / len(latencies)) if latencies else max(0, int(fallback_latency_ms or 0)),
        "error_type": error_type,
        "error_summary": summary,
    }


def _report_suite(report_data: dict[str, Any]) -> list[dict[str, Any]]:
    evidence = report_data.get("evidence_json") if isinstance(report_data, dict) else None
    suite = evidence.get("suite") if isinstance(evidence, dict) else None
    return [item for item in suite if isinstance(item, dict)] if isinstance(suite, list) else []


def _item_http_status(item: dict[str, Any]) -> int | None:
    metadata = item.get("metadata") if isinstance(item, dict) else None
    if not isinstance(metadata, dict):
        return None
    value = metadata.get("status_code")
    return int(value) if isinstance(value, int | float) else None


def _item_latency(item: dict[str, Any]) -> int | None:
    metadata = item.get("metadata") if isinstance(item, dict) else None
    if not isinstance(metadata, dict):
        return None
    value = metadata.get("latency_ms")
    return int(value) if isinstance(value, int | float) else None


def _redact_evidence(value: dict[str, Any]) -> dict[str, Any]:
    return _redact_evidence_value(value)


def _redact_text(value: str) -> str:
    text = str(value or "")
    text = re.sub(r"Bearer\s+[A-Za-z0-9._~+/=-]+", "Bearer [redacted]", text, flags=re.IGNORECASE)
    text = re.sub(r"(?i)(api[_-]?key|access_token|token|secret|password)=([^&\s]+)", r"\1=[redacted]", text)
    text = re.sub(r"sk-[A-Za-z0-9._~+/=-]{6,}", "sk-[redacted]", text)
    return text


def _safe_summary(value: Any, max_len: int = 255) -> str:
    return _redact_text(str(value or ""))[:max_len]


def _redact_evidence_value(value: Any, key: str = "") -> Any:
    lowered = str(key).lower()
    if isinstance(value, dict):
        return {item_key: _redact_evidence_value(item, str(item_key)) for item_key, item in value.items()}
    if isinstance(value, list):
        return [_redact_evidence_value(item, key) for item in value]
    if any(marker in lowered for marker in ("api_key", "token", "secret", "password", "authorization")):
        return mask_secret(str(value))
    if isinstance(value, str) and any(marker in value.lower() for marker in ("bearer ", "sk-", "api_key=")):
        return "[redacted]"
    return value


def _fraud_event_to_dict(event: FraudEvents) -> dict[str, Any]:
    return {
        "id": event.id,
        "subject_type": event.subject_type,
        "subject_id": event.subject_id,
        "event_type": event.event_type,
        "evidence": _redact_evidence(event.evidence or {}),
        "score_delta": int(event.score_delta or 0),
        "status": event.status,
        "created_at": event.created_at.isoformat() if event.created_at else "",
    }


def _channel_to_dict(channel: Channels) -> dict[str, Any]:
    return {
        "id": channel.id,
        "username": channel.username,
        "title": channel.title,
        "category": channel.category,
        "language": channel.language,
        "description": channel.description,
        "status": channel.status,
        "quality_score": float(channel.quality_score or 0),
        "risk_status": channel.risk_status,
    }


def _channel_to_public_detail_dict(channel: Channels) -> dict[str, Any]:
    data = _channel_to_dict(channel)
    data["url"] = f"https://t.me/{channel.username}"
    data["owner_verified"] = channel.owner_user_id is not None
    data["created_at"] = channel.created_at.isoformat() if channel.created_at else ""
    data["updated_at"] = channel.updated_at.isoformat() if channel.updated_at else ""
    return data


def _channel_admin_to_dict(channel: Channels) -> dict[str, Any]:
    data = _channel_to_public_detail_dict(channel)
    data.update({
        "telegram_chat_id": channel.telegram_chat_id,
        "owner_user_id": channel.owner_user_id,
        "risk_notes": channel.risk_notes,
        "risk_reviewed_by": channel.risk_reviewed_by,
        "risk_reviewed_at": channel.risk_reviewed_at.isoformat() if channel.risk_reviewed_at else "",
        "risk_assigned_to": channel.risk_assigned_to,
        "risk_escalation": channel.risk_escalation,
    })
    return data


def _channel_submission_to_dict(channel: Channels, submission: ChannelSubmissions, *, duplicate: bool) -> dict[str, Any]:
    return {"channel": _channel_to_dict(channel), "submission": {"id": submission.id, "status": submission.status, "duplicate": duplicate}}


def _channel_submission_row_to_dict(submission: ChannelSubmissions) -> dict[str, Any]:
    return {
        "id": submission.id,
        "submitter_id": submission.submitter_id,
        "channel_id": submission.channel_id,
        "reason": submission.reason,
        "commercial_content": submission.commercial_content,
        "submitter_relation": submission.submitter_relation,
        "status": submission.status,
        "review_notes": submission.review_notes,
        "reviewed_by": submission.reviewed_by,
        "created_at": submission.created_at.isoformat() if submission.created_at else "",
    }


def _channel_claim_to_dict(claim: ChannelClaims) -> dict[str, Any]:
    data = {
        "id": claim.id,
        "channel_id": claim.channel_id,
        "claimant_id": claim.claimant_id,
        "method": claim.method,
        "status": claim.status,
        "verified_at": claim.verified_at.isoformat() if claim.verified_at else "",
        "created_at": claim.created_at.isoformat() if claim.created_at else "",
    }
    data["verification"] = _channel_claim_verification_to_dict(claim)
    return data


def _channel_claim_public_status(claim: ChannelClaims | None) -> dict[str, Any]:
    if not claim:
        return {"status": "unclaimed", "method": "", "verified_at": ""}
    return {
        "status": claim.status,
        "method": claim.method,
        "verified_at": claim.verified_at.isoformat() if claim.verified_at else "",
    }


def _channel_submission_detail_to_dict(submission: ChannelSubmissions) -> dict[str, Any]:
    return {
        "id": submission.id,
        "submitter_id": submission.submitter_id,
        "channel_id": submission.channel_id,
        "reason": submission.reason,
        "commercial_content": submission.commercial_content,
        "submitter_relation": submission.submitter_relation,
        "status": submission.status,
        "review_notes": submission.review_notes,
        "reviewed_by": submission.reviewed_by,
        "reviewed_at": submission.reviewed_at.isoformat() if submission.reviewed_at else "",
        "created_at": submission.created_at.isoformat() if submission.created_at else "",
        "updated_at": submission.updated_at.isoformat() if submission.updated_at else "",
    }


def _channel_claim_detail_to_dict(claim: ChannelClaims) -> dict[str, Any]:
    return {
        "id": claim.id,
        "channel_id": claim.channel_id,
        "claimant_id": claim.claimant_id,
        "method": claim.method,
        "challenge": claim.challenge,
        "verification": _channel_claim_verification_to_dict(claim),
        "status": claim.status,
        "verified_at": claim.verified_at.isoformat() if claim.verified_at else "",
        "created_at": claim.created_at.isoformat() if claim.created_at else "",
    }


def _channel_claim_public_detail_to_dict(claim: ChannelClaims) -> dict[str, Any]:
    return {
        "id": claim.id,
        "channel_id": claim.channel_id,
        "claimant_id": claim.claimant_id,
        "method": claim.method,
        "status": claim.status,
        "verification": {
            "challenge_required": claim.method in {"challenge", "manual"},
            "challenge_provided": bool(claim.challenge),
        },
        "verified_at": claim.verified_at.isoformat() if claim.verified_at else "",
        "created_at": claim.created_at.isoformat() if claim.created_at else "",
    }


def _owner_channel_dashboard_item(
        channel: Channels,
        *,
        interactions: dict[str, int],
        claim: ChannelClaims | None,
        submission: ChannelSubmissions | None,
) -> dict[str, Any]:
    return {
        "channel": _channel_to_public_detail_dict(channel),
        "interactions": {
            "favorite": int(interactions.get("favorite", 0)),
            "hide": int(interactions.get("hide", 0)),
            "click": int(interactions.get("click", 0)),
            "report": int(interactions.get("report", 0)),
        },
        "latest_claim": _channel_claim_public_status(claim),
        "latest_submission": {
            "id": submission.id,
            "status": submission.status,
            "created_at": submission.created_at.isoformat() if submission.created_at else "",
            "updated_at": submission.updated_at.isoformat() if submission.updated_at else "",
        } if submission else {"id": None, "status": "", "created_at": "", "updated_at": ""},
    }


def _channel_claim_verification_to_dict(claim: ChannelClaims, channel: Channels | None = None) -> dict[str, Any]:
    if claim.method == "bot_admin":
        return {
            "method": claim.method,
            "admin_rights_required": True,
            "challenge": "",
            "expected_text": "",
            "instruction": "Verify the claimant has Telegram channel administrator rights before approval.",
        }
    if claim.method == "manual":
        return {
            "method": claim.method,
            "admin_rights_required": False,
            "challenge": claim.challenge,
            "expected_text": "",
            "instruction": "Use manual evidence review as fallback when Bot admin verification is unavailable.",
        }
    username = f"@{channel.username}" if channel is not None and channel.username else "the channel"
    return {
        "method": claim.method,
        "admin_rights_required": False,
        "challenge": claim.challenge,
        "expected_text": f"TGSellBot claim {claim.challenge}",
        "instruction": f"Ask the claimant to publish the expected text in {username} or a channel admin-visible location.",
    }


def _audit_log_public_to_dict(entry: AuditLog) -> dict[str, Any]:
    return {
        "id": entry.id,
        "timestamp": entry.timestamp.isoformat() if entry.timestamp else "",
        "level": entry.level,
        "action": entry.action,
        "resource_type": entry.resource_type,
        "resource_id": entry.resource_id,
        "details": _safe_summary(entry.details, max_len=1000),
    }


def _audit_log_admin_to_dict(entry: AuditLog) -> dict[str, Any]:
    data = _audit_log_public_to_dict(entry)
    data["user_id"] = int(entry.user_id) if entry.user_id is not None else None
    return data


def _relay_to_dict(provider: RelayProviders, *, duplicate: bool) -> dict[str, Any]:
    return {
        "id": provider.id,
        "name": provider.name,
        "base_url": provider.public_base_url,
        "protocol": provider.protocol,
        "status": provider.status,
        "risk_status": provider.risk_status,
        "duplicate": duplicate,
    }


def _relay_public_to_dict(provider: RelayProviders) -> dict[str, Any]:
    return {
        "id": provider.id,
        "name": provider.name,
        "base_url": provider.public_base_url,
        "protocol": provider.protocol,
        "model_scope": provider.model_scope,
        "region": provider.region,
        "pricing": provider.pricing,
        "status": provider.status,
        "risk_status": provider.risk_status,
        "reputation_score": float(provider.reputation_score or 0),
        "owner_verified": provider.owner_user_id is not None,
    }


def _relay_public_detail_to_dict(provider: RelayProviders) -> dict[str, Any]:
    data = _relay_public_to_dict(provider)
    data["website_url"] = provider.website_url
    data["created_at"] = provider.created_at.isoformat() if provider.created_at else ""
    data["updated_at"] = provider.updated_at.isoformat() if provider.updated_at else ""
    return data


def _relay_claim_to_dict(claim: RelayClaims) -> dict[str, Any]:
    data = {
        "id": claim.id,
        "provider_id": claim.provider_id,
        "claimant_id": claim.claimant_id,
        "method": claim.method,
        "status": claim.status,
        "verified_at": claim.verified_at.isoformat() if claim.verified_at else "",
        "created_at": claim.created_at.isoformat() if claim.created_at else "",
    }
    data["verification"] = _relay_claim_verification_to_dict(claim)
    return data


def _relay_claim_public_status(claim: RelayClaims | None) -> dict[str, Any]:
    if not claim:
        return {"status": "unclaimed", "method": "", "verified_at": ""}
    return {
        "status": claim.status,
        "method": claim.method,
        "verified_at": claim.verified_at.isoformat() if claim.verified_at else "",
    }


def _relay_claim_detail_to_dict(claim: RelayClaims) -> dict[str, Any]:
    return {
        "id": claim.id,
        "provider_id": claim.provider_id,
        "claimant_id": claim.claimant_id,
        "method": claim.method,
        "challenge": claim.challenge,
        "verification": _relay_claim_verification_to_dict(claim),
        "status": claim.status,
        "verified_at": claim.verified_at.isoformat() if claim.verified_at else "",
        "created_at": claim.created_at.isoformat() if claim.created_at else "",
    }


def _relay_claim_public_detail_to_dict(claim: RelayClaims) -> dict[str, Any]:
    return {
        "id": claim.id,
        "provider_id": claim.provider_id,
        "claimant_id": claim.claimant_id,
        "method": claim.method,
        "status": claim.status,
        "verification": {
            "challenge_required": claim.method in {"domain", "challenge", "manual"},
            "challenge_provided": bool(claim.challenge),
        },
        "verified_at": claim.verified_at.isoformat() if claim.verified_at else "",
        "created_at": claim.created_at.isoformat() if claim.created_at else "",
    }


def _owner_relay_dashboard_item(
        provider: RelayProviders,
        *,
        feedback_counts: dict[str, int],
        average_rating: float,
        claim: RelayClaims | None,
) -> dict[str, Any]:
    return {
        "provider": _relay_public_detail_to_dict(provider),
        "feedback": {
            "counts": {
                "rating": int(feedback_counts.get("rating", 0)),
                "complaint": int(feedback_counts.get("complaint", 0)),
                "owner_response": int(feedback_counts.get("owner_response", 0)),
            },
            "average_rating": round(float(average_rating or 0), 2),
        },
        "latest_claim": _relay_claim_public_status(claim),
    }


def _relay_claim_verification_to_dict(claim: RelayClaims, provider: RelayProviders | None = None) -> dict[str, Any]:
    public_url = provider.public_base_url if provider is not None else ""
    provider_name = provider.name if provider is not None else "the relay provider"
    if claim.method == "domain":
        return {
            "method": claim.method,
            "domain_control_required": True,
            "challenge": claim.challenge,
            "expected_text": f"tgsellbot-relay-claim={claim.challenge}",
            "instruction": f"Verify the expected text through DNS TXT, a well-known HTTPS path, or the official site for {provider_name}.",
        }
    if claim.method == "manual":
        return {
            "method": claim.method,
            "domain_control_required": False,
            "challenge": claim.challenge,
            "expected_text": "",
            "instruction": "Use manual evidence review as fallback when domain verification is unavailable.",
        }
    return {
        "method": claim.method,
        "domain_control_required": False,
        "challenge": claim.challenge,
        "expected_text": f"TGSellBot relay claim {claim.challenge}",
        "instruction": f"Ask the claimant to publish the expected text on the relay site or owner-visible channel for {public_url or provider_name}.",
    }


def _relay_feedback_to_dict(feedback: RelayFeedback) -> dict[str, Any]:
    return {
        "id": feedback.id,
        "provider_id": feedback.provider_id,
        "user_id": feedback.user_id,
        "feedback_type": feedback.feedback_type,
        "rating": feedback.rating,
        "text": feedback.text,
        "status": feedback.status,
        "review_notes": feedback.review_notes,
        "reviewed_by": feedback.reviewed_by,
        "reviewed_at": feedback.reviewed_at.isoformat() if feedback.reviewed_at else "",
        "assigned_to": feedback.assigned_to,
        "escalation": feedback.escalation,
        "outcome": feedback.outcome,
        "followup_notes": feedback.followup_notes,
        "resolved_by": feedback.resolved_by,
        "resolved_at": feedback.resolved_at.isoformat() if feedback.resolved_at else "",
        "created_at": feedback.created_at.isoformat() if feedback.created_at else "",
    }


def _relay_feedback_public_to_dict(feedback: RelayFeedback) -> dict[str, Any]:
    return {
        "id": feedback.id,
        "feedback_type": feedback.feedback_type,
        "rating": feedback.rating,
        "text": feedback.text,
        "created_at": feedback.created_at.isoformat() if feedback.created_at else "",
    }


def _model_test_run_to_dict(run: ModelTestRuns) -> dict[str, Any]:
    return {
        "id": run.id,
        "job_id": run.job_id,
        "provider_id": run.provider_id,
        "worker_id": run.worker_id,
        "status": run.status,
        "duration_ms": run.duration_ms,
        "request_count": run.request_count,
        "total_tokens": run.total_tokens,
        "estimated_cost": str(Decimal(str(run.estimated_cost)).quantize(Decimal("0.000001"))) if run.estimated_cost is not None else "",
        "error_type": run.error_type,
        "error_summary": run.error_summary,
        "created_at": run.created_at.isoformat() if run.created_at else "",
    }


def _relay_availability_sample_to_dict(sample: RelayAvailabilitySamples) -> dict[str, Any]:
    return {
        "id": sample.id,
        "provider_id": sample.provider_id,
        "job_id": sample.job_id,
        "source": sample.source,
        "status": sample.status,
        "http_status": sample.http_status,
        "latency_ms": sample.latency_ms,
        "error_type": sample.error_type,
        "error_summary": sample.error_summary,
        "checked_at": sample.checked_at.isoformat() if sample.checked_at else "",
        "created_at": sample.created_at.isoformat() if sample.created_at else "",
    }


def _job_to_dict(job: ModelTestJobs, *, duplicate: bool, report: ModelTestReports | None = None) -> dict[str, Any]:
    report_summary = None
    if report:
        report_summary = {
            "id": report.id,
            "job_id": report.job_id,
            "declared_model": report.declared_model,
            "returned_model": report.returned_model,
            "suite_version": report.suite_version,
            "grade": report.grade,
            "visibility": report.visibility,
            "limitation_note": report.limitation_note,
            "created_at": report.created_at.isoformat() if report.created_at else "",
            "updated_at": report.updated_at.isoformat() if report.updated_at else "",
        }
    return {
        "id": job.id,
        "user_id": job.user_id,
        "status": job.status,
        "worker_id": job.worker_id,
        "failure_reason": job.failure_reason,
        "endpoint": job.endpoint_public,
        "protocol": job.protocol,
        "requested_model": job.requested_model,
        "idempotency_key": job.idempotency_key,
        "key_fingerprint": job.key_fingerprint,
        "key_masked": job.key_masked,
        "duplicate": duplicate,
        "created_at": job.created_at.isoformat() if job.created_at else "",
        "updated_at": job.updated_at.isoformat() if job.updated_at else "",
        "report": report_summary,
    }


def _report_to_dict(report: ModelTestReports, job: ModelTestJobs, *, runs: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "id": report.id,
        "job_id": report.job_id,
        "user_id": job.user_id,
        "declared_model": report.declared_model,
        "returned_model": report.returned_model,
        "suite_version": report.suite_version,
        "scores": report.scores,
        "grade": report.grade,
        "evidence_json": report.evidence_json,
        "visibility": report.visibility,
        "limitation_note": report.limitation_note,
        "created_at": report.created_at.isoformat() if report.created_at else "",
        "updated_at": report.updated_at.isoformat() if report.updated_at else "",
        "job": _job_to_dict(job, duplicate=False),
        "runs": runs or [],
    }


def _public_report_to_dict(
        report: ModelTestReports,
        job: ModelTestJobs,
        *,
        token_secret: str = "",
        runs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    share_token = model_test_report_share_token(report.id, job.user_id, job.id, token_secret)
    return {
        "id": report.id,
        "job_id": report.job_id,
        "declared_model": report.declared_model,
        "returned_model": report.returned_model,
        "suite_version": report.suite_version,
        "scores": report.scores,
        "grade": report.grade,
        "evidence_json": report.evidence_json,
        "visibility": report.visibility,
        "limitation_note": report.limitation_note,
        "created_at": report.created_at.isoformat() if report.created_at else "",
        "updated_at": report.updated_at.isoformat() if report.updated_at else "",
        "share_token": share_token if report.visibility == "unlisted" else "",
        "job": {
            "id": job.id,
            "status": job.status,
            "endpoint": job.endpoint_public,
            "protocol": job.protocol,
            "requested_model": job.requested_model,
            "created_at": job.created_at.isoformat() if job.created_at else "",
            "updated_at": job.updated_at.isoformat() if job.updated_at else "",
        },
        "runs": runs or [],
    }
