"""v6_sprint5_selection

Revision ID: 555555555555
Revises: 444444444444
Create Date: 2026-08-09 15:10:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '555555555555'
down_revision = '444444444444'
branch_labels = None
depends_on = None

def upgrade() -> None:
    # 1. case_workflows
    op.create_table(
        'case_workflows',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('case_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=50), server_default='DRAFT', nullable=False),
        sa.Column('supervisor_id', sa.Integer(), nullable=True),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['case_id'], ['case_files.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['supervisor_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('case_id')
    )
    op.create_index(op.f('ix_case_workflows_case_id'), 'case_workflows', ['case_id'], unique=False)
    op.create_index(op.f('ix_case_workflows_id'), 'case_workflows', ['id'], unique=False)

    # 2. experience_evidences
    op.create_table(
        'experience_evidences',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('supplier_offer_id', sa.Integer(), nullable=False),
        sa.Column('document_id', sa.Integer(), nullable=True),
        sa.Column('document_type', sa.String(length=50), nullable=False),
        sa.Column('page', sa.Integer(), nullable=True),
        sa.Column('raw_fragment', sa.Text(), nullable=False),
        sa.Column('normalized_fragment', sa.Text(), nullable=True),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('validated_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['supplier_offer_id'], ['supplier_offers.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['validated_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_experience_evidences_id'), 'experience_evidences', ['id'], unique=False)
    op.create_index(op.f('ix_experience_evidences_supplier_offer_id'), 'experience_evidences', ['supplier_offer_id'], unique=False)

    # 3. experience_evaluations
    op.create_table(
        'experience_evaluations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('supplier_offer_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=50), server_default='PENDING', nullable=False),
        sa.Column('explanation', sa.Text(), nullable=True),
        sa.Column('validated_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['supplier_offer_id'], ['supplier_offers.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['validated_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_experience_evaluations_id'), 'experience_evaluations', ['id'], unique=False)
    op.create_index(op.f('ix_experience_evaluations_supplier_offer_id'), 'experience_evaluations', ['supplier_offer_id'], unique=False)

    # 4. supplier_selection_attempts
    op.create_table(
        'supplier_selection_attempts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('case_id', sa.Integer(), nullable=False),
        sa.Column('supplier_offer_id', sa.Integer(), nullable=False),
        sa.Column('justification_reason', sa.String(length=255), nullable=True),
        sa.Column('justification_comment', sa.Text(), nullable=True),
        sa.Column('justification_evidence_id', sa.Integer(), nullable=True),
        sa.Column('selected_by', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=50), server_default='PROPOSED', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['case_id'], ['case_files.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['selected_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['supplier_offer_id'], ['supplier_offers.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_supplier_selection_attempts_case_id'), 'supplier_selection_attempts', ['case_id'], unique=False)
    op.create_index(op.f('ix_supplier_selection_attempts_id'), 'supplier_selection_attempts', ['id'], unique=False)

    # 5. supplier_selection_final
    op.create_table(
        'supplier_selection_final',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('case_id', sa.Integer(), nullable=False),
        sa.Column('attempt_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['attempt_id'], ['supplier_selection_attempts.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['case_id'], ['case_files.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('case_id')
    )
    op.create_index(op.f('ix_supplier_selection_final_case_id'), 'supplier_selection_final', ['case_id'], unique=False)
    op.create_index(op.f('ix_supplier_selection_final_id'), 'supplier_selection_final', ['id'], unique=False)


def downgrade() -> None:
    op.drop_table('supplier_selection_final')
    op.drop_table('supplier_selection_attempts')
    op.drop_table('experience_evaluations')
    op.drop_table('experience_evidences')
    op.drop_table('case_workflows')
