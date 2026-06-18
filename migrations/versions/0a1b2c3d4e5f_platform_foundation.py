"""platform foundation for channels relays model lab and ledger

Revision ID: 0a1b2c3d4e5f
Revises: f2c3d4e5f6a7
Create Date: 2026-06-17 19:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0a1b2c3d4e5f'
down_revision: Union[str, None] = 'f2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text(
        """
        insert into roles (name, default, permissions)
        values
            ('CHANNEL_OWNER', false, 1),
            ('STATION_OWNER', false, 1),
            ('REVIEWER', false, 137),
            ('RISK_OPERATOR', false, 137),
            ('OPERATOR', false, 139)
        on conflict (name) do nothing
        """
    ))
    op.execute(sa.text(
        """
        insert into bot_settings (key, value, description)
        values
            ('platform_menu_enabled', '0', 'Feature flag for AI channel discovery, contribution tasks, and Model Lab bot menu entries.'),
            ('platform_api_enabled', '0', 'Feature flag for platform API endpoints used by the Mini App and admin console.'),
            ('platform_webapp_url', '', 'Public HTTPS URL for the Telegram Mini App entry, usually https://your-domain/platform/app.')
        on conflict (key) do nothing
        """
    ))

    op.add_column('group_invite_rewards', sa.Column('status', sa.String(length=32), nullable=False, server_default='active'))
    op.add_column('group_invite_rewards', sa.Column('pending_until', sa.DateTime(timezone=True), nullable=True))
    op.add_column('group_invite_rewards', sa.Column('qualified_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('group_invite_rewards', sa.Column('risk_score', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('group_invite_rewards', sa.Column('risk_reason', sa.Text(), nullable=False, server_default=''))
    op.create_index('ix_group_invite_rewards_status', 'group_invite_rewards', ['status'], unique=False)
    op.create_index('ix_group_invite_rewards_pending_until', 'group_invite_rewards', ['pending_until'], unique=False)
    op.create_index('ix_group_invite_rewards_status_pending', 'group_invite_rewards', ['status', 'pending_until'], unique=False)

    op.create_table(
        'invite_retention_snapshots',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('reward_id', sa.Integer(), sa.ForeignKey('group_invite_rewards.id', ondelete='CASCADE'), nullable=False),
        sa.Column('inviter_id', sa.BigInteger(), sa.ForeignKey('users.telegram_id', ondelete='CASCADE'), nullable=False),
        sa.Column('invited_id', sa.BigInteger(), sa.ForeignKey('users.telegram_id', ondelete='CASCADE'), nullable=False),
        sa.Column('chat_id', sa.String(length=64), nullable=False),
        sa.Column('window_start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('window_end', sa.DateTime(timezone=True), nullable=False),
        sa.Column('activity_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('activity_type', sa.String(length=32), nullable=False, server_default='checkin'),
        sa.Column('retained_7d', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('reward_id', 'activity_type', 'activity_at', name='uq_invite_retention_reward_activity'),
    )
    op.create_index('ix_invite_retention_snapshots_reward_id', 'invite_retention_snapshots', ['reward_id'])
    op.create_index('ix_invite_retention_snapshots_inviter_id', 'invite_retention_snapshots', ['inviter_id'])
    op.create_index('ix_invite_retention_snapshots_invited_id', 'invite_retention_snapshots', ['invited_id'])
    op.create_index('ix_invite_retention_snapshots_chat_id', 'invite_retention_snapshots', ['chat_id'])
    op.create_index('ix_invite_retention_snapshots_window_end', 'invite_retention_snapshots', ['window_end'])
    op.create_index('ix_invite_retention_snapshots_activity_at', 'invite_retention_snapshots', ['activity_at'])
    op.create_index('ix_invite_retention_snapshots_activity_type', 'invite_retention_snapshots', ['activity_type'])
    op.create_index('ix_invite_retention_snapshots_retained_7d', 'invite_retention_snapshots', ['retained_7d'])
    op.create_index('ix_invite_retention_inviter_activity', 'invite_retention_snapshots', ['inviter_id', 'activity_at'])
    op.create_index('ix_invite_retention_window_retained', 'invite_retention_snapshots', ['window_end', 'retained_7d'])

    op.create_table(
        'ledger_entries',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.BigInteger(), sa.ForeignKey('users.telegram_id', ondelete='CASCADE'), nullable=False),
        sa.Column('account_type', sa.String(length=16), nullable=False),
        sa.Column('entry_type', sa.String(length=64), nullable=False),
        sa.Column('amount', sa.Numeric(14, 2), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False, server_default='available'),
        sa.Column('reference_type', sa.String(length=64), nullable=True),
        sa.Column('reference_id', sa.String(length=128), nullable=True),
        sa.Column('idempotency_key', sa.String(length=128), nullable=True, unique=True),
        sa.Column('available_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('reversed_id', sa.Integer(), sa.ForeignKey('ledger_entries.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("account_type IN ('balance', 'points')", name='ck_ledger_account_type'),
        sa.CheckConstraint("status IN ('pending', 'available', 'spent', 'reversed', 'expired')", name='ck_ledger_status'),
    )
    op.create_index('ix_ledger_entries_user_id', 'ledger_entries', ['user_id'])
    op.create_index('ix_ledger_entries_account_type', 'ledger_entries', ['account_type'])
    op.create_index('ix_ledger_entries_entry_type', 'ledger_entries', ['entry_type'])
    op.create_index('ix_ledger_entries_status', 'ledger_entries', ['status'])
    op.create_index('ix_ledger_entries_reference_type', 'ledger_entries', ['reference_type'])
    op.create_index('ix_ledger_entries_reference_id', 'ledger_entries', ['reference_id'])
    op.create_index('ix_ledger_entries_available_at', 'ledger_entries', ['available_at'])
    op.create_index('ix_ledger_user_account_created', 'ledger_entries', ['user_id', 'account_type', 'created_at'])
    op.create_index('ix_ledger_reference', 'ledger_entries', ['reference_type', 'reference_id'])

    op.create_table(
        'channels',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('telegram_chat_id', sa.BigInteger(), nullable=True, unique=True),
        sa.Column('username', sa.String(length=64), nullable=False, unique=True),
        sa.Column('title', sa.String(length=255), nullable=False, server_default=''),
        sa.Column('category', sa.String(length=64), nullable=False),
        sa.Column('language', sa.String(length=16), nullable=False),
        sa.Column('description', sa.Text(), nullable=False, server_default=''),
        sa.Column('owner_user_id', sa.BigInteger(), sa.ForeignKey('users.telegram_id', ondelete='SET NULL'), nullable=True),
        sa.Column('quality_score', sa.Numeric(6, 2), nullable=False, server_default='0'),
        sa.Column('risk_status', sa.String(length=32), nullable=False, server_default='normal'),
        sa.Column('risk_notes', sa.Text(), nullable=False, server_default=''),
        sa.Column('risk_reviewed_by', sa.BigInteger(), sa.ForeignKey('users.telegram_id', ondelete='SET NULL'), nullable=True),
        sa.Column('risk_reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('risk_assigned_to', sa.BigInteger(), sa.ForeignKey('users.telegram_id', ondelete='SET NULL'), nullable=True),
        sa.Column('risk_escalation', sa.String(length=32), nullable=False, server_default='none'),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='submitted'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_channels_username', 'channels', ['username'])
    op.create_index('ix_channels_category', 'channels', ['category'])
    op.create_index('ix_channels_language', 'channels', ['language'])
    op.create_index('ix_channels_owner_user_id', 'channels', ['owner_user_id'])
    op.create_index('ix_channels_risk_status', 'channels', ['risk_status'])
    op.create_index('ix_channels_risk_assigned_to', 'channels', ['risk_assigned_to'])
    op.create_index('ix_channels_risk_escalation', 'channels', ['risk_escalation'])
    op.create_index('ix_channels_status', 'channels', ['status'])
    op.create_index('ix_channels_category_language_status', 'channels', ['category', 'language', 'status'])

    op.create_table(
        'channel_submissions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('submitter_id', sa.BigInteger(), sa.ForeignKey('users.telegram_id', ondelete='CASCADE'), nullable=False),
        sa.Column('channel_id', sa.Integer(), sa.ForeignKey('channels.id', ondelete='CASCADE'), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False, server_default=''),
        sa.Column('commercial_content', sa.String(length=32), nullable=False, server_default='unknown'),
        sa.Column('submitter_relation', sa.String(length=32), nullable=False, server_default='recommender'),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='submitted'),
        sa.Column('review_notes', sa.Text(), nullable=False, server_default=''),
        sa.Column('reviewed_by', sa.BigInteger(), sa.ForeignKey('users.telegram_id', ondelete='SET NULL'), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('submitter_id', 'channel_id', name='uq_channel_submission_submitter_channel'),
    )
    op.create_index('ix_channel_submissions_submitter_id', 'channel_submissions', ['submitter_id'])
    op.create_index('ix_channel_submissions_channel_id', 'channel_submissions', ['channel_id'])
    op.create_index('ix_channel_submissions_status', 'channel_submissions', ['status'])
    op.create_index('ix_channel_submissions_status_created', 'channel_submissions', ['status', 'created_at'])

    op.create_table(
        'channel_claims',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('channel_id', sa.Integer(), sa.ForeignKey('channels.id', ondelete='CASCADE'), nullable=False),
        sa.Column('claimant_id', sa.BigInteger(), sa.ForeignKey('users.telegram_id', ondelete='CASCADE'), nullable=False),
        sa.Column('method', sa.String(length=32), nullable=False),
        sa.Column('challenge', sa.String(length=128), nullable=False, server_default=''),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='pending'),
        sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('channel_id', 'claimant_id', 'status', name='uq_channel_claim_open_status'),
    )
    op.create_index('ix_channel_claims_channel_id', 'channel_claims', ['channel_id'])
    op.create_index('ix_channel_claims_claimant_id', 'channel_claims', ['claimant_id'])
    op.create_index('ix_channel_claims_status', 'channel_claims', ['status'])

    op.create_table(
        'channel_interactions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.BigInteger(), sa.ForeignKey('users.telegram_id', ondelete='CASCADE'), nullable=False),
        sa.Column('channel_id', sa.Integer(), sa.ForeignKey('channels.id', ondelete='CASCADE'), nullable=False),
        sa.Column('action', sa.String(length=32), nullable=False),
        sa.Column('source', sa.String(length=64), nullable=False, server_default=''),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('user_id', 'channel_id', 'action', name='uq_channel_interaction_user_channel_action'),
    )
    op.create_index('ix_channel_interactions_user_id', 'channel_interactions', ['user_id'])
    op.create_index('ix_channel_interactions_channel_id', 'channel_interactions', ['channel_id'])
    op.create_index('ix_channel_interactions_action', 'channel_interactions', ['action'])
    op.create_index('ix_channel_interactions_channel_action', 'channel_interactions', ['channel_id', 'action'])

    op.create_table(
        'relay_providers',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(length=128), nullable=False),
        sa.Column('website_url', sa.String(length=512), nullable=False, server_default=''),
        sa.Column('base_url_normalized', sa.String(length=512), nullable=False),
        sa.Column('base_url_hash', sa.String(length=64), nullable=False, unique=True),
        sa.Column('public_base_url', sa.String(length=512), nullable=False, server_default=''),
        sa.Column('owner_user_id', sa.BigInteger(), sa.ForeignKey('users.telegram_id', ondelete='SET NULL'), nullable=True),
        sa.Column('protocol', sa.String(length=32), nullable=False),
        sa.Column('model_scope', sa.Text(), nullable=False, server_default=''),
        sa.Column('region', sa.String(length=64), nullable=False, server_default=''),
        sa.Column('pricing', sa.Text(), nullable=False, server_default=''),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='submitted'),
        sa.Column('reputation_score', sa.Numeric(6, 2), nullable=False, server_default='0'),
        sa.Column('risk_status', sa.String(length=32), nullable=False, server_default='new'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_relay_providers_name', 'relay_providers', ['name'])
    op.create_index('ix_relay_providers_base_url_hash', 'relay_providers', ['base_url_hash'])
    op.create_index('ix_relay_providers_owner_user_id', 'relay_providers', ['owner_user_id'])
    op.create_index('ix_relay_providers_protocol', 'relay_providers', ['protocol'])
    op.create_index('ix_relay_providers_status', 'relay_providers', ['status'])
    op.create_index('ix_relay_providers_risk_status', 'relay_providers', ['risk_status'])
    op.create_index('ix_relay_providers_protocol_status', 'relay_providers', ['protocol', 'status'])

    op.create_table(
        'relay_claims',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('provider_id', sa.Integer(), sa.ForeignKey('relay_providers.id', ondelete='CASCADE'), nullable=False),
        sa.Column('claimant_id', sa.BigInteger(), sa.ForeignKey('users.telegram_id', ondelete='CASCADE'), nullable=False),
        sa.Column('method', sa.String(length=32), nullable=False),
        sa.Column('challenge', sa.String(length=128), nullable=False, server_default=''),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='pending'),
        sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_relay_claims_provider_id', 'relay_claims', ['provider_id'])
    op.create_index('ix_relay_claims_claimant_id', 'relay_claims', ['claimant_id'])
    op.create_index('ix_relay_claims_status', 'relay_claims', ['status'])

    op.create_table(
        'relay_feedback',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('provider_id', sa.Integer(), sa.ForeignKey('relay_providers.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', sa.BigInteger(), sa.ForeignKey('users.telegram_id', ondelete='CASCADE'), nullable=False),
        sa.Column('feedback_type', sa.String(length=32), nullable=False),
        sa.Column('rating', sa.Integer(), nullable=True),
        sa.Column('text', sa.Text(), nullable=False, server_default=''),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='submitted'),
        sa.Column('review_notes', sa.Text(), nullable=False, server_default=''),
        sa.Column('reviewed_by', sa.BigInteger(), sa.ForeignKey('users.telegram_id', ondelete='SET NULL'), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('assigned_to', sa.BigInteger(), sa.ForeignKey('users.telegram_id', ondelete='SET NULL'), nullable=True),
        sa.Column('escalation', sa.String(length=32), nullable=False, server_default='none'),
        sa.Column('outcome', sa.String(length=32), nullable=False, server_default='none'),
        sa.Column('followup_notes', sa.Text(), nullable=False, server_default=''),
        sa.Column('resolved_by', sa.BigInteger(), sa.ForeignKey('users.telegram_id', ondelete='SET NULL'), nullable=True),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint('rating IS NULL OR (rating >= 1 AND rating <= 5)', name='ck_relay_feedback_rating_range'),
    )
    op.create_index('ix_relay_feedback_provider_id', 'relay_feedback', ['provider_id'])
    op.create_index('ix_relay_feedback_user_id', 'relay_feedback', ['user_id'])
    op.create_index('ix_relay_feedback_feedback_type', 'relay_feedback', ['feedback_type'])
    op.create_index('ix_relay_feedback_status', 'relay_feedback', ['status'])
    op.create_index('ix_relay_feedback_assigned_to', 'relay_feedback', ['assigned_to'])
    op.create_index('ix_relay_feedback_escalation', 'relay_feedback', ['escalation'])
    op.create_index('ix_relay_feedback_outcome', 'relay_feedback', ['outcome'])

    op.create_table(
        'test_suites',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('version', sa.String(length=64), nullable=False, unique=True),
        sa.Column('protocol', sa.String(length=32), nullable=False),
        sa.Column('items', sa.JSON(), nullable=False),
        sa.Column('enabled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_test_suites_version', 'test_suites', ['version'])
    op.create_index('ix_test_suites_protocol', 'test_suites', ['protocol'])

    op.create_table(
        'model_test_jobs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.BigInteger(), sa.ForeignKey('users.telegram_id', ondelete='CASCADE'), nullable=False),
        sa.Column('provider_id', sa.Integer(), sa.ForeignKey('relay_providers.id', ondelete='SET NULL'), nullable=True),
        sa.Column('endpoint_hash', sa.String(length=64), nullable=False),
        sa.Column('endpoint_normalized', sa.String(length=512), nullable=False),
        sa.Column('endpoint_public', sa.String(length=512), nullable=False, server_default=''),
        sa.Column('protocol', sa.String(length=32), nullable=False),
        sa.Column('requested_model', sa.String(length=128), nullable=False, server_default=''),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='created'),
        sa.Column('worker_id', sa.String(length=64), nullable=False, server_default=''),
        sa.Column('idempotency_key', sa.String(length=128), nullable=False, unique=True),
        sa.Column('key_fingerprint', sa.String(length=64), nullable=False, server_default=''),
        sa.Column('key_masked', sa.String(length=64), nullable=False, server_default=''),
        sa.Column('failure_reason', sa.String(length=255), nullable=False, server_default=''),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_model_test_jobs_user_id', 'model_test_jobs', ['user_id'])
    op.create_index('ix_model_test_jobs_provider_id', 'model_test_jobs', ['provider_id'])
    op.create_index('ix_model_test_jobs_endpoint_hash', 'model_test_jobs', ['endpoint_hash'])
    op.create_index('ix_model_test_jobs_protocol', 'model_test_jobs', ['protocol'])
    op.create_index('ix_model_test_jobs_status', 'model_test_jobs', ['status'])
    op.create_index('ix_model_test_jobs_user_status_created', 'model_test_jobs', ['user_id', 'status', 'created_at'])

    op.create_table(
        'model_test_reports',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('job_id', sa.Integer(), sa.ForeignKey('model_test_jobs.id', ondelete='CASCADE'), nullable=False, unique=True),
        sa.Column('declared_model', sa.String(length=128), nullable=False, server_default=''),
        sa.Column('returned_model', sa.String(length=128), nullable=False, server_default=''),
        sa.Column('suite_version', sa.String(length=64), nullable=False, server_default=''),
        sa.Column('scores', sa.JSON(), nullable=False),
        sa.Column('grade', sa.String(length=8), nullable=False, server_default='F'),
        sa.Column('evidence_json', sa.JSON(), nullable=False),
        sa.Column('visibility', sa.String(length=16), nullable=False, server_default='private'),
        sa.Column('limitation_note', sa.Text(), nullable=False, server_default=''),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_model_test_reports_visibility', 'model_test_reports', ['visibility'])

    op.create_table(
        'model_test_runs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('job_id', sa.Integer(), sa.ForeignKey('model_test_jobs.id', ondelete='CASCADE'), nullable=False),
        sa.Column('provider_id', sa.Integer(), sa.ForeignKey('relay_providers.id', ondelete='SET NULL'), nullable=True),
        sa.Column('worker_id', sa.String(length=64), nullable=False, server_default=''),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('duration_ms', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('request_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('estimated_cost', sa.Numeric(14, 6), nullable=True),
        sa.Column('error_type', sa.String(length=64), nullable=False, server_default=''),
        sa.Column('error_summary', sa.String(length=255), nullable=False, server_default=''),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('completed', 'failed', 'cancelled', 'timeout')", name='ck_model_test_run_status'),
    )
    op.create_index('ix_model_test_runs_job_id', 'model_test_runs', ['job_id'])
    op.create_index('ix_model_test_runs_provider_id', 'model_test_runs', ['provider_id'])
    op.create_index('ix_model_test_runs_worker_id', 'model_test_runs', ['worker_id'])
    op.create_index('ix_model_test_runs_status', 'model_test_runs', ['status'])
    op.create_index('ix_model_test_runs_status_created', 'model_test_runs', ['status', 'created_at'])
    op.create_index('ix_model_test_runs_provider_created', 'model_test_runs', ['provider_id', 'created_at'])

    op.create_table(
        'relay_availability_samples',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('provider_id', sa.Integer(), sa.ForeignKey('relay_providers.id', ondelete='CASCADE'), nullable=False),
        sa.Column('job_id', sa.Integer(), sa.ForeignKey('model_test_jobs.id', ondelete='SET NULL'), nullable=True),
        sa.Column('source', sa.String(length=64), nullable=False, server_default='model_test'),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('http_status', sa.Integer(), nullable=True),
        sa.Column('latency_ms', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('error_type', sa.String(length=64), nullable=False, server_default=''),
        sa.Column('error_summary', sa.String(length=255), nullable=False, server_default=''),
        sa.Column('checked_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('available', 'degraded', 'failed', 'unknown')", name='ck_relay_availability_status'),
    )
    op.create_index('ix_relay_availability_samples_provider_id', 'relay_availability_samples', ['provider_id'])
    op.create_index('ix_relay_availability_samples_job_id', 'relay_availability_samples', ['job_id'])
    op.create_index('ix_relay_availability_samples_source', 'relay_availability_samples', ['source'])
    op.create_index('ix_relay_availability_samples_status', 'relay_availability_samples', ['status'])
    op.create_index('ix_relay_availability_samples_checked_at', 'relay_availability_samples', ['checked_at'])
    op.create_index('ix_relay_availability_provider_checked', 'relay_availability_samples', ['provider_id', 'checked_at'])
    op.create_index('ix_relay_availability_status_checked', 'relay_availability_samples', ['status', 'checked_at'])

    op.create_table(
        'fraud_events',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('subject_type', sa.String(length=32), nullable=False),
        sa.Column('subject_id', sa.String(length=128), nullable=False),
        sa.Column('event_type', sa.String(length=64), nullable=False),
        sa.Column('evidence', sa.JSON(), nullable=False),
        sa.Column('score_delta', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='open'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_fraud_events_subject_type', 'fraud_events', ['subject_type'])
    op.create_index('ix_fraud_events_subject_id', 'fraud_events', ['subject_id'])
    op.create_index('ix_fraud_events_event_type', 'fraud_events', ['event_type'])
    op.create_index('ix_fraud_events_status', 'fraud_events', ['status'])


def downgrade() -> None:
    op.drop_index('ix_fraud_events_status', table_name='fraud_events')
    op.drop_index('ix_fraud_events_event_type', table_name='fraud_events')
    op.drop_index('ix_fraud_events_subject_id', table_name='fraud_events')
    op.drop_index('ix_fraud_events_subject_type', table_name='fraud_events')
    op.drop_table('fraud_events')
    op.drop_index('ix_relay_availability_status_checked', table_name='relay_availability_samples')
    op.drop_index('ix_relay_availability_provider_checked', table_name='relay_availability_samples')
    op.drop_index('ix_relay_availability_samples_checked_at', table_name='relay_availability_samples')
    op.drop_index('ix_relay_availability_samples_status', table_name='relay_availability_samples')
    op.drop_index('ix_relay_availability_samples_source', table_name='relay_availability_samples')
    op.drop_index('ix_relay_availability_samples_job_id', table_name='relay_availability_samples')
    op.drop_index('ix_relay_availability_samples_provider_id', table_name='relay_availability_samples')
    op.drop_table('relay_availability_samples')
    op.drop_index('ix_model_test_runs_provider_created', table_name='model_test_runs')
    op.drop_index('ix_model_test_runs_status_created', table_name='model_test_runs')
    op.drop_index('ix_model_test_runs_status', table_name='model_test_runs')
    op.drop_index('ix_model_test_runs_worker_id', table_name='model_test_runs')
    op.drop_index('ix_model_test_runs_provider_id', table_name='model_test_runs')
    op.drop_index('ix_model_test_runs_job_id', table_name='model_test_runs')
    op.drop_table('model_test_runs')
    op.drop_index('ix_model_test_reports_visibility', table_name='model_test_reports')
    op.drop_table('model_test_reports')
    op.drop_index('ix_model_test_jobs_user_status_created', table_name='model_test_jobs')
    op.drop_index('ix_model_test_jobs_status', table_name='model_test_jobs')
    op.drop_index('ix_model_test_jobs_protocol', table_name='model_test_jobs')
    op.drop_index('ix_model_test_jobs_endpoint_hash', table_name='model_test_jobs')
    op.drop_index('ix_model_test_jobs_provider_id', table_name='model_test_jobs')
    op.drop_index('ix_model_test_jobs_user_id', table_name='model_test_jobs')
    op.drop_table('model_test_jobs')
    op.drop_index('ix_test_suites_protocol', table_name='test_suites')
    op.drop_index('ix_test_suites_version', table_name='test_suites')
    op.drop_table('test_suites')
    op.drop_index('ix_relay_feedback_outcome', table_name='relay_feedback')
    op.drop_index('ix_relay_feedback_escalation', table_name='relay_feedback')
    op.drop_index('ix_relay_feedback_assigned_to', table_name='relay_feedback')
    op.drop_index('ix_relay_feedback_status', table_name='relay_feedback')
    op.drop_index('ix_relay_feedback_feedback_type', table_name='relay_feedback')
    op.drop_index('ix_relay_feedback_user_id', table_name='relay_feedback')
    op.drop_index('ix_relay_feedback_provider_id', table_name='relay_feedback')
    op.drop_table('relay_feedback')
    op.drop_index('ix_relay_claims_status', table_name='relay_claims')
    op.drop_index('ix_relay_claims_claimant_id', table_name='relay_claims')
    op.drop_index('ix_relay_claims_provider_id', table_name='relay_claims')
    op.drop_table('relay_claims')
    op.drop_index('ix_relay_providers_protocol_status', table_name='relay_providers')
    op.drop_index('ix_relay_providers_risk_status', table_name='relay_providers')
    op.drop_index('ix_relay_providers_status', table_name='relay_providers')
    op.drop_index('ix_relay_providers_protocol', table_name='relay_providers')
    op.drop_index('ix_relay_providers_owner_user_id', table_name='relay_providers')
    op.drop_index('ix_relay_providers_base_url_hash', table_name='relay_providers')
    op.drop_index('ix_relay_providers_name', table_name='relay_providers')
    op.drop_table('relay_providers')
    op.drop_index('ix_channel_interactions_channel_action', table_name='channel_interactions')
    op.drop_index('ix_channel_interactions_action', table_name='channel_interactions')
    op.drop_index('ix_channel_interactions_channel_id', table_name='channel_interactions')
    op.drop_index('ix_channel_interactions_user_id', table_name='channel_interactions')
    op.drop_table('channel_interactions')
    op.drop_index('ix_channel_claims_status', table_name='channel_claims')
    op.drop_index('ix_channel_claims_claimant_id', table_name='channel_claims')
    op.drop_index('ix_channel_claims_channel_id', table_name='channel_claims')
    op.drop_table('channel_claims')
    op.drop_index('ix_channel_submissions_status_created', table_name='channel_submissions')
    op.drop_index('ix_channel_submissions_status', table_name='channel_submissions')
    op.drop_index('ix_channel_submissions_channel_id', table_name='channel_submissions')
    op.drop_index('ix_channel_submissions_submitter_id', table_name='channel_submissions')
    op.drop_table('channel_submissions')
    op.drop_index('ix_channels_category_language_status', table_name='channels')
    op.drop_index('ix_channels_status', table_name='channels')
    op.drop_index('ix_channels_risk_escalation', table_name='channels')
    op.drop_index('ix_channels_risk_assigned_to', table_name='channels')
    op.drop_index('ix_channels_risk_status', table_name='channels')
    op.drop_index('ix_channels_owner_user_id', table_name='channels')
    op.drop_index('ix_channels_language', table_name='channels')
    op.drop_index('ix_channels_category', table_name='channels')
    op.drop_index('ix_channels_username', table_name='channels')
    op.drop_table('channels')
    op.drop_index('ix_ledger_reference', table_name='ledger_entries')
    op.drop_index('ix_ledger_user_account_created', table_name='ledger_entries')
    op.drop_index('ix_ledger_entries_available_at', table_name='ledger_entries')
    op.drop_index('ix_ledger_entries_reference_id', table_name='ledger_entries')
    op.drop_index('ix_ledger_entries_reference_type', table_name='ledger_entries')
    op.drop_index('ix_ledger_entries_status', table_name='ledger_entries')
    op.drop_index('ix_ledger_entries_entry_type', table_name='ledger_entries')
    op.drop_index('ix_ledger_entries_account_type', table_name='ledger_entries')
    op.drop_index('ix_ledger_entries_user_id', table_name='ledger_entries')
    op.drop_table('ledger_entries')
    op.drop_index('ix_invite_retention_window_retained', table_name='invite_retention_snapshots')
    op.drop_index('ix_invite_retention_inviter_activity', table_name='invite_retention_snapshots')
    op.drop_index('ix_invite_retention_snapshots_retained_7d', table_name='invite_retention_snapshots')
    op.drop_index('ix_invite_retention_snapshots_activity_type', table_name='invite_retention_snapshots')
    op.drop_index('ix_invite_retention_snapshots_activity_at', table_name='invite_retention_snapshots')
    op.drop_index('ix_invite_retention_snapshots_window_end', table_name='invite_retention_snapshots')
    op.drop_index('ix_invite_retention_snapshots_chat_id', table_name='invite_retention_snapshots')
    op.drop_index('ix_invite_retention_snapshots_invited_id', table_name='invite_retention_snapshots')
    op.drop_index('ix_invite_retention_snapshots_inviter_id', table_name='invite_retention_snapshots')
    op.drop_index('ix_invite_retention_snapshots_reward_id', table_name='invite_retention_snapshots')
    op.drop_table('invite_retention_snapshots')
    op.drop_index('ix_group_invite_rewards_status_pending', table_name='group_invite_rewards')
    op.drop_index('ix_group_invite_rewards_pending_until', table_name='group_invite_rewards')
    op.drop_index('ix_group_invite_rewards_status', table_name='group_invite_rewards')
    op.drop_column('group_invite_rewards', 'risk_reason')
    op.drop_column('group_invite_rewards', 'risk_score')
    op.drop_column('group_invite_rewards', 'qualified_at')
    op.drop_column('group_invite_rewards', 'pending_until')
    op.drop_column('group_invite_rewards', 'status')
