"""Add company ownership, verification, and invitation records without moving legacy users."""

from alembic import op
import sqlalchemy as sa

revision = "0005_company_onboarding"
down_revision = "0004_auth_sessions"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    companies = {column["name"] for column in inspector.get_columns("companies")}
    users = {column["name"] for column in inspector.get_columns("users")}
    for name, column in (
        ("owner_user_id", sa.Column("owner_user_id", sa.String(36), nullable=True)),
        ("contact_email", sa.Column("contact_email", sa.String(320), nullable=True)),
        ("industry", sa.Column("industry", sa.String(120), nullable=True)),
        ("profile_completed_at", sa.Column("profile_completed_at", sa.DateTime(timezone=True), nullable=True)),
        ("onboarding_status", sa.Column("onboarding_status", sa.String(20), server_default="complete", nullable=False)),
    ):
        if name not in companies:
            op.add_column("companies", column)
    if bind.dialect.name != "sqlite" and "fk_company_owner_user" not in {
        fk.get("name") for fk in inspector.get_foreign_keys("companies")
    }:
        op.create_foreign_key("fk_company_owner_user", "companies", "users", ["owner_user_id"], ["id"])
    if "email_verified" not in users:
        op.add_column("users", sa.Column("email_verified", sa.Boolean(), server_default=sa.true(), nullable=False))

    tables = set(inspector.get_table_names())
    if "email_claims" not in tables:
        op.create_table("email_claims", sa.Column("email", sa.String(320), primary_key=True),
                        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    # A claim for every historical address prevents a new public account from
    # taking a legacy address; duplicate legacy identities remain unresolved.
    bind.execute(sa.text("INSERT INTO email_claims (email, created_at) "
                         "SELECT lower(trim(email)), CURRENT_TIMESTAMP FROM users "
                         "WHERE email IS NOT NULL AND trim(email) <> '' "
                         "AND lower(trim(email)) NOT IN (SELECT email FROM email_claims) "
                         "GROUP BY lower(trim(email))"))
    if "email_verifications" not in tables:
        op.create_table("email_verifications",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("token_digest", sa.String(64), unique=True, nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("consumed_at", sa.DateTime(timezone=True)))
        op.create_index("ix_email_verifications_user_id", "email_verifications", ["user_id"])
    if "company_invitations" not in tables:
        op.create_table("company_invitations",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("company_id", sa.String(36), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
            sa.Column("invited_by_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("email", sa.String(320), nullable=False),
            sa.Column("role_name", sa.String(100), nullable=False),
            sa.Column("token_digest", sa.String(64), unique=True, nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("consumed_at", sa.DateTime(timezone=True)),
            sa.Column("revoked_at", sa.DateTime(timezone=True)),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
        op.create_index("ix_company_invitations_company_id", "company_invitations", ["company_id"])
        op.create_index("ix_company_invite_email", "company_invitations", ["company_id", "email"])


def downgrade():
    raise RuntimeError("Forward-only identity migration; do not discard ownership or invitation history")
