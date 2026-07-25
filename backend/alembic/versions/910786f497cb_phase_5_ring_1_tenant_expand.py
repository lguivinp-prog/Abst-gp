"""phase_5_ring_1_tenant_expand

Revision ID: 910786f497cb
Revises: 531ab381efea
Create Date: 2026-07-20 21:12:00.922084

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '910786f497cb'
down_revision: Union[str, Sequence[str], None] = '531ab381efea'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 1. Expand: Create tenants table
    op.create_table('tenants',
    sa.Column('id', sa.String(length=50), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )

    # 2. Insert canonical Mega Tenant
    op.execute("INSERT INTO tenants (id, name) VALUES ('mega_tenant', 'Mega Tenant') ON CONFLICT DO NOTHING")

    # 3. Add columns (nullable, without default initially)
    op.add_column('audit_logs', sa.Column('tenant_id', sa.String(length=50), nullable=True))
    op.add_column('case_files', sa.Column('tenant_id', sa.String(length=50), nullable=True))
    op.add_column('users', sa.Column('tenant_id', sa.String(length=50), nullable=True))

    # 4. Set temporary server_default to 'mega_tenant' for legacy compatibility during rollout
    op.alter_column('audit_logs', 'tenant_id', server_default='mega_tenant')
    op.alter_column('case_files', 'tenant_id', server_default='mega_tenant')
    op.alter_column('users', 'tenant_id', server_default='mega_tenant')

    # 5. SystemSettings - active_ring
    op.add_column('system_settings', sa.Column('active_ring', sa.Integer(), server_default='0', nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('users', 'tenant_id')
    op.drop_column('system_settings', 'active_ring')
    op.drop_column('case_files', 'tenant_id')
    op.drop_column('audit_logs', 'tenant_id')
    op.drop_table('tenants')
