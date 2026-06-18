# TGSellBot Testing Guide

This repository uses pytest with `pytest-asyncio`, async SQLite fixtures, real SQLAlchemy queries, fake cache behavior, and mocked external APIs.

## Baseline Commands

Use the local venv when available:

```powershell
.\.venv312\Scripts\python.exe -m pytest -q
git diff --check
```

Fallback:

```powershell
py -3.12 -m pytest -q
git diff --check
```

`pytest.ini` already enables coverage for `bot` with `--cov=bot --cov-report=term-missing`.

## Fix-Verify Loop

1. Reproduce the issue or define the expected behavior.
2. Add or update focused tests for behavior changes.
3. Implement the smallest correct change.
4. Run targeted tests for direct impact.
5. Run broader regression checks when the touched area is shared, security-sensitive, or payment/data related.

No test, no merge for logic changes unless the task is explicitly documentation-only or an automated test is genuinely impractical.

## Focused Test Matrix

- Payments, balance, ledger, referral, inventory, delivery: run transaction, payment, recovery, audit, and cache-invalidation tests.
- Permissions, roles, admin web, and high-risk actions: run role management, admin handlers, admin web/login-rate-limiter, middleware, and audit tests.
- User Telegram flows: run handler, keyboard, i18n, middleware, shop, payment handler, and paginator tests.
- Database schema or migrations: run model/data-method tests plus migration smoke where practical.
- Caching or performance paths: run cache invalidation, lazy query, paginator, and metrics tests.
- Locale or copy changes: run i18n/admin-i18n tests and manually inspect affected UI strings when needed.
- Model Lab or isolated Worker additions: add URL safety, SSRF, timeout, idempotency, key-redaction, quota, report-visibility, and failure-refund tests.
- Mini App/API additions: add auth/initData validation, permission, pagination, filtering, and report redaction tests.

## Mocking Policy

- Mock external APIs: Telegram Bot API, CryptoPay, provider-token payment callbacks, third-party relay endpoints, and official model APIs.
- Do not mock core business logic or repository methods when a real async SQLite query can exercise the behavior.
- Keep fake cache behavior realistic enough to catch invalidation and stale-read issues.
- Use stable fixtures rather than broad monkeypatching when testing payments, roles, inventory, and ledger behavior.

## Manual And Smoke Checks

Use manual checks when the change affects:

- SQLAdmin templates and visual/admin workflows,
- local startup and Windows scripts,
- webhook/polling behavior,
- Mini App browser flows,
- report visibility and redaction,
- payment provider setup that cannot be fully exercised locally.

Manual verification must include the path checked, expected result, observed result, and any residual risk.

## Acceptance Constraints For Upgrade Work

New platform work must satisfy:

- no loss of existing users, balances, orders, payments, or purchased goods;
- ledger entries reconcile to balances and points;
- duplicate webhooks or retries do not duplicate rewards, charges, reports, or deliveries;
- ordinary users cannot access admin functions, modify others' channels, or alter reports;
- channel owner claim works through Bot admin permission, challenge verification, or documented manual review;
- channel discovery supports search, filters, pagination, favorite, hide, click, and report actions;
- one-time API keys are not accepted in chat and are not persisted or logged;
- private networks, metadata services, redirect bypasses, abnormal ports, and DNS rebinding are blocked;
- model-test tasks can cancel or timeout and failed tasks do not incorrectly charge;
- reports include time, model, suite version, evidence, score/grade, and limitation wording;
- payment success, delivery, refund support, and `/paysupport` remain valid;
- core flows remain localized in `ru`, `en`, and `zh`.

