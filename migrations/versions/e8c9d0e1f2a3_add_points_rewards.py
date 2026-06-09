"""add points rewards

Revision ID: e8c9d0e1f2a3
Revises: e7b8c9d0e1f2
Create Date: 2026-06-08 22:55:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e8c9d0e1f2a3'
down_revision: Union[str, None] = 'e7b8c9d0e1f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('points_balance', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('goods', sa.Column('points_price', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('checkins', sa.Column('points_awarded', sa.Integer(), nullable=False, server_default='0'))
    op.alter_column('users', 'points_balance', server_default=None)
    op.alter_column('goods', 'points_price', server_default=None)
    op.alter_column('checkins', 'points_awarded', server_default=None)


def downgrade() -> None:
    op.drop_column('checkins', 'points_awarded')
    op.drop_column('goods', 'points_price')
    op.drop_column('users', 'points_balance')
