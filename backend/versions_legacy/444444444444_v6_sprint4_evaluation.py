"""v6_sprint4_evaluation

Revision ID: 444444444444
Revises: 333333333333
Create Date: 2026-08-09 14:58:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '444444444444'
down_revision = '333333333333'
branch_labels = None
depends_on = None

def upgrade() -> None:
    # 1. Add evaluation_status to supplier_offers
    op.add_column('supplier_offers', sa.Column('evaluation_status', sa.String(length=50), server_default='PENDING', nullable=False))

    # 2. Create offer_evidences
    op.create_table(
        'offer_evidences',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('supplier_offer_id', sa.Integer(), nullable=False),
        sa.Column('document_id', sa.Integer(), nullable=True),
        sa.Column('document_type', sa.String(length=50), nullable=False),
        sa.Column('page', sa.Integer(), nullable=True),
        sa.Column('fragment', sa.Text(), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['supplier_offer_id'], ['supplier_offers.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_offer_evidences_id'), 'offer_evidences', ['id'], unique=False)
    op.create_index(op.f('ix_offer_evidences_supplier_offer_id'), 'offer_evidences', ['supplier_offer_id'], unique=False)

    # 3. Create offer_evaluations
    op.create_table(
        'offer_evaluations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('supplier_offer_id', sa.Integer(), nullable=False),
        sa.Column('requirement_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='PENDING'),
        sa.Column('explanation', sa.Text(), nullable=True),
        sa.Column('evaluation_confidence', sa.Float(), nullable=True),
        sa.Column('validated_by', sa.Integer(), nullable=True),
        sa.Column('validated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['requirement_id'], ['case_requirement_matrices.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['supplier_offer_id'], ['supplier_offers.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['validated_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_offer_evaluations_id'), 'offer_evaluations', ['id'], unique=False)
    op.create_index(op.f('ix_offer_evaluations_requirement_id'), 'offer_evaluations', ['requirement_id'], unique=False)
    op.create_index(op.f('ix_offer_evaluations_supplier_offer_id'), 'offer_evaluations', ['supplier_offer_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_offer_evaluations_supplier_offer_id'), table_name='offer_evaluations')
    op.drop_index(op.f('ix_offer_evaluations_requirement_id'), table_name='offer_evaluations')
    op.drop_index(op.f('ix_offer_evaluations_id'), table_name='offer_evaluations')
    op.drop_table('offer_evaluations')
    
    op.drop_index(op.f('ix_offer_evidences_supplier_offer_id'), table_name='offer_evidences')
    op.drop_index(op.f('ix_offer_evidences_id'), table_name='offer_evidences')
    op.drop_table('offer_evidences')
    
    op.drop_column('supplier_offers', 'evaluation_status')
