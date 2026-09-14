"""relax_admin_tenant_constraint

Revision ID: 6ae6760eedcc
Revises: 0001
Create Date: 2026-08-14 04:58:34.534714

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6ae6760eedcc'
down_revision: Union[str, Sequence[str], None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_constraint('chk_users_tenant_resolution', 'users', type_='check')
    op.create_check_constraint(
        'chk_users_tenant_resolution',
        'users',
        'tenant_id IS NOT NULL'
    )

def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('chk_users_tenant_resolution', 'users', type_='check')
    op.create_check_constraint(
        'chk_users_tenant_resolution',
        'users',
        "(role = 'ADMIN' AND tenant_id IS NULL AND tenant_resolution_status = 'RESOLVED') OR (role != 'ADMIN' AND tenant_id IS NOT NULL)"
    )
