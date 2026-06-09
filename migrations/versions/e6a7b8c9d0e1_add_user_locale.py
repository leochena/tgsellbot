"""add user locale preference

Revision ID: e6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-06-08 10:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'e6a7b8c9d0e1'
down_revision: Union[str, None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('locale', sa.String(length=8), nullable=True))
    op.create_index('ix_users_locale', 'users', ['locale'])


def downgrade() -> None:
    op.drop_index('ix_users_locale', table_name='users')
    op.drop_column('users', 'locale')
