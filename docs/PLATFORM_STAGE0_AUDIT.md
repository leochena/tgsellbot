# TGSellBot AI Platform Stage 0 Audit

Date: 2026-06-17

This audit converts `tgsellbot_AI频道与模型验证平台升级开发计划书_v1.0.docx` into an executable backend foundation plan for the current repository.

## Current Capabilities

- Users: `users.telegram_id` is the primary user id, with role, balance, points, locale, first referral, registration date, and block status.
- Shop and delivery: categories, goods, item values, cart items, bought goods, promo codes, reviews, and JSON delivery are already modeled.
- Payments: `payments(provider, external_id)` has a uniqueness constraint for idempotency. Telegram Stars, provider-token checkout, and CryptoPay are represented in service code.
- Balance operations: top-ups, purchases, admin balance changes, and balance promo redemption update `users.balance` and `operations`.
- Points: check-in, group invites, lotteries, and points redemption update `users.points_balance`.
- Invites: group invite links and rewards exist, but historical rewards were immediate after check-in rather than 72h/7d matured.
- Roles: current permission bitmask covers user/admin/shop/stats/balance/promo operations. Domain roles such as channel owner, station owner, reviewer, risk operator, and content operator should be implemented as custom roles first, with new bits only when access gates need them.
- Admin: SQLAdmin plus custom Product Operations page are present. Financial/payment/audit tables are read-only in generic admin views.
- Deployment: Docker, systemd template, Windows local admin runner, Webhook mode, Redis option, PostgreSQL schema support, health/metrics endpoints, and CSV exports exist.

## Gaps Blocking Full P0

- Append-only ledger foundations now cover balance and points opening entries, dry-run preview, idempotent execution, and reconciliation. Existing fields remain the source of truth until the dry-run/execution/reconcile loop is rehearsed against a production-like database copy.
- The user-facing channel directory is now usable at Mini App P0 depth: discovery, search, category/language filters, pagination, submit, public detail view, favorite/hide/report interactions, and constrained owner-claim creation are wired. Public detail now shows recent submission, claim, and safe audit-trail context without leaking raw claim challenges, internal risk notes, or report-review audit details. Claim creation now shows one-time verification instructions/expected text in the Mini App after submission; public detail still redacts raw claim challenges. Verified channel owners can update the public title, category, language, and description through viewer-scoped Mini App detail forms/API without changing ownership, review status, or risk state. Admin claim queues include verification context for `bot_admin`, `challenge`, and `manual` methods. `bot_admin` claim approval now performs live Telegram `get_chat_member` verification and the data layer rejects matching-proof-free direct approvals. Channel report triage now records reviewer, notes, assignment, escalation, and reviewed time without exposing internal notes through public discovery. The admin review workspace now has a channel detail panel with internal risk notes, report summary, interactions, submission history, claim history, audit trail, and a structured moderation history timeline covering submissions, ownership claims, reports, current risk state, and audit events. Channel report queues can be filtered by assigned reviewer, reviewed-by reviewer, unassigned/unreviewed state, and escalation level. Channel review APIs accept either SQLAdmin session auth or signed Mini App `initData` from reviewer-role users; risk-blocking and risk/urgent escalation actions require `RISK_OPERATOR` or higher. Review workload summary now tracks open channel-report and relay-feedback assignments, unassigned backlog, urgent escalation, reviewer load, and threshold alerts. Admin audit-log filters now remain read-only and session-gated.
- The user-facing relay/provider directory now has a Mini App P0 slice: approved provider discovery, protocol/region filters, pagination, redacted public URL display, detail view, domain claim creation with verification instructions, inline rating/complaint forms, and viewer-scoped owner profile forms. Public relay detail now shows recent approved feedback, claim history, and audit-trail context without leaking raw claim challenges or internal follow-up conclusions. Verified relay owners can update public name, website, protocol label, model scope, region, and pricing through Mini App/API; endpoint normalized value/hash, owner, review status, and risk state are not owner-editable. Admin relay claim queues include verification context for `domain`, `challenge`, and `manual` methods. Domain claims now require HTTPS `.well-known/tgsellbot-relay-claim.txt` proof with public-DNS revalidation, no redirects, response-size limits, and expected-text matching before approval. Relay feedback/complaint triage records reviewer, notes, assignment, escalation, reviewed time, outcome, follow-up notes, resolved metadata, follow-up state (`needs_followup`, `in_followup`, `resolved`, `unresolved`), and filters for outcome, assigned/reviewed reviewer, escalation, and follow-up state. The admin review workspace now has a relay provider detail panel with provider profile, claim history, feedback summary, audit trail, and relay complaint quick actions for acknowledge, monitor, and resolve. Relay review APIs accept either SQLAdmin session auth or signed Mini App `initData` from reviewer-role users; risk-blocking and risk/urgent escalation actions require `RISK_OPERATOR` or higher. Mini App owner dashboard foundation now lists verified-owner channels and relay providers with public-safe interaction, feedback, latest claim, and submission status metrics. SQLAdmin/operator owner dashboard foundation now aggregates owner-scoped channel/relay counts, status/risk distribution, interactions, feedback, average rating, and recent public-safe resources while workload thresholds and audit filters now have baseline implementations.
- Model Lab orchestration tables, job status reads, private report reads, user-scoped report lists, owner-controlled visibility changes, public report lists, token-gated unlisted report reads, recent run history, an operator batch drain command, systemd drain templates, sample retention pruning, and dashboard readouts for latest drain/retention outcomes now exist. Mini App report detail now separates score badges, job/report timeline, worker run history, visibility meaning, limitation copy, redacted evidence summary, and public/unlisted share controls instead of dumping raw JSON. Sharing supports copy, system share, and Telegram share fallbacks while private reports omit public links. Enabling the drain timer still needs the server-local key manifest and release approval.
- An isolated Model Lab Worker skeleton now exists as `bot/model_lab/worker.py` plus `scripts/platform_worker.py`. It performs runtime SSRF checks, DNS revalidation, bounded OpenAI-compatible and Anthropic-compatible probes, and redacted report assembly without importing the main database or persisting API keys. Dispatcher paths can claim `model_test_jobs`, pass one-time keys to the isolated Worker through stdin, and write back redacted reports. The batch drain path matches ephemeral local key manifests by irreversible fingerprint and does not persist raw keys. Operators can now pass `--worker-runner` so the Worker executes through a separate root-owned runner as `tgsellbot-worker` with the application environment cleared. The Virginia server has the root-owned runner and sudoers installed, smoke-tested, and kept disabled for scheduled drains until a server-local key manifest is approved.
- Mini App authentication foundation is implemented for user-facing platform API endpoints through signed Telegram `initData`. A minimal P0 Mini App page now exists for channel discovery/submission/detail, channel and relay owner profile updates, relay submission, relay directory/detail, model-test job creation/status, private report viewing with structured summaries, visibility switching across private/unlisted/public modes, share-link creation, contribution entry points, and ledger viewing; full production UX is still pending.
- A read-only admin dashboard foundation now aggregates current channel, relay, Model Lab, ledger, invite-retention, fraud-event counts, Model Lab run samples, relay availability samples, and the latest redacted Model Lab ops outcomes from existing tables. It also exposes stable operating thresholds and alerts for invite retention, ban events, appeal volume, and reviewer workload. Cost, latency, relay availability, and scheduled ops readouts stay explicitly unavailable until real samples or audit events are recorded.
- Webhook idempotency is not recorded beyond business idempotency in payments and some purchase/reward paths.

