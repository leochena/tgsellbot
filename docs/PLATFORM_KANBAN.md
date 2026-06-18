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
- Channel `bot_admin` ownership claims now require live Telegram admin
  verification before approval.
  - The admin review API fetches the claim/channel context and calls Telegram
    `get_chat_member` for the claimant before approving `bot_admin` claims.
  - The data layer rejects direct `bot_admin` approvals unless the live proof
    matches the claim channel and claimant.
  - Challenge and manual claim methods remain available as fallback review
    paths.
- Invite maturity settlement is live on the Virginia server.
  - Pre-enable read-only check: 2 total invite rewards, 0 mature unrewarded,
    0 mature low-risk, 0 mature high-risk, 1 already rewarded.
  - Manual `tgsellbot-invite-settle.service` pass succeeded with
    `settled=0`, `blocked=0`.
  - Enabling `tgsellbot-invite-settle.timer` triggered a second successful
    pass with `settled=0`, `blocked=0`.
  - `tgsellbot-invite-settle.timer` is enabled and active; next run observed
    at `2026-06-19 03:32:42 CST`.
- Admin review queues now support reviewer workload filters for channel
  reports, relay feedback, and relay complaints.
  - `assigned_to` accepts a reviewer id or `unassigned`.
  - `reviewed_by` accepts a reviewer id or `unreviewed`.
  - `escalation` filters by `none`, `watch`, `operator`, `risk`, or `urgent`.
- Channel admin detail now includes a structured moderation history timeline
  for submissions, ownership claims, user reports, risk-state changes, and
  audit events. Public channel detail excludes internal report-review audit
  notes and does not expose the admin-only timeline.
- Channel and relay review APIs now accept either an existing SQLAdmin session
  or signed Telegram Mini App `initData` from users with `REVIEWER`,
  `RISK_OPERATOR`, `OPERATOR`, `ADMIN`, or `OWNER` roles. Risk-blocking and
  urgent/risk escalation actions require `RISK_OPERATOR` or higher.
- Relay complaint queues now expose follow-up states for `needs_followup`,
  `in_followup`, `resolved`, and `unresolved`, with admin API filters plus
  quick Acknowledge, Monitor, and Resolve actions in the review workspace.
- Platform Dashboard now returns stable operating thresholds and alerts for
  invite retention, ban events, appeal volume, and reviewer workload, and the
  review workspace renders the alert count alongside aggregate metrics.
- Model Lab production wiring now has systemd templates for operator batch
  drain and daily sample retention, plus a `model-sample-retention` ops command
  that prunes old Model Lab run and relay availability samples with dry-run
  support.
- Platform Dashboard now includes Model Lab operations readouts for the latest
  `model-test-drain` and `model-sample-retention` runs. The CLI records
  redacted `platform_ops_run` audit events for successful and failed scheduled
  runs, and the review workspace renders a Model ops row.
- Model Lab drain can now use an external isolated Worker runner through
  `--worker-runner`. The source-controlled runner/sudoers templates execute
  `platform_worker.py` as `tgsellbot-worker` with a cleared application
  environment, and the drain service skips until the root-owned runner exists.

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

3. Channel center P0 hardening
   - Extend reviewer-role gates only when new channel moderation endpoints are
     introduced.
   - Continue enriching moderation history only when new moderation event types
     are introduced.

4. Relay directory P0 hardening
   - Keep complaint follow-up state rules aligned when new outcomes are
     introduced.
   - Expand public owner-managed profiles after verification workflows mature.

5. Model Lab P0 production wiring
   - Enable the batch-drain timer only after the server-local key manifest and
     installed isolated Worker runner are approved.

6. Dashboard hardening
   - Replace unavailable metric placeholders only when collection is live.

## Blocked Or Needs External Setup

- Model Lab batch drain requires the root-owned isolated Worker runner,
  `tgsellbot-worker` user, sudoers template, and server-local key manifest to be
  installed and smoke-tested before accepting real user keys at scale.

## Verification Checklist

- Local tests pass for each slice.
- `git diff --check` passes.
- Server deployment records commit, backup path, Alembic version, service state,
  and feature-flag values.
- New production tasks remain disabled until their manual smoke path is proven.
- Latest local runtime verification:
  - `.\.venv312\Scripts\python.exe -m pytest tests\test_platform_foundation.py tests\test_platform_api.py tests\test_platform_ops.py -q` passed: 87 tests.
  - `.\.venv312\Scripts\python.exe -m pytest -q` passed: 662 tests.
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
