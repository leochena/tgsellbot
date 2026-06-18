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
- Mini App empty states and Telegram-entry guards are implemented and deployed.
  - Commit: `f459dad897166f0b8aa7a599fa785a41eb1d08d2`.
  - Server backup: `/opt/tgsellbot_backups/20260619-011548-miniapp-empty-states`.
- `scripts/platform_ops.py platform-launch-check` validates the public Mini App
  URL and feature-flag state before `platform_api_enabled` or
  `platform_menu_enabled` are switched on.
- Public Mini App HTTPS entry is live on the Virginia server.
  - Cloudflare DNS: `tg.1so.org A 47.253.251.141`, DNS-only.
  - Nginx reverse proxy: public `80/443` to `127.0.0.1:9090`.
  - Source-controlled nginx rebuild assets live under `deploy/nginx/`.
  - Let's Encrypt certificate covers `tg.1so.org` and
    `47-253-251-141.sslip.io`; expiry `2026-09-16`.
  - Platform settings: `platform_webapp_url=https://tg.1so.org/platform/app`,
    `platform_api_enabled=1`, `platform_menu_enabled=1`.
  - Launch gate: `platform-launch-check --smoke` passed with
    `current_launch_live=true`.
- Ledger migration rehearsal completed on a temporary production-copy database.
  - Evidence directory:
    `/opt/tgsellbot_backups/20260619-020157-ledger-rehearsal`.
  - Temporary database:
    `tgsellbot_ledger_rehearsal_20260619_020157`, dropped after rehearsal.
  - Source dump was removed after restore; preserved evidence is redacted
    summary JSON only.
  - `ledger-opening --dry-run`: 18 users checked, 23 opening entries would be
    created: 17 points, 6 balance.
  - `ledger-opening`: 23 opening entries created on the temporary database.
  - Repeat `ledger-opening`: 0 created, 23 skipped, proving idempotency.
  - `ledger-reconcile`: 18 users checked, 0 mismatches.

## In Progress

- Mini App launch readiness
  - Platform-only web runtime is deployed and bound behind HTTPS.
  - Telegram menu markup now emits WebApp URLs for `tg.1so.org`.
  - Manual Telegram client `/start` smoke remains to verify the live Bot button
    opens the Mini App inside Telegram.

## Next

1. Mini App launch readiness
   - Run a Telegram client `/start` smoke from the owner account and confirm the
     channel discovery, Model Lab, and contribution buttons open
     `https://tg.1so.org/platform/app` inside Telegram.
   - Keep the Cloudflare token rotated after DNS setup.
   - Keep certificate renewal monitoring in the server closeout checklist using
     `certbot certificates -d tg.1so.org` and `systemctl list-timers certbot*`.

2. Ledger source-of-truth decision
   - Keep current `users.balance` and `users.points_balance` fields
     authoritative until a separate release explicitly switches read paths.
   - If switching, repeat rehearsal immediately before release and define
     rollback/correction steps.

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

- Model Lab production run path requires a separate isolated Worker deployment
  environment before accepting real user keys at scale.

## Verification Checklist

- Local tests pass for each slice.
- `git diff --check` passes.
- Server deployment records commit, backup path, Alembic version, service state,
  and feature-flag values.
- New production tasks remain disabled until their manual smoke path is proven.
- Latest local runtime verification:
  - `.\.venv312\Scripts\python.exe -m pytest -q` passed: 647 tests.
  - `git diff --check` passed with only Windows LF-to-CRLF working-copy warnings.
  - `.\.venv312\Scripts\python.exe -m compileall bot scripts tests` passed.
- Latest server runtime verification:
  - `https://tg.1so.org/platform/app` returned 200 and includes the Telegram
    WebApp SDK.
  - `https://tg.1so.org/health` returned `healthy` with database `ok`.
  - Unauthenticated `https://tg.1so.org/platform/api/channels/discover`
    returned 401 `telegram_init_data_invalid`.
  - `scripts/platform_ops.py platform-launch-check --smoke` passed with
    `current_launch_live=true`.
