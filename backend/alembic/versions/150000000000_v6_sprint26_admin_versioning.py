"""v6_sprint26_admin_versioning

Revision ID: 150000000000
Revises: 140000000000
Create Date: 2026-08-09 23:45:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '150000000000'
down_revision = '140000000000'
branch_labels = None
depends_on = None

def upgrade() -> None:
    # 1. Add versioning to TenantConfiguration
    op.add_column('tenant_configurations', sa.Column('configuration_version', sa.Integer(), server_default='1', nullable=False))

    # 2. Create TenantConfigurationHistory table
    op.create_table('tenant_configuration_history',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.String(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('field_changed', sa.String(), nullable=False),
        sa.Column('old_value', sa.String(), nullable=True),
        sa.Column('new_value', sa.String(), nullable=True),
        sa.Column('changed_by_user_id', sa.Integer(), nullable=False),
        sa.Column('reason', sa.String(), nullable=True),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_tenant_configuration_history_id'), 'tenant_configuration_history', ['id'], unique=False)
    op.create_index(op.f('ix_tenant_configuration_history_tenant_id'), 'tenant_configuration_history', ['tenant_id'], unique=False)

def downgrade() -> None:
    pass
