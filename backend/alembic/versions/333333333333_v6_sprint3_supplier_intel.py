"""v6_sprint3_supplier_intel

Revision ID: 333333333333
Revises: 222222222222
Create Date: 2026-08-09 14:48:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '333333333333'
down_revision = '222222222222'
branch_labels = None
depends_on = None

def upgrade() -> None:
    # 1. supplier_profiles
    op.create_table(
        'supplier_profiles',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('supplier_id', sa.Integer(), nullable=False),
        sa.Column('address', sa.String(), nullable=True),
        sa.Column('aggregated_score', sa.Float(), nullable=True),
        sa.Column('status_summary', sa.String(length=50), nullable=True),
        sa.ForeignKeyConstraint(['supplier_id'], ['suppliers.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('supplier_id')
    )
    op.create_index(op.f('ix_supplier_profiles_id'), 'supplier_profiles', ['id'], unique=False)
    op.create_index(op.f('ix_supplier_profiles_supplier_id'), 'supplier_profiles', ['supplier_id'], unique=False)

    # 2. validation_requests
    op.create_table(
        'validation_requests',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('supplier_id', sa.Integer(), nullable=False),
        sa.Column('source', sa.String(length=50), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='PENDING'),
        sa.Column('requested_by', sa.Integer(), nullable=True),
        sa.Column('requested_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('response_hash', sa.String(), nullable=True),
        sa.Column('response_payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('response_schema_version', sa.String(length=20), nullable=True),
        sa.Column('attempt_number', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('expiration_cache', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['requested_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['supplier_id'], ['suppliers.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_validation_requests_id'), 'validation_requests', ['id'], unique=False)
    op.create_index(op.f('ix_validation_requests_supplier_id'), 'validation_requests', ['supplier_id'], unique=False)

    # 3. ciiu_catalogs
    op.create_table(
        'ciiu_catalogs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(length=20), nullable=False),
        sa.Column('description', sa.String(), nullable=False),
        sa.Column('version', sa.String(length=20), nullable=False),
        sa.Column('source', sa.String(length=50), nullable=False, server_default='INEI'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code')
    )
    op.create_index(op.f('ix_ciiu_catalogs_code'), 'ciiu_catalogs', ['code'], unique=True)
    op.create_index(op.f('ix_ciiu_catalogs_id'), 'ciiu_catalogs', ['id'], unique=False)

def downgrade() -> None:
    op.drop_index(op.f('ix_ciiu_catalogs_id'), table_name='ciiu_catalogs')
    op.drop_index(op.f('ix_ciiu_catalogs_code'), table_name='ciiu_catalogs')
    op.drop_table('ciiu_catalogs')
    
    op.drop_index(op.f('ix_validation_requests_supplier_id'), table_name='validation_requests')
    op.drop_index(op.f('ix_validation_requests_id'), table_name='validation_requests')
    op.drop_table('validation_requests')
    
    op.drop_index(op.f('ix_supplier_profiles_supplier_id'), table_name='supplier_profiles')
    op.drop_index(op.f('ix_supplier_profiles_id'), table_name='supplier_profiles')
    op.drop_table('supplier_profiles')
