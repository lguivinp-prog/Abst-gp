"""v6_sprint2_extraction

Revision ID: 222222222222
Revises: 1ecccaae7267
Create Date: 2026-08-09 14:43:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '222222222222'
down_revision = '1ecccaae7267'
branch_labels = None
depends_on = None

def upgrade() -> None:
    # Add status to case_requirement_matrices
    op.add_column('case_requirement_matrices', sa.Column('status', sa.String(length=50), server_default='PENDING_REVIEW', nullable=False))
    
    # Drop legacy columns from Sprint 1 matrix design
    op.drop_column('case_requirement_matrices', 'source_document')
    op.drop_column('case_requirement_matrices', 'source_page')
    op.drop_column('case_requirement_matrices', 'confidence')

    # Create requirement_evidences table
    op.create_table(
        'requirement_evidences',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('requirement_id', sa.Integer(), nullable=False),
        sa.Column('source_document', sa.String(), nullable=False),
        sa.Column('source_page', sa.Integer(), nullable=True),
        sa.Column('source_fragment', sa.Text(), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['requirement_id'], ['case_requirement_matrices.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_requirement_evidences_id'), 'requirement_evidences', ['id'], unique=False)
    op.create_index(op.f('ix_requirement_evidences_requirement_id'), 'requirement_evidences', ['requirement_id'], unique=False)

def downgrade() -> None:
    op.drop_index(op.f('ix_requirement_evidences_requirement_id'), table_name='requirement_evidences')
    op.drop_index(op.f('ix_requirement_evidences_id'), table_name='requirement_evidences')
    op.drop_table('requirement_evidences')
    
    op.add_column('case_requirement_matrices', sa.Column('confidence', postgresql.DOUBLE_PRECISION(precision=53), autoincrement=False, nullable=True))
    op.add_column('case_requirement_matrices', sa.Column('source_page', sa.INTEGER(), autoincrement=False, nullable=True))
    op.add_column('case_requirement_matrices', sa.Column('source_document', sa.VARCHAR(), autoincrement=False, nullable=True))
    
    op.drop_column('case_requirement_matrices', 'status')
