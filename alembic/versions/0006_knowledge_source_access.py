"""Add requester attribution and explicit knowledge source grants.

Existing knowledge sources receive no grants and remain unavailable to RAG
until a trusted owner explicitly classifies and approves them.
"""
from alembic import op
import sqlalchemy as sa

revision = "0006_knowledge_source_access"
down_revision = "0005_company_onboarding"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    task_columns = {c["name"] for c in inspector.get_columns("tasks")}
    if "requested_by_user_id" not in task_columns:
        op.add_column(
            "tasks",
            sa.Column(
                "requested_by_user_id",
                sa.String(36),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
        )
        op.create_index(
            "ix_tasks_requested_by_user_id",
            "tasks",
            ["requested_by_user_id"],
        )

    if "knowledge_source_grants" not in inspector.get_table_names():
        op.create_table(
            "knowledge_source_grants",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("company_id", sa.String(36), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
            sa.Column("source_type", sa.String(20), nullable=False),
            sa.Column("source_id", sa.String(36), nullable=False),
            sa.Column("classification", sa.String(1), nullable=False, server_default="U"),
            sa.Column("owner_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_by_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("allowed_user_ids", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("allowed_role_ids", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("allowed_department_ids", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("allowed_purposes", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("is_approved", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("policy_version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("source_version", sa.String(100), nullable=True),
            sa.Column("source_hash", sa.String(64), nullable=True),
            sa.Column("approved_by_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint("source_type IN ('item', 'document')", name="ck_knowledge_grant_source_type"),
            sa.CheckConstraint("classification IN ('A', 'B', 'C', 'D', 'U')", name="ck_knowledge_grant_classification"),
            sa.UniqueConstraint("company_id", "source_type", "source_id", name="uq_knowledge_source_grant"),
        )
        op.create_index("ix_knowledge_source_grants_company", "knowledge_source_grants", ["company_id"])
        op.create_index("ix_knowledge_source_grants_source", "knowledge_source_grants", ["source_type", "source_id"])

    # Existing chunks have no trustworthy source classification or requester
    # ACL. They are derived data and can be rebuilt after each source is
    # explicitly approved; remove them before the new policy is enabled.
    if "knowledge_chunks" in inspector.get_table_names():
        op.execute("DELETE FROM knowledge_chunks")


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "knowledge_source_grants" in inspector.get_table_names():
        op.drop_index("ix_knowledge_source_grants_source", table_name="knowledge_source_grants")
        op.drop_index("ix_knowledge_source_grants_company", table_name="knowledge_source_grants")
        op.drop_table("knowledge_source_grants")
    task_columns = {c["name"] for c in inspector.get_columns("tasks")}
    if "requested_by_user_id" in task_columns:
        op.drop_index("ix_tasks_requested_by_user_id", table_name="tasks")
        op.drop_column("tasks", "requested_by_user_id")
