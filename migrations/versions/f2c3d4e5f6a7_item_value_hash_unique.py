"""use hash uniqueness for item values

Revision ID: f2c3d4e5f6a7
Revises: f1b2c3d4e5f6
Create Date: 2026-06-09 17:00:00.000000
"""
import hashlib
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f2c3d4e5f6a7'
down_revision: Union[str, None] = 'f1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _constraint_exists(bind, table_name: str, constraint_name: str) -> bool:
    return bool(
        bind.execute(
            sa.text(
                """
                select 1
                from pg_constraint
                where conrelid = to_regclass(:table_name)
                  and conname = :constraint_name
                """
            ),
            {"table_name": table_name, "constraint_name": constraint_name},
        ).first()
    )


def _column_exists(bind, table_name: str, column_name: str) -> bool:
    return bool(
        bind.execute(
            sa.text(
                """
                select 1
                from information_schema.columns
                where table_schema = current_schema()
                  and table_name = :table_name
                  and column_name = :column_name
                """
            ),
            {"table_name": table_name, "column_name": column_name},
        ).first()
    )


def upgrade() -> None:
    bind = op.get_bind()

    if not _column_exists(bind, "item_values", "value_hash"):
        op.add_column("item_values", sa.Column("value_hash", sa.String(length=64), nullable=True))

    rows = bind.execute(
        sa.text("select id, value from item_values where value_hash is null or value_hash = ''")
    ).mappings()
    for row in rows:
        value_hash = hashlib.sha256((row["value"] or "").encode("utf-8")).hexdigest()
        bind.execute(
            sa.text("update item_values set value_hash = :value_hash where id = :id"),
            {"id": row["id"], "value_hash": value_hash},
        )

    op.alter_column("item_values", "value_hash", existing_type=sa.String(length=64), nullable=False)

    for name in ("uq_item_value_per_item_new", "uq_item_value_per_item"):
        if _constraint_exists(bind, "item_values", name):
            op.drop_constraint(name, "item_values", type_="unique")

    if not _constraint_exists(bind, "item_values", "uq_item_value_hash_per_item"):
        op.create_unique_constraint(
            "uq_item_value_hash_per_item",
            "item_values",
            ["item_id", "value_hash"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    if _constraint_exists(bind, "item_values", "uq_item_value_hash_per_item"):
        op.drop_constraint("uq_item_value_hash_per_item", "item_values", type_="unique")
    if not _constraint_exists(bind, "item_values", "uq_item_value_per_item"):
        op.create_unique_constraint("uq_item_value_per_item", "item_values", ["item_id", "value"])
    if _column_exists(bind, "item_values", "value_hash"):
        op.drop_column("item_values", "value_hash")
