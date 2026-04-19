"""add ai streaming metadata

Revision ID: 20260419_0001
Revises:
Create Date: 2026-04-19 00:01:00.000000
"""

from collections.abc import Iterable

from alembic import op
import sqlalchemy as sa


revision = "20260419_0001"
down_revision = None
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def _existing_columns(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {column["name"] for column in inspector.get_columns(table_name)}


def _add_missing_columns(
    table_name: str,
    columns: Iterable[sa.Column],
) -> None:
    existing_columns = _existing_columns(table_name)
    with op.batch_alter_table(table_name) as batch_op:
        for column in columns:
            if column.name not in existing_columns:
                batch_op.add_column(column)


def upgrade() -> None:
    if not _table_exists("ai_interactions"):
        op.create_table(
            "ai_interactions",
            sa.Column("interaction_id", sa.String(length=36), nullable=False),
            sa.Column("document_id", sa.String(length=36), nullable=False),
            sa.Column("requested_by", sa.String(length=36), nullable=False),
            sa.Column("action_type", sa.String(length=50), nullable=False),
            sa.Column("scope_type", sa.String(length=50), nullable=False),
            sa.Column("selection_from", sa.Integer(), nullable=True),
            sa.Column("selection_to", sa.Integer(), nullable=True),
            sa.Column("base_revision_id", sa.String(length=100), nullable=True),
            sa.Column("prompt_template_version", sa.String(length=50), nullable=True),
            sa.Column("provider_name", sa.String(length=50), nullable=True),
            sa.Column("model_name", sa.String(length=100), nullable=True),
            sa.Column("model_profile", sa.String(length=100), nullable=True),
            sa.Column("prompt_text", sa.Text(), nullable=True),
            sa.Column("system_prompt_text", sa.Text(), nullable=True),
            sa.Column("error_code", sa.String(length=100), nullable=True),
            sa.Column("error_message", sa.String(length=500), nullable=True),
            sa.Column("status", sa.String(length=50), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["document_id"], ["documents.document_id"]),
            sa.ForeignKeyConstraint(["requested_by"], ["users.user_id"]),
            sa.PrimaryKeyConstraint("interaction_id"),
        )
    else:
        _add_missing_columns(
            "ai_interactions",
            [
                sa.Column("prompt_template_version", sa.String(length=50), nullable=True),
                sa.Column("provider_name", sa.String(length=50), nullable=True),
                sa.Column("model_name", sa.String(length=100), nullable=True),
                sa.Column("model_profile", sa.String(length=100), nullable=True),
                sa.Column("prompt_text", sa.Text(), nullable=True),
                sa.Column("system_prompt_text", sa.Text(), nullable=True),
                sa.Column("error_code", sa.String(length=100), nullable=True),
                sa.Column("error_message", sa.String(length=500), nullable=True),
            ],
        )

    if not _table_exists("ai_suggestions"):
        op.create_table(
            "ai_suggestions",
            sa.Column("suggestion_id", sa.String(length=36), nullable=False),
            sa.Column("interaction_id", sa.String(length=36), nullable=False),
            sa.Column("disposition", sa.String(length=50), nullable=False),
            sa.Column("stale", sa.Boolean(), nullable=False),
            sa.Column("original_text", sa.Text(), nullable=True),
            sa.Column("suggested_text", sa.Text(), nullable=True),
            sa.Column("partial_output_available", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("diff_json", sa.JSON(), nullable=True),
            sa.Column("accepted_segments_json", sa.JSON(), nullable=True),
            sa.Column("applied_revision_id", sa.String(length=100), nullable=True),
            sa.Column("applied_by", sa.String(length=36), nullable=True),
            sa.Column("applied_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["applied_by"], ["users.user_id"]),
            sa.ForeignKeyConstraint(["interaction_id"], ["ai_interactions.interaction_id"]),
            sa.PrimaryKeyConstraint("suggestion_id"),
        )
    else:
        _add_missing_columns(
            "ai_suggestions",
            [
                sa.Column(
                    "partial_output_available",
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.false(),
                ),
            ],
        )


def downgrade() -> None:
    existing_ai_suggestion_columns = (
        _existing_columns("ai_suggestions") if _table_exists("ai_suggestions") else set()
    )
    existing_ai_interaction_columns = (
        _existing_columns("ai_interactions") if _table_exists("ai_interactions") else set()
    )

    removable_suggestion_columns = ["partial_output_available"]
    removable_interaction_columns = [
        "error_message",
        "error_code",
        "system_prompt_text",
        "prompt_text",
        "model_profile",
        "model_name",
        "provider_name",
        "prompt_template_version",
    ]

    if existing_ai_suggestion_columns:
        with op.batch_alter_table("ai_suggestions") as batch_op:
            for column_name in removable_suggestion_columns:
                if column_name in existing_ai_suggestion_columns:
                    batch_op.drop_column(column_name)

    if existing_ai_interaction_columns:
        with op.batch_alter_table("ai_interactions") as batch_op:
            for column_name in removable_interaction_columns:
                if column_name in existing_ai_interaction_columns:
                    batch_op.drop_column(column_name)