## New Foundation Added In This Iteration

- Repository governance files: `CLAUDE.md`, `AGENTS.md`, `ARCHITECTURE.md`, `TESTING.md`, `CI_STATUS.md`.
- Feature flags stored in `bot_settings`:
  - `platform_menu_enabled`
  - `platform_api_enabled`
  - `platform_webapp_url`
- Data foundation:
  - ledger entries,
  - channel records, submissions, claims, and interactions,
  - relay providers, claims, and feedback,
  - test suites, model test jobs, and reports,
  - fraud events,
  - matured invite fields on existing group invite rewards,
  - invite-retention snapshots.
- Service foundation:
  - channel username normalization and submission,
  - channel discovery, public detail reads, and interactions,
  - channel and relay claim creation plus review approval paths,
  - verified owner profile update paths for public channel and relay metadata without allowing owner-side endpoint/hash/status/risk mutation,
  - relay domain-claim ownership verification through a bounded HTTPS well-known proof fetch before approval,
  - admin-only channel submission queues and review transitions,
  - relay URL normalization, submission, public discovery, and detail reads,
  - admin-only relay provider, claim, and feedback review queues,
  - model-test job creation with API-key fingerprint/mask only,
  - model-test job claim/complete/fail lifecycle helpers,
  - one-shot Model Lab dispatcher that invokes the isolated Worker without putting API keys in command-line arguments,
  - operator batch drain command and disabled-by-default systemd timer templates for claimable Model Lab jobs using an ephemeral JSON key manifest,
  - isolated Worker runner and sudoers templates that let the drain service execute `platform_worker.py` as `tgsellbot-worker` without inheriting main app secrets or database settings,
  - launch-gate Bot menu markup validation that renders the configured main menu and verifies the channel, Model Lab, and contribution buttons are WebApp buttons for `/platform/app` tabs,
  - Model Lab run and relay availability sample retention command plus daily systemd timer templates,
  - redacted `platform_ops_run` audit events plus Platform Dashboard readouts for latest Model Lab drain and retention outcomes,
  - model-test job status reads, report creation, report reads, public/unlisted report entry points, recent run history, and visibility changes with limitation wording plus Mini App report summary/timeline/run-history/share rendering for public and unlisted reports only,
  - owner dashboard API and Mini App contribution-tab summary for verified owner channels and relay providers without raw claim challenges, internal risk notes, or relay endpoint hash/normalized values,
  - durable Model Lab run samples for worker status, duration, request count, token count, optional cost, and redacted failure summary,
  - durable relay availability samples from Model Lab runs or operator checks with status, HTTP status, latency, and redacted error summary,
  - SSRF-oriented HTTPS URL safety checks,
  - sensitive query parameters such as `api_key`, `token`, `secret`, and `password` are rejected before URL persistence,
  - SQLAdmin Platform Review workspace and reviewer-role API gates for channel submissions, channel claims, channel report detail history with structured moderation timeline, relay providers, relay provider detail history, relay claims, relay feedback, a dedicated relay complaint queue, assignment/escalation capture for channel report triage, outcome/follow-up capture for relay feedback plus complaints, and follow-up state filters with acknowledge/monitor/resolve complaint actions,
  - admin-only Platform Dashboard tab and API with current aggregate counts, real run/availability metric aggregation, operating thresholds/alerts, and explicit unavailable metric coverage when samples are absent,
  - admin-only owner dashboard tab and API with owner-scoped channel/relay status, risk, interaction, feedback, average-rating, and recent-resource summaries,
  - admin-only review workload tab and API with open assignment totals, unassigned backlog, urgent escalation count, per-reviewer load, and threshold alerts for current channel-report and relay-feedback queues,
  - admin-only audit logs tab and API with read-only filters for level, action, resource type, resource id, user id, and free-text search; details are redacted before JSON/HTML rendering and IP addresses are not exposed,
  - invite-retention snapshot capture for invite-related activity plus dashboard/admin readout,
- invite reward review queues for qualified, risky, and rejected rewards with audited reviewer transitions,
- settled invite rewards can now be reversed once by admin review when later rejected or risk-blocked,
- inviter-facing reward status history with masked invited-user ids, delayed settlement status, public rejection/risk reasons, pagination, one-click appeal creation for risk/rejected rewards, and duplicate-appeal throttling while a matching appeal is open or under review,
  - systemd `invite-settle` service/timer templates plus operations runbook for hourly mature reward settlement; the Virginia timer is enabled and active after a clean manual pass,
  - user appeal event capture plus admin fraud-event queue and review status transitions,
  - Telegram Mini App entry page at `/platform/app` with channel discovery filters, channel detail view, relay directory filters, relay detail view, interactions, claim creation with verification guidance, and viewer-scoped owner profile forms,
  - optional Bot menu WebApp buttons when `platform_webapp_url` is configured,
  - ledger balance and entry query helpers,
  - idempotent opening ledger backfill and reconciliation,
  - read-only ledger source-of-truth cutover gate with full-scan, mismatch,
    rollback-plan, and correction-plan output,
  - invite qualification plus mature settlement after the freeze/7-day windows.

## Public Interface Slice Added

All endpoints are feature-flagged by `platform_api_enabled`. User-facing
endpoints accept signed Telegram Mini App `initData` through
`X-Telegram-Init-Data`, derive the actor id server-side, and reject cross-user
access. Channel and relay review endpoints accept either the existing SQLAdmin
session or reviewer-role Mini App auth; broader admin endpoints remain session-gated.

