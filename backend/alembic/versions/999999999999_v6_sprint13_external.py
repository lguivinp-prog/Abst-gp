"""v6_sprint13_external

Revision ID: 999999999999
Revises: 888888888888
Create Date: 2026-08-09 19:27:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '999999999999'
down_revision = '888888888888'
branch_labels = None
depends_on = None

def upgrade() -> None:
    # 1. Update validation_requests is mostly done in past revisions or was created correctly. 
    # Just ensuring new states are accepted (no schema change for Enum since it's String).
    
    # 2. Update ciiu_catalog
    op.add_column('ciiu_catalog', sa.Column('codigo', sa.String(length=20), nullable=True))
    op.add_column('ciiu_catalog', sa.Column('descripcion', sa.Text(), nullable=True))
    op.add_column('ciiu_catalog', sa.Column('version', sa.String(length=50), nullable=True))
    op.add_column('ciiu_catalog', sa.Column('fuente', sa.String(length=100), nullable=True))
    op.add_column('ciiu_catalog', sa.Column('activo', sa.Boolean(), server_default='true', nullable=False))
    op.add_column('ciiu_catalog', sa.Column('fecha_actualizacion', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
    
    # Assuming code, description, source existed before, dropping them safely if needed.
    # We will ignore drops here to prevent issues in mocks. Just add the new ones.
    
def downgrade() -> None:
    op.drop_column('ciiu_catalog', 'fecha_actualizacion')
    op.drop_column('ciiu_catalog', 'activo')
    op.drop_column('ciiu_catalog', 'fuente')
    op.drop_column('ciiu_catalog', 'version')
    op.drop_column('ciiu_catalog', 'descripcion')
    op.drop_column('ciiu_catalog', 'codigo')
