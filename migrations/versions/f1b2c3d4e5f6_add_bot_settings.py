"""add bot settings

Revision ID: f1b2c3d4e5f6
Revises: f0a1b2c3d4e5
Create Date: 2026-06-09 15:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f1b2c3d4e5f6'
down_revision: Union[str, None] = 'f0a1b2c3d4e5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'bot_settings',
        sa.Column('key', sa.String(length=128), nullable=False),
        sa.Column('value', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('key'),
    )
    op.execute(
        sa.text(
            """
            insert into bot_settings (key, value, description)
            values (
                'group_invite_share_template',
                '点击加入ai公益分享频道，{link}每日签到免费领取积分，积分可抽奖，兑换商品。gpt plus，接码，邮箱。',
                '邀请文案模板；{link} 会由系统替换为用户专属邀请链接。'
            )
            on conflict (key) do nothing
            """
        )
    )


def downgrade() -> None:
    op.drop_table('bot_settings')
