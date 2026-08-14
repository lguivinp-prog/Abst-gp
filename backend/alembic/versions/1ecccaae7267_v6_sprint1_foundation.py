"""v6_sprint1_foundation

Revision ID: 1ecccaae7267
Revises: f1a2b3c4d5e6
Create Date: 2026-08-09 14:26:11.123456

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '1ecccaae7267'
down_revision = 'f1a2b3c4d5e6'
branch_labels = None
depends_on = None

def upgrade() -> None:
    # 1. suppliers
    op.create_table(
        'suppliers',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.String(length=50), server_default='mega_tenant', nullable=False),
        sa.Column('ruc', sa.String(length=20), nullable=False),
        sa.Column('business_name', sa.String(), nullable=False),
        sa.Column('legal_representative', sa.String(), nullable=True),
        sa.Column('dni', sa.String(length=20), nullable=True),
        sa.Column('contact_email', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], onupdate='RESTRICT', ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_suppliers_id'), 'suppliers', ['id'], unique=False)
    op.create_index(op.f('ix_suppliers_tenant_id'), 'suppliers', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_suppliers_ruc'), 'suppliers', ['ruc'], unique=False)

    # 2. case_requirement_matrices
    op.create_table(
        'case_requirement_matrices',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('case_id', sa.Integer(), nullable=False),
        sa.Column('requirement_type', sa.String(length=50), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('value', sa.String(), nullable=True),
        sa.Column('mandatory', sa.Boolean(), nullable=False, default=True),
        sa.Column('source_document', sa.String(), nullable=True),
        sa.Column('source_page', sa.Integer(), nullable=True),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('validated_by', sa.Integer(), nullable=True),
        sa.Column('validated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['case_id'], ['case_files.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['validated_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_case_requirement_matrices_case_id'), 'case_requirement_matrices', ['case_id'], unique=False)
    op.create_index(op.f('ix_case_requirement_matrices_id'), 'case_requirement_matrices', ['id'], unique=False)

    # 3. supplier_offers
    op.create_table(
        'supplier_offers',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('case_id', sa.Integer(), nullable=False),
        sa.Column('supplier_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False, default='PENDING'),
        sa.Column('price', sa.Float(), nullable=True),
        sa.Column('source_document', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['case_id'], ['case_files.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['supplier_id'], ['suppliers.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_supplier_offers_case_id'), 'supplier_offers', ['case_id'], unique=False)
    op.create_index(op.f('ix_supplier_offers_id'), 'supplier_offers', ['id'], unique=False)
    op.create_index(op.f('ix_supplier_offers_supplier_id'), 'supplier_offers', ['supplier_id'], unique=False)

def downgrade() -> None:
    op.drop_index(op.f('ix_supplier_offers_supplier_id'), table_name='supplier_offers')
    op.drop_index(op.f('ix_supplier_offers_id'), table_name='supplier_offers')
    op.drop_index(op.f('ix_supplier_offers_case_id'), table_name='supplier_offers')
    op.drop_table('supplier_offers')
    
    op.drop_index(op.f('ix_case_requirement_matrices_id'), table_name='case_requirement_matrices')
    op.drop_index(op.f('ix_case_requirement_matrices_case_id'), table_name='case_requirement_matrices')
    op.drop_table('case_requirement_matrices')
    
    op.drop_index(op.f('ix_suppliers_ruc'), table_name='suppliers')
    op.drop_index(op.f('ix_suppliers_tenant_id'), table_name='suppliers')
    op.drop_index(op.f('ix_suppliers_id'), table_name='suppliers')
    op.drop_table('suppliers')
