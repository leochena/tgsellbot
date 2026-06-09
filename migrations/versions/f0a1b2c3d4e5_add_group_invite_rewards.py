"""add group invite rewards

Revision ID: f0a1b2c3d4e5
Revises: e9d0e1f2a3b4
Create Date: 2026-06-09 14:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f0a1b2c3d4e5'
down_revision: Union[str, None] = 'e9d0e1f2a3b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'group_invite_links',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('inviter_id', sa.BigInteger(), nullable=False),
        sa.Column('chat_id', sa.String(length=64), nullable=False),
        sa.Column('invite_link', sa.String(length=512), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['inviter_id'], ['users.telegram_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('invite_link', name='uq_group_invite_link_url'),
        sa.UniqueConstraint('inviter_id', 'chat_id', name='uq_group_invite_link_inviter_chat'),
    )
    op.create_index(op.f('ix_group_invite_links_chat_id'), 'group_invite_links', ['chat_id'], unique=False)
    op.create_index(op.f('ix_group_invite_links_inviter_id'), 'group_invite_links', ['inviter_id'], unique=False)
    op.create_index('ix_group_invite_links_chat_inviter', 'group_invite_links', ['chat_id', 'inviter_id'], unique=False)

    op.create_table(
        'group_invite_rewards',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('inviter_id', sa.BigInteger(), nullable=False),
        sa.Column('invited_id', sa.BigInteger(), nullable=False),
        sa.Column('chat_id', sa.String(length=64), nullable=False),
        sa.Column('invite_link', sa.String(length=512), nullable=True),
        sa.Column('joined_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('rewarded_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('points_awarded', sa.Integer(), nullable=False, server_default='0'),
        sa.CheckConstraint('inviter_id != invited_id', name='ck_group_invite_reward_no_self'),
        sa.ForeignKeyConstraint(['invited_id'], ['users.telegram_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['inviter_id'], ['users.telegram_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('invited_id', 'chat_id', name='uq_group_invite_reward_invited_chat'),
    )
    op.create_index(op.f('ix_group_invite_rewards_chat_id'), 'group_invite_rewards', ['chat_id'], unique=False)
    op.create_index(op.f('ix_group_invite_rewards_invited_id'), 'group_invite_rewards', ['invited_id'], unique=False)
    op.create_index(op.f('ix_group_invite_rewards_inviter_id'), 'group_invite_rewards', ['inviter_id'], unique=False)
    op.create_index('ix_group_invite_rewards_pending', 'group_invite_rewards', ['chat_id', 'invited_id', 'rewarded_at'], unique=False)
    op.create_index('ix_group_invite_rewards_inviter_joined', 'group_invite_rewards', ['inviter_id', 'joined_at'], unique=False)
    op.alter_column('group_invite_rewards', 'points_awarded', server_default=None)


def downgrade() -> None:
    op.drop_index('ix_group_invite_rewards_inviter_joined', table_name='group_invite_rewards')
    op.drop_index('ix_group_invite_rewards_pending', table_name='group_invite_rewards')
    op.drop_index(op.f('ix_group_invite_rewards_inviter_id'), table_name='group_invite_rewards')
    op.drop_index(op.f('ix_group_invite_rewards_invited_id'), table_name='group_invite_rewards')
    op.drop_index(op.f('ix_group_invite_rewards_chat_id'), table_name='group_invite_rewards')
    op.drop_table('group_invite_rewards')

    op.drop_index('ix_group_invite_links_chat_inviter', table_name='group_invite_links')
    op.drop_index(op.f('ix_group_invite_links_inviter_id'), table_name='group_invite_links')
    op.drop_index(op.f('ix_group_invite_links_chat_id'), table_name='group_invite_links')
    op.drop_table('group_invite_links')
