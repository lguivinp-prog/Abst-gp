"""Add procurement and supplier items

Revision ID: 7a0f12d8a43c
Revises: 49fab9ca2c61
Create Date: 2026-09-15 20:15:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '7a0f12d8a43c'
down_revision = '49fab9ca2c61'
branch_labels = None
depends_on = None

def upgrade() -> None:
    # 1. Create case_procurement_items
    op.create_table('case_procurement_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('case_id', sa.Integer(), nullable=False),
        sa.Column('item_number', sa.String(), nullable=True),
        sa.Column('description', sa.String(), nullable=False),
        sa.Column('quantity', sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column('unit', sa.String(), nullable=False),
        sa.Column('source_document_id', sa.Integer(), nullable=True),
        sa.Column('source_page', sa.Integer(), nullable=True),
        sa.Column('source_requirement_id', sa.Integer(), nullable=True),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['case_id'], ['case_files.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['source_document_id'], ['uploaded_documents.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['source_requirement_id'], ['case_requirement_matrices.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('case_id', 'item_number', name='uq_case_item_number')
    )
    op.create_index(op.f('ix_case_procurement_items_case_id'), 'case_procurement_items', ['case_id'], unique=False)
    op.create_index(op.f('ix_case_procurement_items_id'), 'case_procurement_items', ['id'], unique=False)

    # 2. Create supplier_offer_items
    op.create_table('supplier_offer_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('supplier_offer_id', sa.Integer(), nullable=False),
        sa.Column('procurement_item_id', sa.Integer(), nullable=False),
        sa.Column('description', sa.String(), nullable=True),
        sa.Column('quantity', sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column('unit', sa.String(), nullable=False),
        sa.Column('unit_price', sa.Numeric(precision=18, scale=2), nullable=False),
        sa.ForeignKeyConstraint(['procurement_item_id'], ['case_procurement_items.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['supplier_offer_id'], ['supplier_offers.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('supplier_offer_id', 'procurement_item_id', name='uq_offer_procurement_item')
    )
    op.create_index(op.f('ix_supplier_offer_items_id'), 'supplier_offer_items', ['id'], unique=False)
    op.create_index(op.f('ix_supplier_offer_items_procurement_item_id'), 'supplier_offer_items', ['procurement_item_id'], unique=False)
    op.create_index(op.f('ix_supplier_offer_items_supplier_offer_id'), 'supplier_offer_items', ['supplier_offer_id'], unique=False)

def downgrade() -> None:
    op.drop_index(op.f('ix_supplier_offer_items_supplier_offer_id'), table_name='supplier_offer_items')
    op.drop_index(op.f('ix_supplier_offer_items_procurement_item_id'), table_name='supplier_offer_items')
    op.drop_index(op.f('ix_supplier_offer_items_id'), table_name='supplier_offer_items')
    op.drop_table('supplier_offer_items')
    op.drop_index(op.f('ix_case_procurement_items_id'), table_name='case_procurement_items')
    op.drop_index(op.f('ix_case_procurement_items_case_id'), table_name='case_procurement_items')
    op.drop_table('case_procurement_items')
