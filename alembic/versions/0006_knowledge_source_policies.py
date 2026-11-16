"""Add requester identity and fail-closed knowledge source policies."""

from alembic import op
import sqlalchemy as sa

revision = "0006_knowledge_source_policies"
down_revision = "0005_company_onboarding"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("tasks", sa.Column("requested_by_user_id", sa.String(length=36), nullable=True))
    op.create_index("ix_tasks_requested_by_user_id", "tasks", ["requested_by_user_id"])
    if op.get_bind().dialect.name != "sqlite":
        op.create_foreign_key(
            "fk_tasks_requested_by_user_id_users", "tasks", "users",
            ["requested_by_user_id"], ["id"], ondelete="SET NULL",
        )
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
    )
    op.create_index("ix_knowledge_source_policies_company_id", "knowledge_source_policies", ["company_id"])
    op.create_index("ix_knowledge_source_policy_company", "knowledge_source_policies", ["company_id", "source_type", "is_active"])
    op.create_index("ix_knowledge_source_policies_source_id", "knowledge_source_policies", ["source_id"])


def downgrade():
    op.drop_index("ix_knowledge_source_policies_source_id", table_name="knowledge_source_policies")
    op.drop_index("ix_knowledge_source_policy_company", table_name="knowledge_source_policies")
    op.drop_index("ix_knowledge_source_policies_company_id", table_name="knowledge_source_policies")
    op.drop_table("knowledge_source_policies")
    op.drop_index("ix_tasks_requested_by_user_id", table_name="tasks")
    op.drop_column("tasks", "requested_by_user_id")
