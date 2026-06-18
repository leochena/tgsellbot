# TGSellBot Platform Development Kanban

Date: 2026-06-19

This board tracks the work needed to move from the deployed Stage 0 foundation
to a production-ready Telegram Mini App, channel directory, relay directory,
Model Lab, and platform operations layer.

## Done

- Stage 0 schema and backend foundation deployed to the Virginia server.
  - Commit: `6841ebe7e6bb50d7e049e3ef84df132798d4d38a`.
  - Server Alembic version: `0a1b2c3d4e5f`.
  - Service: `tgsellbot.service` active.
  - Backup: `/opt/tgsellbot_backups/20260619-001212`.
- Platform database tables, data methods, admin review APIs, Mini App P0 route,
  Model Lab worker skeleton, Telegram initData validation, and tests exist.
- Platform-only web runtime implemented. `PLATFORM_WEB_ENABLED=1` can serve
  `/platform/app`, `/platform/api`, public reports, and `/health` without
  exposing SQLAdmin.
- Platform feature flags are default-off in production:
  - `platform_api_enabled=0`
  - `platform_menu_enabled=0`
  - `platform_webapp_url=<empty>`

## In Progress

- Mini App launch readiness
  - Deploy platform-only web runtime to the Virginia server.
  - Bind the runtime behind HTTPS before enabling Telegram menu buttons.
  - Keep platform feature flags off until public URL smoke tests pass.

## Next

1. Mini App launch readiness
   - Configure a public HTTPS URL and set `platform_webapp_url`.
   - Enable `platform_api_enabled` only after a smoke test through the public URL.
   - Enable `platform_menu_enabled` after Bot menu entry smoke testing.
   - Add richer Mini App empty states and report detail screens.

2. Ledger migration rehearsal
   - Run `ledger-opening --dry-run`, `ledger-opening`, and `ledger-reconcile`
     against a production-like database copy.
   - Preserve preview, execution, and mismatch evidence.
   - Keep current balance/points fields authoritative until reconciliation passes.

3. Invite maturity
   - Run one manual `invite-settle` pass after checking mature reward counts.
   - Enable `tgsellbot-invite-settle.timer` only after the manual pass is clean.
   - Monitor reward appeals and review reversals.

4. Channel center P0 hardening
   - Add live Bot-admin ownership verification.
   - Add reviewer roles and review filters.
   - Expand moderation history.

5. Relay directory P0 hardening
   - Add reviewer role filters.
   - Improve complaint follow-up workflows.
   - Expand public owner-managed profiles after ownership verification is ready.

6. Model Lab P0 production wiring
   - Isolate Worker deployment from the main bot trust boundary.
   - Add scheduler/queue wiring for operator batch drain.
   - Add retention and monitoring for run and relay availability samples.

7. Dashboard hardening
   - Add stable thresholds for invite retention, bans, appeals, and reviewer load.
   - Replace unavailable metric placeholders only when collection is live.

## Blocked Or Needs External Setup

- Public Mini App requires a HTTPS domain or reverse proxy in front of the
  platform web runtime.
- Model Lab production run path requires a separate isolated Worker deployment
  environment before accepting real user keys at scale.

## Verification Checklist

- Local tests pass for each slice.
- `git diff --check` passes.
- Server deployment records commit, backup path, Alembic version, service state,
  and feature-flag values.
- New production tasks remain disabled until their manual smoke path is proven.
- Latest local runtime verification:
  - `.\.venv312\Scripts\python.exe -m pytest -q` passed: 644 tests.
  - `git diff --check` passed with only Windows LF-to-CRLF working-copy warnings.
  - `.\.venv312\Scripts\python.exe -m compileall -q bot scripts tests` passed.
