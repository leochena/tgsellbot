# TGSellBot Agent Rules

This is the entry point for agents working in this repository. Keep it focused on behavior and process. Architecture facts, testing rules, and delivery gates live in the companion files listed below.

## Rule Index

Read these files before non-trivial work:

- `AGENTS.md`: agent behavior, scope control, permission policy, and product non-negotiables.
- `ARCHITECTURE.md`: current system structure, target upgrade boundaries, data rules, and security architecture.
- `TESTING.md`: test strategy, focused test matrix, mocking policy, and verification commands.
- `CI_STATUS.md`: definition of done, blocking checks, release and migration gates.
- `README.md`, `README.zh-CN.md`, and `docs/OPERATIONS.md`: user-facing setup and operations context.

Parent engineering-methods source:

- Repository: `https://github.com/leochena/agent-methods.git`
- Verified through SSH on `2026-06-17`; default branch `main`; observed HEAD `05dd44b` (`docs: update governance delivery assets`).
- Adopted methods: layered project governance, closed-loop delivery, regression-first validation, plan/worktree mode, permission policy, governance validation loop, issue closeout, and repo closeout.

For OpenAI APIs, SDKs, models, Agents SDK, ChatGPT Apps, Codex configuration, or Cookbook examples, verify against official OpenAI documentation first. Prefer bundled OpenAI docs tooling over general web search.

## Product Non-Negotiables

- Do not rebuild a second full Telegram bot. The target product is the existing Bot brand entry plus a Mini App, modular backend services, and an isolated model-test Worker.
- Preserve current account, balance, points, invite, language, shop, admin, payment, audit, metrics, and recovery capabilities unless a task explicitly proves they must change.
- Keep shop, wallet, payment, and digital delivery decoupled from channel discovery and model testing.
- Model testing may evaluate protocol compatibility, declared-model consistency, observed behavior, degradation risk, and historical stability. It must not claim black-box tests can prove the real upstream model with certainty.
- User API keys must not be collected in Telegram chat, stored in the main database, written to browser storage, persisted in logs, or exposed in reports.
- User-submitted URLs are high risk. Model-test Workers must block localhost, private ranges, link-local ranges, cloud metadata services, database ports, admin panels, suspicious redirects, DNS rebinding, non-HTTPS P0 targets, and abnormal ports.

## Closed-Loop Delivery

- Resolve ambiguity from repository evidence before escalating for clarification when possible.
- For non-trivial tasks, plan before implementation. A non-trivial task is one that crosses modules, changes schema, touches payments/security, changes public behavior, or needs a migration/release decision.
- Define the verification matrix before or during implementation, not after writing the final response.
- Implement the smallest correct change inside existing module boundaries. Do not introduce parallel mechanisms when a local pattern already exists.
- Never report a task complete without running relevant verification or clearly stating what could not be run.
- Keep diffs surgical. Do not mix unrelated refactors, formatting churn, generated files, or local artifacts into the same change.
- Do not revert unrelated local changes. If the worktree is dirty, identify which changes are yours and work around user-owned changes.

## Plan, Branch, And Worktree Policy

- Use plan-first execution for work involving architecture, data flow, permissions, migrations, payments, security, or more than three files.
- Use a dedicated branch for issue-sized work. Branch names should be short and traceable, for example `feat/channel-submissions` or `fix/payment-idempotency`.
- Use a separate worktree when the current workspace is dirty, when tasks run in parallel, or when the change has high interference risk.
- If a worktree is created, record its branch, baseline, purpose, and cleanup decision. Do not leave task worktrees behind by accident.
- After issue or PR completion, run a repo closeout pass: check status, stale branches/worktrees, docs drift, and temporary noise.

## Regression-First Quality Gate

- Do not validate only the exact lines changed.
- Treat shared modules, startup paths, config loading, middleware, database methods, payment paths, admin views, cache invalidation, and i18n as high-regression-risk areas.
- When a change touches shared behavior, run targeted tests for direct paths plus adjacent risk paths.
- When reporting a bug or review finding, provide reproduction path, file location, impact, and fix direction.

## Permission Policy

- Low-risk read-only actions are allowed: file reads, text search, git status/log/diff, local docs inspection, and non-mutating diagnostics.
- Medium-risk actions require explicit user intent or an already clear task: code edits, dependency installation, service restarts, migrations against local data, commits, pushes, PRs, and external side effects.
- High-risk actions are denied unless the user explicitly requests them and the rollback/safety plan is clear: destructive git operations, production writes, secret rotation, database destructive changes, force push, broad cleanup, deployment, and irreversible file deletion.
- Never write broad allow rules for shells, interpreters, `eval`, or wildcard command execution. Keep permissions specific and explainable.
- Production or customer data work must be metadata-only by default. Never print raw tokens, API keys, passwords, private keys, database dumps, or raw sensitive payloads.

## Codebase Conventions

- Python target is 3.11+; the local Windows workflow commonly uses `.venv312`.
- Keep async behavior native. Do not add blocking database, HTTP, or file work to bot handlers without moving it out of the event path.
- Follow existing layout:
  - `bot/handlers` for Telegram flows,
  - `bot/database/models` and `bot/database/methods` for persistence,
  - `bot/middleware` for request controls,
  - `bot/misc/services` for recovery, payment, and background services,
  - `bot/web` and `templates/sqladmin` for admin and web surfaces,
  - `migrations/versions` for schema changes,
  - `tests` for focused regression coverage.
- Prefer existing helpers for validation, stock formatting, metrics, audit logging, cache invalidation, and i18n.
- Keep UI strings centralized through existing i18n/admin-i18n patterns. Core user flows should preserve current supported locales: `ru`, `en`, and `zh`.
- Schema changes require Alembic migrations and matching model/test updates.
- Admin financial tables, payment records, operations, and audit logs should remain read-only in generic SQLAdmin views unless a task explicitly introduces an audited, permission-gated workflow.
- Do not commit `.env`, tokens, private keys, database dumps, production logs, uploaded stock data, coverage output, or local runtime artifacts.

## Commit And PR Standards

- Use focused commits. Prefer conventional prefixes already common in this repo, such as `feat:`, `fix:`, `test:`, `docs:`, `refactor:`, and `chore:`.
- PR descriptions should include problem, approach, validation, risk, and explicitly excluded work.
- Logic changes need tests. If no automated test is practical, document the manual or smoke verification path.
- Documentation must be updated when setup, configuration, user-facing behavior, API shape, migration steps, or operations flow changes.

