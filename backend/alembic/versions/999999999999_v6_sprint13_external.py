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
    
    # 2. Update ciiu_catalogs
    op.add_column('ciiu_catalogs', sa.Column('codigo', sa.String(length=20), nullable=True))
    op.add_column('ciiu_catalogs', sa.Column('descripcion', sa.Text(), nullable=True))
    op.alter_column('ciiu_catalogs', 'version', type_=sa.String(length=50), existing_type=sa.String(length=20), nullable=True)
    op.add_column('ciiu_catalogs', sa.Column('fuente', sa.String(length=100), nullable=True))
    op.add_column('ciiu_catalogs', sa.Column('activo', sa.Boolean(), server_default='true', nullable=False))
    op.add_column('ciiu_catalogs', sa.Column('fecha_actualizacion', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
    
def downgrade() -> None:
    op.drop_column('experience_evaluations', 'similarity_score')
    
    op.drop_column('ciiu_catalogs', 'fecha_actualizacion')
    op.drop_column('ciiu_catalogs', 'activo')
    op.drop_column('ciiu_catalogs', 'fuente')
    op.alter_column('ciiu_catalogs', 'version', type_=sa.String(length=20), existing_type=sa.String(length=50), nullable=False)
    op.drop_column('ciiu_catalogs', 'descripcion')
    op.drop_column('ciiu_catalogs', 'codigo')
