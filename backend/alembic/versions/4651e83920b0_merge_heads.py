"""merge heads

Revision ID: 4651e83920b0
Revises: 150000000000, c4d5e6f7a8b9
Create Date: 2026-08-10 17:41:30.645556

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4651e83920b0'
down_revision: Union[str, Sequence[str], None] = ('150000000000', 'c4d5e6f7a8b9')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