- `GET /admin/platform/review`
- `GET /admin/platform/review/app`
- `GET /platform/app`
- `GET /platform/reports`
- `GET /platform/reports/{report_id}`
- `GET /platform/api/users/{user_id}/ledger`
- `GET /platform/api/owner/dashboard`
- `POST /platform/api/channels/submissions`
- `GET /platform/api/channels/discover`
- `GET /platform/api/channels/{channel_id}`
- `GET /platform/api/admin/channels/submissions`
- `GET /platform/api/admin/channels/{channel_id}`
- `POST /platform/api/admin/channels/submissions/{submission_id}/review`
- `POST /platform/api/channels/{channel_id}/interactions`
- `POST /platform/api/channels/{channel_id}/claim`
- `POST /platform/api/channels/{channel_id}/owner-profile`
- `GET /platform/api/admin/channel-claims`
- `POST /platform/api/channel-claims/{claim_id}/review`
- `POST /platform/api/relays`
- `GET /platform/api/relays/discover`
- `GET /platform/api/relays/{provider_id}`
- `GET /platform/api/admin/relays`
- `GET /platform/api/admin/relays/{provider_id}`
- `POST /platform/api/admin/relays/{provider_id}/review`
- `POST /platform/api/relays/{provider_id}/claim`
- `POST /platform/api/relays/{provider_id}/owner-profile`
- `GET /platform/api/admin/relay-claims`
- `POST /platform/api/relay-claims/{claim_id}/review`
- `POST /platform/api/relays/{provider_id}/feedback`
- `GET /platform/api/admin/relay-feedback`
- `POST /platform/api/admin/relay-feedback/{feedback_id}/review`
- `GET /platform/api/admin/dashboard`
- `GET /platform/api/admin/owners/dashboard`
- `GET /platform/api/admin/review-workload`
- `GET /platform/api/admin/audit-logs`
- `POST /platform/api/users/{user_id}/appeals`
- `GET /platform/api/admin/fraud-events`
- `GET /platform/api/admin/invite-retention`
- `GET /platform/api/admin/invite-rewards`
- `POST /platform/api/admin/invite-rewards/{reward_id}/review`
- `POST /platform/api/admin/fraud-events/{event_id}/review`
- `POST /platform/api/relay-tests`
- `GET /platform/api/relay-tests`
- `GET /platform/api/relay-tests/{job_id}`
- `POST /platform/api/relay-tests/{job_id}/reports`
- `GET /platform/api/reports`
- `GET /platform/api/reports/{report_id}`
- `POST /platform/api/reports/{report_id}/visibility`
- `GET /platform/api/public/reports`
- `GET /platform/api/public/reports/{report_id}`

## Operator Commands

- `.\.venv312\Scripts\python.exe scripts\platform_ops.py ledger-opening --dry-run --limit 1000 --offset 0`
  previews idempotent opening ledger entries for current balances and points without writing ledger rows.
- `.\.venv312\Scripts\python.exe scripts\platform_ops.py ledger-opening --limit 1000 --offset 0`
  creates the previewed idempotent opening ledger entries.
- `.\.venv312\Scripts\python.exe scripts\platform_ops.py ledger-reconcile --limit 1000 --offset 0`
  compares `users.balance` / `users.points_balance` with available ledger totals.
- `.\.venv312\Scripts\python.exe scripts\platform_ops.py ledger-cutover-check --limit 5000 --offset 0`
  runs a read-only source-of-truth release gate. It allows a future switch only
  after a full clean reconciliation scan and prints rollback/correction steps;
  it does not change read paths.
- `.\.venv312\Scripts\python.exe scripts\platform_ops.py invite-settle --limit 100`
  credits mature qualified invite rewards. Rewards remain pending until both the
  72-hour freeze and 7-day settlement window have elapsed.
- `Get-Content .\one-time-key.txt | .\.venv312\Scripts\python.exe scripts\platform_ops.py model-test-run <job_id>`
  claims one model-test job, sends the one-time API key to the isolated Worker
  through stdin, and writes back a redacted private report. Do not pass keys on
  the command line.
- `Get-Content .\model-test-keys.json | .\.venv312\Scripts\python.exe scripts\platform_ops.py model-test-drain --limit 10 --worker-runner /usr/local/libexec/tgsellbot/run-isolated-worker.sh`
  scans claimable `created`, `queued`, and `failed` model-test jobs, matches the
  local one-time key manifest by fingerprint, runs only jobs with a matching
  ephemeral key, returns redacted job/report ids, and records a redacted
  `platform_ops_run` audit event. Do not commit or log the manifest file. The
  runner path should be a root-owned wrapper installed from
  `deploy/model_lab/run-isolated-worker.sh` with the matching sudoers template.
- `.\.venv312\Scripts\python.exe scripts\platform_ops.py model-key-manifest-check --key-manifest-file .\model-test-keys.json`
  validates a server-local Model Lab key manifest before manual drain or timer
  enablement. The output is read-only and contains only counts, fingerprints,
  hashes, and masks; raw keys must not appear in command output or logs.
- `.\.venv312\Scripts\python.exe scripts\platform_ops.py model-sample-retention --dry-run`
  previews old Model Lab run and relay availability samples that would be
  pruned. Omit `--dry-run` to delete the bounded batch using the configured
  retention windows. The CLI records a redacted `platform_ops_run` audit event
  for scheduled run monitoring.
- Configure `platform_webapp_url` to the public HTTPS `/platform/app` URL before
  enabling Mini App buttons. With an empty value, feature-flagged platform menu
  entries fall back to safe Bot placeholder messages.
  Unsafe URLs fall back to callback buttons automatically.

## Sprint Backlog

1. Ledger migration rehearsal
   - Run `ledger-opening --dry-run`, `ledger-opening`, then `ledger-reconcile` against a production-like database copy.
   - Preserve the dry-run preview, execution result, and mismatch report as migration evidence.
   - Keep existing fields as read source until reconciliation and
     `ledger-cutover-check` pass in the release window.

2. Invite maturity
   - Virginia production enablement is complete: pre-enable check found 0 mature unrewarded invite rewards, the manual settlement pass returned `settled=0` and `blocked=0`, and `tgsellbot-invite-settle.timer` is enabled and active.
   - Confirm the operator-facing reinstatement workflow for rewards that were settled, later reversed, and then cleared again when real appeal volume appears.
   - Monitor reward-history appeal volume and tune escalation thresholds if operators still see noisy repeated submissions.

