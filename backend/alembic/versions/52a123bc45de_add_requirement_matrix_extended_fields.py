"""add requirement matrix extended fields

Revision ID: 52a123bc45de
Revises: dcfc6c1bda38
Create Date: 2026-09-17 17:45:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '52a123bc45de'
down_revision = 'dcfc6c1bda38'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('case_requirement_matrices', sa.Column('category', sa.String(length=50), nullable=True))
    op.add_column('case_requirement_matrices', sa.Column('phase', sa.String(length=50), nullable=True))
    op.add_column('case_requirement_matrices', sa.Column('procurement_item_id', sa.Integer(), nullable=True))
    op.add_column('case_requirement_matrices', sa.Column('flows_to_contract', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('case_requirement_matrices', sa.Column('source_section', sa.String(length=255), nullable=True))
    
    op.create_index(op.f('ix_case_requirement_matrices_category'), 'case_requirement_matrices', ['category'], unique=False)
    op.create_index(op.f('ix_case_requirement_matrices_phase'), 'case_requirement_matrices', ['phase'], unique=False)
    op.create_index(op.f('ix_case_requirement_matrices_procurement_item_id'), 'case_requirement_matrices', ['procurement_item_id'], unique=False)
    op.create_foreign_key('fk_crm_procurement_item', 'case_requirement_matrices', 'case_procurement_items', ['procurement_item_id'], ['id'], ondelete='SET NULL')


def downgrade():
    op.drop_constraint('fk_crm_procurement_item', 'case_requirement_matrices', type_='foreignkey')
    op.drop_index(op.f('ix_case_requirement_matrices_procurement_item_id'), table_name='case_requirement_matrices')
    op.drop_index(op.f('ix_case_requirement_matrices_phase'), table_name='case_requirement_matrices')
    op.drop_index(op.f('ix_case_requirement_matrices_category'), table_name='case_requirement_matrices')
    
    op.drop_column('case_requirement_matrices', 'source_section')
    op.drop_column('case_requirement_matrices', 'flows_to_contract')
    op.drop_column('case_requirement_matrices', 'procurement_item_id')
    op.drop_column('case_requirement_matrices', 'phase')
    op.drop_column('case_requirement_matrices', 'category')
