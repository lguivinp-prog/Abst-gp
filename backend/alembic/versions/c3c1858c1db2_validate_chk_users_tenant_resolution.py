"""validate_chk_users_tenant_resolution

Revision ID: c3c1858c1db2
Revises: 48cb7a717463
Create Date: 2026-07-21 22:09:52.872378

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3c1858c1db2'
down_revision: Union[str, Sequence[str], None] = '48cb7a717463'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("ALTER TABLE users VALIDATE CONSTRAINT chk_users_tenant_resolution")


def downgrade() -> None:
    """Downgrade schema."""
    pass # Cannot un-validate a constraint without dropping it, which we don't want to do
