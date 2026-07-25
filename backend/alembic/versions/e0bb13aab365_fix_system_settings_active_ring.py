"""fix_system_settings_active_ring

Revision ID: e0bb13aab365
Revises: e03e62268655
Create Date: 2026-07-21 20:32:16.159317

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e0bb13aab365'
down_revision: Union[str, Sequence[str], None] = 'e03e62268655'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    context = op.get_context()
    if not context.as_sql:
        conn = op.get_bind()
        res = conn.execute(sa.text("SELECT id, active_ring FROM system_settings")).fetchall()
        if len(res) == 1:
            row = res[0]
            if row[0] != 1:
                raise Exception("system_settings contains a row with id != 1. Aborting migration.")
            if row[1] is None or row[1] < 0:
                raise Exception(f"system_settings contains invalid active_ring={row[1]}. Aborting migration.")
        elif len(res) > 1:
            raise Exception("system_settings contains multiple rows. Aborting migration.")


def downgrade() -> None:
    """Downgrade schema."""
    pass
