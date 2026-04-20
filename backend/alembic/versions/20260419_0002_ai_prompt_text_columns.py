"""add missing ai prompt text columns

Revision ID: 20260419_0002
Revises: 20260419_0001
Create Date: 2026-04-19 23:05:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260419_0002"
down_revision = "20260419_0001"
branch_labels = None
depends_on = None


def _existing_columns(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    existing_columns = _existing_columns("ai_interactions")
    with op.batch_alter_table("ai_interactions") as batch_op:
        if "prompt_text" not in existing_columns:
            batch_op.add_column(sa.Column("prompt_text", sa.Text(), nullable=True))
        if "system_prompt_text" not in existing_columns:
            batch_op.add_column(sa.Column("system_prompt_text", sa.Text(), nullable=True))


def downgrade() -> None:
    existing_columns = _existing_columns("ai_interactions")
    with op.batch_alter_table("ai_interactions") as batch_op:
        if "system_prompt_text" in existing_columns:
            batch_op.drop_column("system_prompt_text")
        if "prompt_text" in existing_columns:
            batch_op.drop_column("prompt_text")
