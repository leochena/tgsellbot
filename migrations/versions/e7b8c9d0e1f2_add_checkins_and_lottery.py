"""add checkins and lottery

Revision ID: e7b8c9d0e1f2
Revises: e6a7b8c9d0e1
Create Date: 2026-06-08 11:20:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'e7b8c9d0e1f2'
down_revision: Union[str, None] = 'e6a7b8c9d0e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'checkins',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('checkin_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('reward_amount', sa.Numeric(12, 2), nullable=False),
        sa.Column('tickets_awarded', sa.Integer(), nullable=False),
        sa.Column('streak', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.telegram_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'checkin_date', name='uq_checkins_user_date'),
    )
    op.create_index('ix_checkins_user_id', 'checkins', ['user_id'])
    op.create_index('ix_checkins_date', 'checkins', ['checkin_date'])

    op.create_table(
        'lottery_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=128), nullable=False),
        sa.Column('prize', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('winner_user_id', sa.BigInteger(), nullable=True),
        sa.Column('created_by', sa.BigInteger(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['users.telegram_id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['winner_user_id'], ['users.telegram_id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_lottery_events_status', 'lottery_events', ['status'])
    op.create_index('ix_lottery_events_winner_user_id', 'lottery_events', ['winner_user_id'])
    op.create_index('ix_lottery_events_created_by', 'lottery_events', ['created_by'])
    op.create_index('ix_lottery_events_status_created', 'lottery_events', ['status', 'created_at'])

    op.create_table(
        'lottery_entries',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('event_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('source', sa.String(length=32), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['event_id'], ['lottery_events.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.telegram_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_lottery_entries_event_id', 'lottery_entries', ['event_id'])
    op.create_index('ix_lottery_entries_user_id', 'lottery_entries', ['user_id'])
    op.create_index('ix_lottery_entries_event_user', 'lottery_entries', ['event_id', 'user_id'])


def downgrade() -> None:
    op.drop_index('ix_lottery_entries_event_user', table_name='lottery_entries')
    op.drop_index('ix_lottery_entries_user_id', table_name='lottery_entries')
    op.drop_index('ix_lottery_entries_event_id', table_name='lottery_entries')
    op.drop_table('lottery_entries')

    op.drop_index('ix_lottery_events_status_created', table_name='lottery_events')
    op.drop_index('ix_lottery_events_created_by', table_name='lottery_events')
    op.drop_index('ix_lottery_events_winner_user_id', table_name='lottery_events')
    op.drop_index('ix_lottery_events_status', table_name='lottery_events')
    op.drop_table('lottery_events')

    op.drop_index('ix_checkins_date', table_name='checkins')
    op.drop_index('ix_checkins_user_id', table_name='checkins')
    op.drop_table('checkins')
