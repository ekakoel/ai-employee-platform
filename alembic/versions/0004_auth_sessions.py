"""Add durable authentication sessions and single-use credential records."""

from alembic import op
import sqlalchemy as sa

revision = "0004_auth_sessions"
down_revision = "0003_task_result_pins"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "auth_version" not in {column["name"] for column in inspector.get_columns("users")}:
        op.add_column("users", sa.Column("auth_version", sa.Integer(), server_default="0", nullable=False))
    # Earlier baseline migrations use live metadata. Check existing tables so
    # a fresh install and an upgrade of the historical schema both work.
    tables = set(inspector.get_table_names())
    if "auth_sessions" not in tables:
        op.create_table("auth_sessions",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("company_id", sa.String(36), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
            sa.Column("auth_version", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("absolute_expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("revoked_at", sa.DateTime(timezone=True)),
            sa.Column("revoke_reason", sa.String(40)),
            sa.CheckConstraint("auth_version >= 0", name="ck_session_auth_version"))
        op.create_index("ix_auth_session_owner", "auth_sessions", ["user_id", "company_id", "revoked_at"])
        op.create_index("ix_auth_session_expiry", "auth_sessions", ["absolute_expires_at"])
    if "refresh_token_records" not in tables:
        op.create_table("refresh_token_records",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("session_id", sa.String(36), sa.ForeignKey("auth_sessions.id", ondelete="CASCADE"), nullable=False),
            sa.Column("token_digest", sa.String(64), nullable=False, unique=True),
            sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("consumed_at", sa.DateTime(timezone=True)),
            sa.Column("replaced_by", sa.String(36), sa.ForeignKey("refresh_token_records.id")))
        op.create_index("ix_refresh_session", "refresh_token_records", ["session_id"])
        op.create_index("ix_refresh_expiry", "refresh_token_records", ["expires_at"])
    if "password_reset_records" not in tables:
        op.create_table("password_reset_records",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("company_id", sa.String(36), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
            sa.Column("auth_version", sa.Integer(), nullable=False),
            sa.Column("token_digest", sa.String(64), nullable=False, unique=True),
            sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("consumed_at", sa.DateTime(timezone=True)))
        op.create_index("ix_reset_owner", "password_reset_records", ["user_id", "expires_at"])


def downgrade():
    raise RuntimeError("Security cutover is forward-only. Do not drop revocation records or restore stateless authentication.")
