"""add points limits and lottery pool

Revision ID: e9d0e1f2a3b4
Revises: e8c9d0e1f2a3
Create Date: 2026-06-08 23:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e9d0e1f2a3b4'
down_revision: Union[str, None] = 'e8c9d0e1f2a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('goods', sa.Column('points_max_per_redeem', sa.Integer(), nullable=False, server_default='1'))
    op.add_column('goods', sa.Column('lottery_enabled', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('goods', sa.Column('lottery_level', sa.String(length=64), nullable=False, server_default=''))
    op.add_column('goods', sa.Column('lottery_winners_count', sa.Integer(), nullable=False, server_default='1'))
    op.create_index(op.f('ix_goods_lottery_enabled'), 'goods', ['lottery_enabled'], unique=False)

    op.add_column('lottery_events', sa.Column('draw_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('lottery_events', sa.Column('min_entries', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('lottery_events', sa.Column('min_users', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('lottery_events', sa.Column('auto_draw_enabled', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_index(op.f('ix_lottery_events_draw_at'), 'lottery_events', ['draw_at'], unique=False)
    op.create_index(op.f('ix_lottery_events_auto_draw_enabled'), 'lottery_events', ['auto_draw_enabled'], unique=False)

    op.create_table(
        'lottery_winners',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('event_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('goods_id', sa.Integer(), nullable=True),
        sa.Column('goods_name', sa.String(length=100), nullable=False),
        sa.Column('prize_level', sa.String(length=64), nullable=False),
        sa.Column('ticket_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['event_id'], ['lottery_events.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['goods_id'], ['goods.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['user_id'], ['users.telegram_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('event_id', 'user_id', 'goods_id', name='uq_lottery_winner_event_user_goods'),
    )
    op.create_index(op.f('ix_lottery_winners_event_id'), 'lottery_winners', ['event_id'], unique=False)
    op.create_index(op.f('ix_lottery_winners_goods_id'), 'lottery_winners', ['goods_id'], unique=False)
    op.create_index(op.f('ix_lottery_winners_user_id'), 'lottery_winners', ['user_id'], unique=False)
    op.create_index('ix_lottery_winners_event_level', 'lottery_winners', ['event_id', 'prize_level'], unique=False)

    op.alter_column('goods', 'points_max_per_redeem', server_default=None)
    op.alter_column('goods', 'lottery_enabled', server_default=None)
    op.alter_column('goods', 'lottery_level', server_default=None)
    op.alter_column('goods', 'lottery_winners_count', server_default=None)
    op.alter_column('lottery_events', 'min_entries', server_default=None)
    op.alter_column('lottery_events', 'min_users', server_default=None)
    op.alter_column('lottery_events', 'auto_draw_enabled', server_default=None)
    op.alter_column('lottery_winners', 'ticket_count', server_default=None)


def downgrade() -> None:
    op.drop_index('ix_lottery_winners_event_level', table_name='lottery_winners')
    op.drop_index(op.f('ix_lottery_winners_user_id'), table_name='lottery_winners')
    op.drop_index(op.f('ix_lottery_winners_goods_id'), table_name='lottery_winners')
    op.drop_index(op.f('ix_lottery_winners_event_id'), table_name='lottery_winners')
    op.drop_table('lottery_winners')

    op.drop_index(op.f('ix_lottery_events_auto_draw_enabled'), table_name='lottery_events')
    op.drop_index(op.f('ix_lottery_events_draw_at'), table_name='lottery_events')
    op.drop_column('lottery_events', 'auto_draw_enabled')
    op.drop_column('lottery_events', 'min_users')
    op.drop_column('lottery_events', 'min_entries')
    op.drop_column('lottery_events', 'draw_at')

    op.drop_index(op.f('ix_goods_lottery_enabled'), table_name='goods')
    op.drop_column('goods', 'lottery_winners_count')
    op.drop_column('goods', 'lottery_level')
    op.drop_column('goods', 'lottery_enabled')
    op.drop_column('goods', 'points_max_per_redeem')
