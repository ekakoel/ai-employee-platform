"""Add requester identity and fail-closed knowledge source policies.

The initial migration uses current ORM metadata on greenfield databases. This
revision therefore checks for pre-created columns/tables before adding them,
while still upgrading older deployed databases that predate these fields.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0006_knowledge_source_policies"
down_revision = "0005_company_onboarding"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "tasks" in tables:
        task_columns = {c["name"] for c in inspector.get_columns("tasks")}
        if "requested_by_user_id" not in task_columns:
            op.add_column("tasks", sa.Column("requested_by_user_id", sa.String(length=36), nullable=True))
        inspector = inspect(bind)
        task_indexes = {i["name"] for i in inspector.get_indexes("tasks")}
        if "ix_tasks_requested_by_user_id" not in task_indexes:
            op.create_index("ix_tasks_requested_by_user_id", "tasks", ["requested_by_user_id"])
        if bind.dialect.name != "sqlite":
            task_fks = inspector.get_foreign_keys("tasks")
            has_requester_fk = any(
                fk.get("constrained_columns") == ["requested_by_user_id"]
                and fk.get("referred_table") == "users"
                for fk in task_fks
            )
            if not has_requester_fk:
                op.create_foreign_key(
                    "fk_tasks_requested_by_user_id_users", "tasks", "users",
                    ["requested_by_user_id"], ["id"], ondelete="SET NULL",
                )

    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
    if "knowledge_source_policies" not in tables:
        op.create_table(
            "knowledge_source_policies",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("company_id", sa.String(length=36), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
            sa.Column("source_type", sa.String(length=20), nullable=False),
            sa.Column("source_id", sa.String(length=36), nullable=False),
            sa.Column("classification", sa.String(length=1), nullable=False, server_default="U"),
            sa.Column("is_approved", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("allowed_user_ids", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("allowed_role_ids", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("allowed_department_ids", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("allowed_purposes", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("policy_version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("source_version", sa.String(length=100), nullable=True),
            sa.Column("source_hash", sa.String(length=64), nullable=True),
            sa.Column("approval_ref", sa.String(length=200), nullable=True),
            sa.Column("owner_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("company_id", "source_type", "source_id", name="uq_knowledge_source_policy"),
            sa.CheckConstraint("classification IN ('A', 'B', 'C', 'D', 'U')", name="ck_knowledge_source_classification"),
            sa.CheckConstraint("source_type IN ('item', 'document')", name="ck_knowledge_source_type"),
        )

    inspector = inspect(bind)
    indexes = {i["name"] for i in inspector.get_indexes("knowledge_source_policies")}
    for name, columns in (
        ("ix_knowledge_source_policies_company_id", ["company_id"]),
        ("ix_knowledge_source_policy_company", ["company_id", "source_type", "is_active"]),
        ("ix_knowledge_source_policies_source_id", ["source_id"]),
    ):
        if name not in indexes:
            op.create_index(name, "knowledge_source_policies", columns)


def downgrade():
    raise RuntimeError("Forward-only security migration; do not remove requester or source policy history")