3. Channel center P0
   - Harden the current Mini App submit/find/detail flows with richer empty states and report detail screens.
   - Extend reviewer-role gates when new channel moderation endpoints are introduced. Current channel review APIs accept SQLAdmin session auth or signed Mini App `initData` from reviewer-role users; risk-blocking and risk/urgent escalation require `RISK_OPERATOR` or higher.
   - Extend channel report triage with new moderation event types as they are introduced. Structured moderation history, review workload summary, and baseline threshold alerts now exist for channel reports and relay feedback.
   - Live Bot-admin ownership verification now runs before `bot_admin` claim approval. Challenge and manual claim records remain available as fallback review paths.

4. Relay directory P0
   - Keep complaint follow-up state rules aligned when new outcomes or relay moderation endpoints are introduced.
   - Extend reviewer-role gates when new relay moderation endpoints are introduced. Current relay review APIs accept SQLAdmin session auth or signed Mini App `initData` from reviewer-role users; risk-blocking and risk/urgent escalation require `RISK_OPERATOR` or higher. Mini App and SQLAdmin owner dashboard foundations now exist for verified channel/relay owners; complaint follow-up outcome tracking, follow-up state filters, acknowledge/monitor/resolve quick actions, assigned/reviewed/escalation queue filters, audit filters, and workload threshold summaries now exist for relay feedback and complaint queues.
   - Expand public profiles with richer owner-managed editorial fields after owner verification is production-ready.

5. Model Lab P0
   - Enable the operator batch-drain timer only after the isolated Worker runner is installed, smoke-tested under `tgsellbot-worker`, and paired with a restricted server-local key manifest that passes `model-key-manifest-check`.
   - Keep Mini App report sharing limited to public/unlisted visibility. Current public/unlisted report entry points are read-only and redacted; `unlisted` links require the generated share token and do not appear in the public report list. Recent Model Lab run history is now shown on owner job/report details and public report detail without exposing API keys or owner ids.
   - Keep network controls, timeout/size/token limits, and redirect revalidation enforced in deployment.
   - Extend protocol coverage and report scoring as additional compatibility cases are verified.

6. Mini App authentication
   - Complete production-grade Mini App UI flows beyond the current P0 form shell.
   - Add endpoint groups for public read, authenticated user, owner, reviewer, and admin operations.
   - Keep admin moderation endpoints behind SQLAdmin session or role-gated auth.

7. Stage 5 dashboard hardening
   - Keep Model Lab drain and sample-retention readouts aligned as more scheduled operations are added.
   - Keep invite-retention, ban, appeal, and reviewer-load operating thresholds aligned with production policy as real volume grows.
   - Replace unavailable dashboard placeholders only after the corresponding storage and collection path exists. Model Lab cost remains unavailable unless run samples include explicit cost estimates.
   - Move hardcoded operating thresholds into configurable policy only after metric semantics and operator response paths are stable.

## Risk Register

- API key leakage: mitigated in foundation by refusing chat collection in UI copy, storing only fingerprint/mask in job records, passing one-time Worker keys through request body/stdin only, validating server-local batch manifests with redacted output, and recursively redacting reports/failure reasons.
- SSRF: mitigated by `url_safety.py` plus the isolated Worker's runtime DNS and redirect revalidation. The Virginia isolated runner, sudoers file, and `tgsellbot-worker` smoke are installed; production drain should stay disabled until the server-local key manifest is approved.
- Accounting drift: ledger is introduced but not yet authoritative. The live
  `ledger-cutover-check` gate currently rejects production source switching
  (`checked=18`, `mismatch_count=17`); a separate opening-backfill release and
  clean cutover check must precede any source-of-truth switch.
- Menu overload: new platform menu entries are feature-flagged off by default.
- False model claims: report limitation wording is required by default.
- Public API auth: user endpoints validate Telegram Mini App `initData`; channel/relay review endpoints accept SQLAdmin session auth or reviewer-role Mini App auth; broader admin dashboards and audit-log endpoints remain session-gated. Future work still needs a full production Mini App client.

## Verification Record

- `.\.venv312\Scripts\python.exe scripts\platform_ops.py model-key-manifest-check --help` passed.
- `.\.venv312\Scripts\python.exe -m compileall -q bot scripts tests` passed.
- `.\.venv312\Scripts\python.exe -m pytest tests\test_platform_ops.py -q` passed: 22 tests.
- `.\.venv312\Scripts\python.exe -m pytest tests\test_platform_api.py::TestPlatformAPI::test_platform_mini_app_page_uses_telegram_init_data_and_safe_entrypoints tests\test_platform_api.py::TestPlatformAPI::test_public_report_page_uses_public_api_without_telegram_init_data -q` passed: 2 tests.
- `.\.venv312\Scripts\python.exe -m pytest tests\test_platform_foundation.py tests\test_platform_api.py tests\test_platform_ops.py -q` passed: 94 tests.
- `.\.venv312\Scripts\python.exe -m pytest -q` passed: 669 tests.
- Local Browser smoke on `http://127.0.0.1:9393/platform/app?tab=model_lab`
  loaded the Mini App shell with Model Lab active, report sharing templates,
  copy fallback, and no console errors. The public report page shell also
  loaded with public-API-only share controls; the list fetch requires a local
  test database.
