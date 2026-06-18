# TGSellBot Architecture And Product Boundaries

This file records durable system structure and target upgrade boundaries for the AI channel and model validation platform.

## Current System

TGSellBot is a Python Telegram shop bot built around:

- aiogram 3.x for Telegram bot flows,
- async SQLAlchemy 2.x with `asyncpg` for PostgreSQL,
- Alembic migrations,
- optional Redis for FSM storage and caching,
- SQLAdmin and Starlette for local/admin web surfaces,
- payments through Telegram Stars, Telegram provider-token checkout, and CryptoPay,
- digital stock delivery, cart checkout, promo codes, reviews, points, group invites, lottery, metrics, recovery, cleanup, and audit logging.

Core source layout:

- `bot/main.py`: bot startup, middleware, webhook/polling, recovery, cleanup, admin web server.
- `bot/database/models/main.py`: SQLAlchemy models and default role/settings initialization.
- `bot/database/methods`: data access and transactional business logic.
- `bot/handlers`: Telegram user/admin flows.
- `bot/middleware`: rate limiting, authentication, locale, and security controls.
- `bot/misc/services`: payment, recovery, cleanup, and broadcast services.
- `bot/web`: SQLAdmin app, export endpoints, health/metrics, and admin i18n.
- `templates/sqladmin`: admin UI templates.
- `migrations/versions`: database migrations.
- `tests`: async SQLite-backed regression tests with fake cache and mocked external APIs.

## Target Product Architecture

The upgrade brief defines the target as a Telegram AI resource platform, not a replacement bot:

```text
Telegram users
  |
  +-- Existing Bot Gateway: commands, buttons, notifications, payments, invites
  |
  +-- Telegram Mini App: channel discovery, submissions, relay tests, reports
       |
       v
API/Auth Gateway
  |
  +-- User/shop/wallet services
  +-- Channel Hub
  +-- Relay Directory
  +-- Model Lab Orchestrator
       |
       v
PostgreSQL + Redis/Queue + isolated model-test Worker
```

The isolated Worker must be a separate trust boundary. It should not have main database or internal admin-network access.

## Product Modules

P0 modules:

- Channel center: submissions, review state, details, search, favorites, reports, and owner claim.
- Relay directory: provider submission, review, protocol metadata, site profile, community evaluation, and risk labels.
- Model Lab P0: URL safety checks, model list, chat, streaming, latency, JSON output, basic tool-call compatibility, private reports, and redacted public reports.
- Growth and accounting: contribution tasks, invite maturation, append-only ledger entries, feature flags, audit logging, and admin review pages.

P1 modules:

- recommendations, leaderboards, cross-promotion campaigns, owner dashboards, historical relay status, multimodal tests, long context, reference evaluations, repeated sampling, and richer dashboards.

P2 modules:

- topic clustering, cross-language recommendation, SLA/price trends, public APIs, dynamic-route analysis, and community model fingerprints.

## Data Invariants

- Existing users, balances, orders, purchased goods, payments, roles, and audit records must survive upgrades.
- Platform balance/credits and contribution points are separate accounts. Do not blur them with Telegram Stars/XTR.
- Balance and points changes should move toward append-only ledger entries. Corrections should use reverse entries, not physical mutation of financial history.
- A new user can have only one first valid referrer. Do not overwrite first attribution.
- Invite rewards mature through behavior: started, active/joined, pending 72h, retained 72h, qualified 7d, rewarded, risk review, rejected.
- Detection jobs require idempotency keys so retries and duplicate webhooks do not double-charge or double-reward.
- Reports must store test-suite version, test time, declared model, observed model fields, score/grade, evidence summary, visibility, and limitation wording.
- Normalize and hash external URLs where relevant. Public reports must redact paths, query parameters, API keys, prompts, responses, and sensitive evidence.

## Security Boundaries

- P0 relay testing should allow HTTPS only and restrict ports.
- DNS resolution and every redirect hop must be revalidated.
- Block localhost, RFC1918/private ranges, link-local ranges, IPv6 local/private forms, cloud metadata services, database ports, admin panels, and non-standard IP representations.
- Limit task duration, response size, downloads, concurrency, and token budget.
- Do not execute target-site code or auto-download executables.
- One-time API keys stay short-lived and memory-scoped in the isolated path. Logs and reports may store irreversible fingerprints and masked forms only.
- Site-owner continuous monitoring keys must be dedicated, low-limit, revocable, and encrypted through a separate key-management path.
- High-risk admin actions need audit records with before/after values where applicable.
- Human report review may change only platform display conclusions. It must not rewrite original test evidence without retaining a versioned audit trail.

## Telegram And Payment Boundaries

- Production Telegram delivery should use Webhook mode only when secret-token validation and idempotency are in place.
- Mini App server code must validate `initData`; never trust `initDataUnsafe`.
- Channel invite-link attribution and member verification require the Bot to have corresponding channel admin permissions.
- Save Telegram payment charge IDs for audit and refunds.
- Digital goods and digital services inside Telegram should use Telegram Stars/XTR when required by Telegram rules.
- Keep `/paysupport`, privacy explanation, data deletion flow, and support process available when payment or personal data features change.

## Navigation Direction

The first-level product navigation should converge around:

- channel discovery,
- interface/model testing,
- contribution tasks,
- shop,
- profile,
- help/rules.

Secondary features such as check-in, lottery, cart, language, promo redemption, purchased goods, and operation history should move under profile or shop-level flows where practical.

