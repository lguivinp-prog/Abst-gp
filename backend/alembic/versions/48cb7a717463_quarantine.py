"""quarantine

Revision ID: 48cb7a717463
Revises: e0bb13aab365
Create Date: 2026-07-21 21:23:59.653672

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '48cb7a717463'
down_revision: Union[str, Sequence[str], None] = 'e0bb13aab365'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('user_tenant_quarantine',
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('reason_code', sa.String(), nullable=False),
    sa.Column('evidence_reviewed', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('status', sa.String(), nullable=False),
    sa.Column('proposed_tenant_id', sa.String(length=50), nullable=True),
    sa.Column('quarantined_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('resolution_reference', sa.String(), nullable=True),
    sa.ForeignKeyConstraint(['proposed_tenant_id'], ['tenants.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], onupdate='CASCADE', ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('user_id')
    )
    op.execute("ALTER TABLE users ALTER COLUMN is_active SET NOT NULL")
    op.execute("ALTER TABLE users ALTER COLUMN tenant_id DROP DEFAULT")
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS chk_users_tenant_id_not_null")
    op.add_column('users', sa.Column('tenant_resolution_status', sa.String(length=50), server_default='RESOLVED', nullable=False))

    op.add_column('users', sa.Column('quarantined_at', sa.DateTime(timezone=True), nullable=True))
    
    op.execute("""
        ALTER TABLE users ADD CONSTRAINT chk_users_tenant_resolution 
        CHECK (
            (tenant_resolution_status = 'RESOLVED' AND tenant_id IS NOT NULL) OR
            (tenant_resolution_status = 'QUARANTINED' AND tenant_id IS NULL AND is_active = false)
        ) NOT VALID
    """)

def downgrade() -> None:
    """Downgrade schema."""
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS chk_users_tenant_resolution")
    op.execute("ALTER TABLE users ADD CONSTRAINT chk_users_tenant_id_not_null CHECK (tenant_id IS NOT NULL) NOT VALID")
    op.drop_column('users', 'quarantined_at')
    op.drop_column('users', 'tenant_resolution_status')
    op.drop_table('user_tenant_quarantine')

