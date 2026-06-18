# TGSellBot Delivery Gates

This file defines what must be true before a task is reported complete, merged, or released.

## Definition Of Done

A change is done only when:

- scope is limited to the task goal;
- implementation follows existing module boundaries;
- behavior changes have tests or documented manual verification;
- relevant targeted tests pass;
- `git diff --check` passes;
- docs/config examples are updated when setup, operations, API shape, migrations, or user-facing behavior changes;
- secrets, logs, dumps, coverage files, and local runtime artifacts are not included;
- remaining risks and skipped checks are explicitly stated.

## Blocking Local Checks

For most code changes:

```powershell
.\.venv312\Scripts\python.exe -m pytest -q
git diff --check
```

For documentation-only changes:

```powershell
git diff --check
```

For targeted development, run the smallest relevant pytest module first, then broaden when shared behavior is touched.

## High-Risk Change Gates

Payments, balance, points, ledger, referral, inventory, and delivery:

- focused transaction/payment/recovery/audit/cache tests pass;
- idempotency and duplicate callback behavior are covered;
- rollback or correction path is documented.

Schema or migration changes:

- Alembic migration exists;
- upgrade path is tested or rehearsed locally;
- data-preservation and rollback notes are documented;
- financial/history data is not physically rewritten without an explicit migration plan.

Security, admin, permissions, Worker, Mini App auth, or URL testing:

- abuse cases and permission-denied paths are tested;
- SSRF and key-redaction tests are added where relevant;
- admin actions are audit-logged;
- production or customer data exposure is avoided.

UI/admin/template changes:

- targeted tests pass where available;
- manual smoke path is documented if visual inspection is needed.

## Release And Migration Gates

Before release:

- back up database and deployment configuration;
- confirm the previous stable commit/tag and rollback path;
- run required tests and smoke checks;
- verify `.env.example`, README, operations docs, and migration instructions are current;
- verify feature flags allow gradual rollout;
- verify detection services can fail without breaking shop, wallet, or delivery.

Rollout order:

1. internal/admin alpha,
2. limited beta,
3. gradual rollout,
4. full release.

New monitoring should cover growth, channel submissions/reviews, relay status, model-test success/cost, payments/refunds, SSRF blocks, key-misuse events, bans, and appeals.

## Governance Validation

After this governance setup, prove it with a real bounded task before claiming the process is fully validated. A good validation task should:

- cross at least two layers, such as schema plus domain logic, or config plus runtime behavior;
- require tests or a smoke check;
- stay inside existing architecture boundaries;
- produce a clear validation record and clean diff.

