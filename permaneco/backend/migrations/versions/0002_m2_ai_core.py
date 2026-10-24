"""Add the M2 AI core schema."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app import models  # noqa: F401

revision = "0002_m2_ai_core"
down_revision = "0001_m1_foundation"
branch_labels = None
depends_on = None


def _columns(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def _add_column(table_name: str, column: sa.Column) -> None:
    if column.name not in _columns(table_name):
        op.add_column(table_name, column)


def upgrade() -> None:
    _add_column(
        "memories",
        sa.Column("category", sa.String(length=24), nullable=False, server_default="rotina"),
    )
    _add_column(
        "memories",
        sa.Column("is_sensitive", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    _add_column(
        "memories",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    _add_column(
        "memories",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    _add_column(
        "memories",
        sa.Column(
            "source_conversation_id",
            sa.Uuid(),
            sa.ForeignKey("conversations.id", ondelete="SET NULL"),
        ),
    )
    _add_column("plans", sa.Column("change_summary", sa.Text()))
    _add_column("next_steps", sa.Column("due_text", sa.Text()))
    _add_column("conversations", sa.Column("ended_at", sa.DateTime(timezone=True)))
    _add_column(
        "conversations",
        sa.Column("channel", sa.String(length=16), nullable=False, server_default="texto"),
    )

    knowledge_columns = _columns("knowledge_items")
    if "slug" not in knowledge_columns:
        op.add_column("knowledge_items", sa.Column("slug", sa.String(length=120)))
        op.execute("UPDATE knowledge_items SET slug = id::text WHERE slug IS NULL")
        op.alter_column("knowledge_items", "slug", nullable=False)
    if "kind" not in knowledge_columns:
        op.add_column(
            "knowledge_items",
            sa.Column("kind", sa.String(length=24), nullable=False, server_default="instituicao"),
        )
    if "verified_at" not in knowledge_columns:
        op.add_column("knowledge_items", sa.Column("verified_at", sa.Date()))
    if "search_vector" not in knowledge_columns:
        op.add_column(
            "knowledge_items",
            sa.Column(
                "search_vector",
                postgresql.TSVECTOR(),
                sa.Computed(
                    "to_tsvector('portuguese'::regconfig, coalesce(title, '') || ' ' || coalesce(content, ''))",
                    persisted=True,
                ),
            ),
        )

    bind = op.get_bind()
    if "plan_proposals" not in sa.inspect(bind).get_table_names():
        models.PlanProposal.__table__.create(bind, checkfirst=True)
    if "token_usage" not in sa.inspect(bind).get_table_names():
        models.TokenUsage.__table__.create(bind, checkfirst=True)
    if "uq_knowledge_items_slug" not in {
        item["name"] for item in sa.inspect(bind).get_unique_constraints("knowledge_items")
    }:
        op.create_unique_constraint("uq_knowledge_items_slug", "knowledge_items", ["slug"])
    if "ix_knowledge_items_search_vector" not in {
        item["name"] for item in sa.inspect(bind).get_indexes("knowledge_items")
    }:
        op.create_index(
            "ix_knowledge_items_search_vector",
            "knowledge_items",
            ["search_vector"],
            postgresql_using="gin",
        )


def downgrade() -> None:
    bind = op.get_bind()
    if "ix_knowledge_items_search_vector" in {
        item["name"] for item in sa.inspect(bind).get_indexes("knowledge_items")
    }:
        op.drop_index("ix_knowledge_items_search_vector", table_name="knowledge_items")
    if "uq_knowledge_items_slug" in {
        item["name"] for item in sa.inspect(bind).get_unique_constraints("knowledge_items")
    }:
        op.drop_constraint("uq_knowledge_items_slug", "knowledge_items", type_="unique")
    for table_name in ("token_usage", "plan_proposals"):
        if table_name in sa.inspect(bind).get_table_names():
            op.drop_table(table_name)
    for table_name, column_names in {
        "memories": [
            "source_conversation_id",
            "updated_at",
            "is_active",
            "is_sensitive",
            "category",
        ],
        "plans": ["change_summary"],
        "next_steps": ["due_text"],
        "conversations": ["channel", "ended_at"],
        "knowledge_items": ["search_vector", "verified_at", "kind", "slug"],
    }.items():
        existing = _columns(table_name)
        for column_name in column_names:
            if column_name in existing:
                op.drop_column(table_name, column_name)