- `.\.venv312\Scripts\python.exe -m pytest tests\test_group_invites.py tests\test_platform_api.py tests\test_platform_foundation.py -q` passed: 51 tests.
- `.\.venv312\Scripts\python.exe -m pytest tests\test_platform_ops.py -q` passed: 7 tests.
- `.\.venv312\Scripts\python.exe -m pytest tests\test_group_invites.py tests\test_keyboards.py -q` passed: 57 tests.
- `.\.venv312\Scripts\python.exe -m pytest -q` passed: 610 tests.
- `git diff --check` passed with only Windows LF-to-CRLF working-copy warnings.
- `.\.venv312\Scripts\python.exe -m pytest tests\test_group_invites.py tests\test_platform_api.py -q` passed: 34 tests.
- `.\.venv312\Scripts\python.exe -m pytest tests\test_keyboards.py tests\test_group_invites.py tests\test_platform_api.py -q` passed: 78 tests.
- `.\.venv312\Scripts\python.exe -m compileall bot scripts tests` passed.
- `.\.venv312\Scripts\python.exe -m pytest -q` passed: 615 tests.
- `git diff --check` passed with only Windows LF-to-CRLF working-copy warnings.
- `.\.venv312\Scripts\python.exe -m pytest tests\test_group_invites.py -q` passed: 22 tests.
- `.\.venv312\Scripts\python.exe -m pytest tests\test_keyboards.py tests\test_group_invites.py tests\test_platform_api.py -q` passed: 82 tests.
- `.\.venv312\Scripts\python.exe -m pytest -q` passed: 619 tests.
- `.\.venv312\Scripts\python.exe -m compileall bot scripts tests` passed.
- `git diff --check` passed with only Windows LF-to-CRLF working-copy warnings.
- `.\.venv312\Scripts\python.exe -m pytest tests\test_platform_foundation.py tests\test_platform_api.py -q` passed: 42 tests.
- `.\.venv312\Scripts\python.exe -m pytest -q` passed: 619 tests.
- `.\.venv312\Scripts\python.exe -m compileall bot scripts tests` passed.
- `git diff --check` passed with only Windows LF-to-CRLF working-copy warnings.
- `.\.venv312\Scripts\python.exe -m pytest tests\test_platform_api.py -q` passed: 19 tests.
- `.\.venv312\Scripts\python.exe -m pytest tests\test_platform_foundation.py tests\test_platform_api.py -q` passed: 43 tests.
- `.\.venv312\Scripts\python.exe -m pytest -q` passed: 620 tests.
- `.\.venv312\Scripts\python.exe -m compileall bot scripts tests` passed.
- `git diff --check` passed with only Windows LF-to-CRLF working-copy warnings.
- `.\.venv312\Scripts\python.exe -m pytest tests\test_platform_foundation.py::TestLedgerFoundation tests\test_platform_ops.py::TestPlatformOpsScript -q` passed: 10 tests.
- `.\.venv312\Scripts\python.exe -m pytest tests\test_platform_foundation.py tests\test_platform_api.py tests\test_platform_ops.py -q` passed: 51 tests.
- `.\.venv312\Scripts\python.exe -m pytest -q` passed: 621 tests.
- `.\.venv312\Scripts\python.exe -m compileall bot scripts tests` passed.
- `git diff --check` passed with only Windows LF-to-CRLF working-copy warnings.
- `.\.venv312\Scripts\python.exe -m pytest tests\test_group_invites.py tests\test_platform_api.py -q` passed: 42 tests.
- `.\.venv312\Scripts\python.exe -m pytest tests\test_group_invites.py tests\test_platform_api.py tests\test_keyboards.py tests\test_admin_i18n.py -q` passed: 93 tests.
- `.\.venv312\Scripts\python.exe -m pytest -q` passed: 622 tests.
- `.\.venv312\Scripts\python.exe -m compileall bot scripts tests` passed.
- `git diff --check` passed with only Windows LF-to-CRLF working-copy warnings.
- `.\.venv312\Scripts\python.exe -m pytest tests\test_platform_foundation.py::TestChannelFoundation tests\test_platform_api.py::TestPlatformAPI::test_mini_app_api_discovers_filters_pages_and_claims_channel tests\test_platform_api.py::TestPlatformAPI::test_platform_review_app_requires_admin_session_and_uses_admin_review_api -q` passed: 7 tests.
- `.\.venv312\Scripts\python.exe -m pytest tests\test_platform_foundation.py tests\test_platform_api.py -q` passed: 45 tests.
- `.\.venv312\Scripts\python.exe -m pytest -q` passed: 623 tests.
- `.\.venv312\Scripts\python.exe -m compileall bot scripts tests` passed.
- `git diff --check` passed with only Windows LF-to-CRLF working-copy warnings.
- `.\.venv312\Scripts\python.exe -m pytest tests\test_platform_foundation.py::TestRelayAndModelLabFoundation::test_relay_claim_approval_sets_owner tests\test_platform_foundation.py::TestRelayAndModelLabFoundation::test_relay_claim_verification_context_is_admin_only tests\test_platform_api.py::TestPlatformAPI::test_mini_app_api_discovers_and_reads_relay_directory tests\test_platform_api.py::TestPlatformAPI::test_platform_review_app_requires_admin_session_and_uses_admin_review_api -q` passed: 4 tests.
- `.\.venv312\Scripts\python.exe -m pytest tests\test_platform_foundation.py tests\test_platform_api.py -q` passed: 46 tests.
- `.\.venv312\Scripts\python.exe -m pytest -q` passed: 624 tests.
- `.\.venv312\Scripts\python.exe -m compileall bot scripts tests` passed.
- `git diff --check` passed with only Windows LF-to-CRLF working-copy warnings.
- `.\.venv312\Scripts\python.exe -m pytest tests\test_platform_foundation.py::TestChannelFoundation::test_channel_report_queue_updates_risk_and_blocks_discovery tests\test_platform_api.py::TestPlatformAPI::test_admin_session_can_filter_and_triage_relay_complaints tests\test_platform_api.py::TestPlatformAPI::test_admin_session_can_triage_channel_reports tests\test_platform_api.py::TestPlatformAPI::test_platform_review_app_requires_admin_session_and_uses_admin_review_api -q` passed: 4 tests.
- `.\.venv312\Scripts\python.exe -m compileall bot scripts tests` passed.
- `.\.venv312\Scripts\python.exe -m pytest tests\test_platform_foundation.py tests\test_platform_api.py tests\test_platform_ops.py -q` passed: 53 tests.
- `.\.venv312\Scripts\python.exe -m pytest tests\test_group_invites.py::TestGroupInviteMethods::test_invite_retention_activity_is_idempotent_for_same_snapshot -q` passed: 1 test.
- `.\.venv312\Scripts\python.exe -m compileall bot scripts tests` passed.
- `.\.venv312\Scripts\python.exe -m pytest -q` passed: 624 tests.
- `git diff --check` passed with only Windows LF-to-CRLF working-copy warnings.
- `.\.venv312\Scripts\python.exe -m pytest tests\test_platform_foundation.py::TestRelayAndModelLabFoundation::test_relay_claim_approval_sets_owner tests\test_platform_foundation.py::TestRelayAndModelLabFoundation::test_relay_claim_verification_context_is_admin_only tests\test_platform_foundation.py::TestRelayAndModelLabFoundation::test_relay_domain_claim_requires_well_known_proof_before_approval tests\test_platform_api.py::TestPlatformAPI::test_admin_api_requires_domain_claim_proof_before_approval -q` passed: 4 tests.
- `.\.venv312\Scripts\python.exe -m compileall bot scripts tests` passed.
- `.\.venv312\Scripts\python.exe -m pytest tests\test_platform_foundation.py tests\test_platform_api.py tests\test_platform_ops.py -q` passed: 55 tests.
- `.\.venv312\Scripts\python.exe -m pytest -q` passed: 626 tests.
- `.\.venv312\Scripts\python.exe -m compileall bot scripts tests` passed.
- `.\.venv312\Scripts\python.exe -m pytest tests\test_platform_api.py::TestPlatformAPI::test_admin_api_reads_relay_provider_detail_history tests\test_platform_api.py::TestPlatformAPI::test_platform_review_app_requires_admin_session_and_uses_admin_review_api -q` passed: 2 tests.
- `.\.venv312\Scripts\python.exe -m compileall bot scripts tests` passed.
- `.\.venv312\Scripts\python.exe -m pytest tests\test_platform_foundation.py tests\test_platform_api.py tests\test_platform_ops.py -q` passed: 56 tests.
- `.\.venv312\Scripts\python.exe -m pytest tests\test_platform_foundation.py::TestRelayAndModelLabFoundation::test_relay_feedback_review_tracks_internal_outcome_without_public_leak tests\test_platform_api.py::TestPlatformAPI::test_admin_session_can_filter_and_triage_relay_complaints -q` passed: 2 tests.
- `.\.venv312\Scripts\python.exe -m compileall bot scripts tests` passed.
- `.\.venv312\Scripts\python.exe -m pytest tests\test_platform_foundation.py tests\test_platform_api.py tests\test_platform_ops.py -q` passed: 57 tests.
- `.\.venv312\Scripts\python.exe -m pytest -q` passed: 628 tests.
- `.\.venv312\Scripts\python.exe -m compileall bot scripts tests` passed.
- `git diff --check` passed with only Windows LF-to-CRLF working-copy warnings.
- `.\.venv312\Scripts\python.exe -m pytest tests\test_platform_foundation.py::TestChannelFoundation::test_channel_admin_detail_includes_report_history_without_public_leak tests\test_platform_api.py::TestPlatformAPI::test_admin_api_reads_channel_report_detail_history tests\test_platform_api.py::TestPlatformAPI::test_platform_review_app_requires_admin_session_and_uses_admin_review_api -q` passed: 3 tests.
- `.\.venv312\Scripts\python.exe -m compileall bot scripts tests` passed.
- `.\.venv312\Scripts\python.exe -m pytest tests\test_platform_foundation.py tests\test_platform_api.py tests\test_platform_ops.py -q` passed: 59 tests.
- `.\.venv312\Scripts\python.exe -m pytest -q` passed: 630 tests.
- `.\.venv312\Scripts\python.exe -m compileall bot scripts tests` passed.
- `git diff --check` passed with only Windows LF-to-CRLF working-copy warnings.
- `.\.venv312\Scripts\python.exe -m pytest tests\test_platform_foundation.py::TestChannelFoundation::test_channel_owner_profile_update_is_owner_scoped tests\test_platform_foundation.py::TestRelayAndModelLabFoundation::test_relay_owner_profile_update_keeps_base_url_and_hash_stable tests\test_platform_api.py::TestPlatformAPI::test_channel_owner_profile_api_requires_verified_owner tests\test_platform_api.py::TestPlatformAPI::test_relay_owner_profile_api_requires_verified_owner_and_keeps_endpoint_stable -q` passed: 4 tests.
- `.\.venv312\Scripts\python.exe -m pytest tests\test_platform_foundation.py::TestChannelFoundation::test_channel_owner_profile_update_is_owner_scoped tests\test_platform_foundation.py::TestRelayAndModelLabFoundation::test_relay_owner_profile_update_keeps_base_url_and_hash_stable tests\test_platform_api.py::TestPlatformAPI::test_channel_owner_profile_api_requires_verified_owner tests\test_platform_api.py::TestPlatformAPI::test_relay_owner_profile_api_requires_verified_owner_and_keeps_endpoint_stable tests\test_platform_api.py::TestPlatformAPI::test_platform_mini_app_page_uses_telegram_init_data_and_safe_entrypoints -q` passed: 5 tests.
- `.\.venv312\Scripts\python.exe -m pytest tests\test_platform_foundation.py tests\test_platform_api.py tests\test_platform_ops.py -q` passed: 63 tests.
- `.\.venv312\Scripts\python.exe -m compileall bot scripts tests` passed.
- `.\.venv312\Scripts\python.exe -m pytest tests\test_platform_foundation.py tests\test_platform_api.py tests\test_platform_ops.py -q` passed: 63 tests.
- `.\.venv312\Scripts\python.exe -m pytest -q` passed: 634 tests.
- `.\.venv312\Scripts\python.exe -m compileall bot scripts tests` passed.
- `git diff --check` passed with only Windows LF-to-CRLF working-copy warnings.
- `.\.venv312\Scripts\python.exe -m pytest tests\test_platform_api.py::TestPlatformAPI::test_platform_mini_app_page_uses_telegram_init_data_and_safe_entrypoints tests\test_platform_api.py::TestPlatformAPI::test_mini_app_api_discovers_filters_pages_and_claims_channel tests\test_platform_api.py::TestPlatformAPI::test_mini_app_api_discovers_and_reads_relay_directory -q` passed: 3 tests.
- `.\.venv312\Scripts\python.exe -m pytest tests\test_platform_api.py::TestPlatformAPI::test_platform_mini_app_page_uses_telegram_init_data_and_safe_entrypoints tests\test_platform_api.py::TestPlatformAPI::test_mini_app_api_reads_model_test_job_and_report_by_owner -q` passed: 2 tests.
- `.\.venv312\Scripts\python.exe -m pytest tests\test_platform_api.py::TestPlatformAPI::test_platform_mini_app_page_uses_telegram_init_data_and_safe_entrypoints -q` passed: 1 test.
- `.\.venv312\Scripts\python.exe -m pytest tests\test_platform_api.py::TestPlatformAPI::test_public_model_report_entries_are_visibility_scoped_and_redacted tests\test_platform_api.py::TestPlatformAPI::test_mini_app_api_reads_model_test_job_and_report_by_owner tests\test_platform_api.py::TestPlatformAPI::test_platform_mini_app_page_uses_telegram_init_data_and_safe_entrypoints tests\test_platform_api.py::TestPlatformAPI::test_public_report_page_uses_public_api_without_telegram_init_data -q` passed: 4 tests.
- `.\.venv312\Scripts\python.exe -m pytest tests\test_platform_foundation.py tests\test_platform_api.py tests\test_platform_ops.py -q` passed: 65 tests.
- `.\.venv312\Scripts\python.exe -m compileall bot scripts tests` passed.
- `.\.venv312\Scripts\python.exe -m pytest -q` passed: 636 tests.
- `git diff --check` passed with only Windows LF-to-CRLF working-copy warnings.
- `.\.venv312\Scripts\python.exe -m pytest tests\test_platform_foundation.py tests\test_platform_api.py -q` passed: 67 tests, including channel report and relay feedback review filters for assigned, reviewed, unassigned, unreviewed, and escalation queries.
- `.\.venv312\Scripts\python.exe -m pytest -q` passed: 650 tests.
- `.\.venv312\Scripts\python.exe -m compileall bot scripts tests` passed.
- `git diff --check` passed with only Windows LF-to-CRLF working-copy warnings.
- `.\.venv312\Scripts\python.exe -m pytest tests\test_platform_foundation.py::TestChannelFoundation::test_channel_admin_detail_includes_report_history_without_public_leak tests\test_platform_api.py::TestPlatformAPI::test_admin_api_reads_channel_report_detail_history tests\test_platform_api.py::TestPlatformAPI::test_platform_review_app_requires_admin_session_and_uses_admin_review_api -q` passed: 3 tests.
- `.\.venv312\Scripts\python.exe -m pytest tests\test_platform_foundation.py tests\test_platform_api.py -q` passed: 67 tests, including admin-only structured channel moderation history and public channel audit redaction.
- `.\.venv312\Scripts\python.exe -m pytest -q` passed: 650 tests.
- `.\.venv312\Scripts\python.exe -m compileall bot scripts tests` passed.
- `git diff --check` passed with only Windows LF-to-CRLF working-copy warnings.
- `.\.venv312\Scripts\python.exe -m pytest tests\test_platform_api.py::TestPlatformAPI::test_reviewer_init_data_can_use_channel_review_api_without_admin_session tests\test_platform_api.py::TestPlatformAPI::test_reviewer_init_data_can_use_relay_review_api_without_admin_session -q` passed: 2 tests.
- `.\.venv312\Scripts\python.exe -m pytest tests\test_platform_foundation.py tests\test_platform_api.py -q` passed: 69 tests, including reviewer-role Mini App auth for channel/relay review APIs and risk-operator-only risk escalation.
- `.\.venv312\Scripts\python.exe -m pytest -q` passed: 652 tests.
- `.\.venv312\Scripts\python.exe -m compileall bot scripts tests` passed.
- `git diff --check` passed with only Windows LF-to-CRLF working-copy warnings.
- `.\.venv312\Scripts\python.exe -m compileall bot scripts tests` passed.
- `.\.venv312\Scripts\python.exe -m pytest tests\test_platform_foundation.py tests\test_platform_api.py -q` passed: 67 tests, including live Bot-admin channel-claim approval and failure paths with Telegram API mocked.
- `.\.venv312\Scripts\python.exe -m pytest -q` passed: 650 tests.
- `git diff --check` passed with only Windows LF-to-CRLF working-copy warnings.
- Virginia invite settlement production enablement passed: read-only precheck found 0 mature unrewarded rewards, manual service run returned `settled=0` and `blocked=0`, the timer-triggered run returned `settled=0` and `blocked=0`, and `tgsellbot-invite-settle.timer` is enabled and active.
- `.\.venv312\Scripts\python.exe -m pytest tests\test_platform_foundation.py::TestRelayAndModelLabFoundation::test_owner_dashboard_lists_only_owned_resources_with_public_metrics tests\test_platform_api.py::TestPlatformAPI::test_owner_dashboard_api_is_mini_app_user_scoped tests\test_platform_api.py::TestPlatformAPI::test_platform_mini_app_page_uses_telegram_init_data_and_safe_entrypoints -q` passed: 3 tests.
- `.\.venv312\Scripts\python.exe -m pytest tests\test_platform_foundation.py tests\test_platform_api.py tests\test_platform_ops.py -q` passed: 67 tests.
- `.\.venv312\Scripts\python.exe -m compileall bot scripts tests` passed.
- `.\.venv312\Scripts\python.exe -m pytest -q` passed: 638 tests.
- `git diff --check` passed with only Windows LF-to-CRLF working-copy warnings.
- `.\.venv312\Scripts\python.exe -m pytest tests\test_platform_foundation.py::TestRelayAndModelLabFoundation::test_admin_review_workload_metrics_track_assignments_thresholds_and_alerts tests\test_platform_api.py::TestPlatformAPI::test_admin_review_workload_is_session_only_and_reports_assignments tests\test_platform_api.py::TestPlatformAPI::test_platform_review_app_requires_admin_session_and_uses_admin_review_api -q` passed: 3 tests.
- `.\.venv312\Scripts\python.exe -m pytest tests\test_platform_foundation.py tests\test_platform_api.py tests\test_platform_ops.py -q` passed: 69 tests.
- `.\.venv312\Scripts\python.exe -m compileall bot scripts tests` passed.
- `.\.venv312\Scripts\python.exe -m pytest -q` passed: 640 tests.
- `git diff --check` passed with only Windows LF-to-CRLF working-copy warnings.
- `.\.venv312\Scripts\python.exe -m pytest tests\test_platform_foundation.py::TestRelayAndModelLabFoundation::test_owner_dashboard_lists_only_owned_resources_with_public_metrics tests\test_platform_api.py::TestPlatformAPI::test_owner_dashboard_api_is_mini_app_user_scoped tests\test_platform_api.py::TestPlatformAPI::test_platform_review_app_requires_admin_session_and_uses_admin_review_api -q` passed: 3 tests.
- `.\.venv312\Scripts\python.exe -m pytest tests\test_platform_foundation.py tests\test_platform_api.py tests\test_platform_ops.py -q` passed: 67 tests.
- `.\.venv312\Scripts\python.exe -m compileall bot scripts tests` passed.
- `.\.venv312\Scripts\python.exe -m pytest -q` passed: 638 tests.
- `git diff --check` passed with only Windows LF-to-CRLF working-copy warnings.
- After fixing the public report page `renderRunHistory` definition, the focused Model Lab report-history tests, platform group, `compileall`, full `pytest -q` (636 tests), and `git diff --check` were rerun successfully; `git diff --check` still reports only Windows LF-to-CRLF working-copy warnings.
- Temporary local HTTP smoke for `http://127.0.0.1:9191/platform/reports` returned 200 with the `TGSellBot Model Lab Report` page content; the in-app browser webview attach timed out before DOM sampling, so browser-level visual QA was not completed.
- `.\.venv312\Scripts\python.exe -m pytest tests\test_platform_foundation.py::TestRelayAndModelLabFoundation::test_platform_audit_logs_filter_page_and_redact_sensitive_details tests\test_platform_api.py::TestPlatformAPI::test_admin_audit_logs_are_session_only_filtered_and_redacted tests\test_platform_api.py::TestPlatformAPI::test_platform_review_app_requires_admin_session_and_uses_admin_review_api -q` passed: 3 tests.
- `.\.venv312\Scripts\python.exe -m pytest tests\test_platform_foundation.py tests\test_platform_api.py tests\test_platform_ops.py -q` passed: 71 tests.
- `.\.venv312\Scripts\python.exe -m compileall bot scripts tests` passed.
- `.\.venv312\Scripts\python.exe -m pytest -q` passed: 642 tests.
- `git diff --check` passed with only Windows LF-to-CRLF working-copy warnings.
- `.\.venv312\Scripts\python.exe -m pytest tests\test_platform_foundation.py::TestRelayAndModelLabFoundation::test_model_test_dispatcher_runs_once_and_marks_failure tests\test_platform_api.py::TestPlatformAPI::test_public_model_report_entries_are_visibility_scoped_and_redacted tests\test_platform_api.py::TestPlatformAPI::test_platform_mini_app_page_uses_telegram_init_data_and_safe_entrypoints tests\test_platform_api.py::TestPlatformAPI::test_public_report_page_uses_public_api_without_telegram_init_data -q` passed: 4 tests.
- `.\.venv312\Scripts\python.exe -m pytest tests\test_platform_foundation.py tests\test_platform_api.py -q` passed: 67 tests, including live Bot-admin channel-claim approval and failure paths with Telegram API mocked.
- `.\.venv312\Scripts\python.exe -m pytest tests\test_platform_foundation.py tests\test_platform_api.py tests\test_platform_ops.py -q` passed: 65 tests.
- `.\.venv312\Scripts\python.exe -m compileall bot scripts tests` passed.
- `.\.venv312\Scripts\python.exe -m pytest -q` passed: 636 tests.
- `git diff --check` passed with only Windows LF-to-CRLF working-copy warnings.
- `.\.venv312\Scripts\python.exe -m pytest tests\test_platform_foundation.py::TestRelayAndModelLabFoundation::test_relay_feedback_review_tracks_internal_outcome_without_public_leak tests\test_platform_api.py::TestPlatformAPI::test_admin_session_can_filter_and_triage_relay_complaints tests\test_platform_api.py::TestPlatformAPI::test_platform_review_app_requires_admin_session_and_uses_admin_review_api -q` passed: 3 tests.
- `.\.venv312\Scripts\python.exe -m pytest tests\test_platform_foundation.py tests\test_platform_api.py -q` passed: 69 tests, including relay complaint follow-up states, follow-up filters, and review workspace actions.
- `.\.venv312\Scripts\python.exe -m compileall bot scripts tests` passed.
- `.\.venv312\Scripts\python.exe -m pytest -q` passed: 652 tests.
- `git diff --check` passed with only Windows LF-to-CRLF working-copy warnings.
- `.\.venv312\Scripts\python.exe -m pytest tests\test_platform_foundation.py::TestRelayAndModelLabFoundation::test_platform_dashboard_metrics_aggregate_current_foundation_without_fake_unavailable_values tests\test_platform_foundation.py::TestRelayAndModelLabFoundation::test_admin_review_workload_metrics_track_assignments_thresholds_and_alerts tests\test_platform_api.py::TestPlatformAPI::test_admin_dashboard_is_session_only_and_reports_unavailable_coverage tests\test_platform_api.py::TestPlatformAPI::test_platform_review_app_requires_admin_session_and_uses_admin_review_api -q` passed: 4 tests.
- `.\.venv312\Scripts\python.exe -m pytest tests\test_platform_foundation.py tests\test_platform_api.py -q` passed: 69 tests, including Platform Dashboard operating thresholds and alert rendering.
- `.\.venv312\Scripts\python.exe -m compileall bot scripts tests` passed.
- `.\.venv312\Scripts\python.exe -m pytest -q` passed: 652 tests.
- `git diff --check` passed with only Windows LF-to-CRLF working-copy warnings.
- `.\.venv312\Scripts\python.exe -m pytest tests\test_platform_foundation.py tests\test_platform_ops.py -q` passed: 49 tests, including Model Lab sample retention pruning and bounded systemd template safety.
- `.\.venv312\Scripts\python.exe -m compileall bot scripts tests` passed.
- `.\.venv312\Scripts\python.exe -m pytest -q` passed: 655 tests.
- `git diff --check` passed with only Windows LF-to-CRLF working-copy warnings.
- `.\.venv312\Scripts\python.exe -m pytest tests\test_platform_foundation.py tests\test_platform_api.py tests\test_platform_ops.py -q` passed: 86 tests, including redacted Model Lab ops audit events, dashboard readouts, and review workspace Model ops rendering.
- `.\.venv312\Scripts\python.exe -m compileall bot scripts tests` passed.
- `.\.venv312\Scripts\python.exe -m pytest -q` passed: 659 tests.
- `git diff --check` passed with only Windows LF-to-CRLF working-copy warnings.
- `.\.venv312\Scripts\python.exe -m pytest tests\test_model_lab_worker.py tests\test_platform_api.py tests\test_platform_ops.py -q` passed: 63 tests, including isolated Worker runner dispatch and Mini App `run_now` runner enforcement.
- `.\.venv312\Scripts\python.exe -m pytest tests\test_platform_foundation.py tests\test_platform_api.py tests\test_platform_ops.py -q` passed: 87 tests.
- `.\.venv312\Scripts\python.exe -m compileall -q bot scripts tests` passed.
- `.\.venv312\Scripts\python.exe -m pytest -q` passed: 662 tests.
- `.\.venv312\Scripts\python.exe -m pytest tests\test_platform_ops.py -q` passed: 15 tests, including Bot WebApp menu markup validation in the launch gate.
- `.\.venv312\Scripts\python.exe -m pytest tests\test_platform_foundation.py tests\test_platform_api.py tests\test_platform_ops.py -q` passed: 87 tests.
- `.\.venv312\Scripts\python.exe -m compileall -q bot scripts tests` passed.
- `.\.venv312\Scripts\python.exe -m pytest -q` passed: 662 tests.
- `git diff --check` passed with only Windows LF-to-CRLF working-copy warnings.
- `.\.venv312\Scripts\python.exe -m pytest tests\test_platform_ops.py -q` passed: 17 tests, including the read-only ledger cutover gate.
- `.\.venv312\Scripts\python.exe -m pytest tests\test_platform_foundation.py tests\test_platform_api.py tests\test_platform_ops.py -q` passed: 89 tests.
- `.\.venv312\Scripts\python.exe -m compileall -q bot scripts tests` passed.
- `.\.venv312\Scripts\python.exe -m pytest -q` passed: 664 tests.
- `git diff --check` passed with only Windows LF-to-CRLF working-copy warnings.
