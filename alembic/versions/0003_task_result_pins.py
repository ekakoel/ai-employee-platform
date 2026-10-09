"""Personal AI result bookmarks."""

from alembic import op
from app.models.entities import TaskResultPin

revision = "0003_task_result_pins"
down_revision = "0002_schema_sync"
branch_labels = None
depends_on = None


def upgrade():
    TaskResultPin.__table__.create(op.get_bind(), checkfirst=True)


def downgrade():
    TaskResultPin.__table__.drop(op.get_bind(), checkfirst=True)
