"""v6_sprint14_experience

Revision ID: 100000000000
Revises: 999999999999
Create Date: 2026-08-09 20:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '100000000000'
down_revision = '999999999999'
branch_labels = None
depends_on = None

def upgrade() -> None:
    # experience_requirements table
    op.create_table(
        'experience_requirements',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('case_id', sa.Integer(), nullable=False),
        sa.Column('monto_requerido', sa.Float(), nullable=True),
        sa.Column('periodo_anios', sa.Integer(), nullable=True),
        sa.Column('objeto_similar', sa.String(), nullable=True),
        sa.Column('cantidad_minima', sa.Integer(), nullable=True),
        sa.Column('condicion', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(['case_id'], ['case_files.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_experience_requirements_case_id'), 'experience_requirements', ['case_id'], unique=False)
    op.create_index(op.f('ix_experience_requirements_id'), 'experience_requirements', ['id'], unique=False)

    # calculation_traces table
    op.create_table(
        'calculation_traces',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('supplier_offer_id', sa.Integer(), nullable=False),
        sa.Column('evidencias_usadas', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('montos', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('fechas', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('resultado_calculo', sa.String(length=255), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['supplier_offer_id'], ['supplier_offers.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_calculation_traces_id'), 'calculation_traces', ['id'], unique=False)
    op.create_index(op.f('ix_calculation_traces_supplier_offer_id'), 'calculation_traces', ['supplier_offer_id'], unique=False)

    # update experience_evidences
    op.add_column('experience_evidences', sa.Column('evidence_status', sa.String(length=50), server_default='EXTRACTED', nullable=False))
    op.add_column('experience_evidences', sa.Column('entidad_contratante', sa.String(length=255), nullable=True))
    op.add_column('experience_evidences', sa.Column('objeto', sa.Text(), nullable=True))
    op.add_column('experience_evidences', sa.Column('monto', sa.Float(), nullable=True))
    op.add_column('experience_evidences', sa.Column('fecha', sa.DateTime(timezone=True), nullable=True))

    # update supplier_profiles
    op.add_column('supplier_profiles', sa.Column('validation_status', sa.String(length=50), server_default='NOT_STARTED', nullable=False))

def downgrade() -> None:
    pass
