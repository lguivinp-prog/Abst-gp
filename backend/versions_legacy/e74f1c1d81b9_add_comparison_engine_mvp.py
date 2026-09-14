"""add comparison engine mvp

Revision ID: e74f1c1d81b9
Revises: 3356ea46065f
Create Date: 2026-07-17 12:56:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'e74f1c1d81b9'
down_revision = '3356ea46065f'
branch_labels = None
depends_on = None

def upgrade():
    # 1. Definir los Enums
    comparison_run_status_enum = postgresql.ENUM('CREATED', 'PROCESSING', 'COMPLETED', 'FAILED', name='comparison_run_status_enum', create_type=False)
    comparison_run_status_enum.create(op.get_bind())

    requirement_item_type_enum = postgresql.ENUM('TECHNICAL', 'COMMERCIAL', 'LEGAL', 'DELIVERY', 'WARRANTY', name='requirement_item_type_enum', create_type=False)
    requirement_item_type_enum.create(op.get_bind())

    comparison_result_status_enum = postgresql.ENUM('PASS', 'FAIL', 'MANUAL_REVIEW', name='comparison_result_status_enum', create_type=False)
    comparison_result_status_enum.create(op.get_bind())

    comparison_evaluation_method_enum = postgresql.ENUM('EXACT_MATCH', 'NUMERIC_MATCH', 'FUZZY_MATCH', 'MANUAL_REVIEW', name='comparison_evaluation_method_enum', create_type=False)
    comparison_evaluation_method_enum.create(op.get_bind())

    # 2. Crear tabla comparison_runs
    op.create_table(
        'comparison_runs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('case_id', sa.Integer(), sa.ForeignKey('case_files.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('requirement_doc_id', sa.Integer(), sa.ForeignKey('uploaded_documents.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('quotation_doc_id', sa.Integer(), sa.ForeignKey('uploaded_documents.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('status', comparison_run_status_enum, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False)
    )

    # 3. Crear tabla requirement_items
    op.create_table(
        'requirement_items',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('parsed_section_id', sa.Integer(), sa.ForeignKey('parsed_sections.id', ondelete='CASCADE'), nullable=False),
        sa.Column('item_type', requirement_item_type_enum, nullable=False),
        sa.Column('content_text', sa.String(), nullable=False),
        sa.Column('is_approved', sa.Boolean(), default=False, nullable=False)
    )

    # 4. Crear tabla comparison_results
    op.create_table(
        'comparison_results',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('run_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('comparison_runs.id', ondelete='CASCADE'), nullable=False),
        sa.Column('requirement_item_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('requirement_items.id', ondelete='CASCADE'), nullable=False),
        sa.Column('quotation_section_id', sa.Integer(), sa.ForeignKey('parsed_sections.id', ondelete='SET NULL'), nullable=True),
        sa.Column('status', comparison_result_status_enum, nullable=False),
        sa.Column('evaluation_method', comparison_evaluation_method_enum, nullable=False),
        sa.Column('confidence_score', sa.Float(), nullable=False),
        sa.Column('reasoning', sa.String(), nullable=True),
        sa.Column('evidence_text', sa.String(), nullable=True),
        sa.Column('requirement_page', sa.Integer(), nullable=True),
        sa.Column('quotation_page', sa.Integer(), nullable=True)
    )

    # 5. Índices
    op.create_index('ix_comparison_runs_case_id', 'comparison_runs', ['case_id'])
    op.create_index('ix_comparison_results_run_id', 'comparison_results', ['run_id'])
    op.create_index('ix_comparison_results_requirement_item_id', 'comparison_results', ['requirement_item_id'])
    op.create_index('ix_comparison_results_status', 'comparison_results', ['status'])

def downgrade():
    # 1. Eliminar índices
    op.drop_index('ix_comparison_results_status', table_name='comparison_results')
    op.drop_index('ix_comparison_results_requirement_item_id', table_name='comparison_results')
    op.drop_index('ix_comparison_results_run_id', table_name='comparison_results')
    op.drop_index('ix_comparison_runs_case_id', table_name='comparison_runs')

    # 2. Eliminar tablas
    op.drop_table('comparison_results')
    op.drop_table('requirement_items')
    op.drop_table('comparison_runs')

    # 3. Eliminar los ENUM Types
    postgresql.ENUM(name='comparison_evaluation_method_enum').drop(op.get_bind())
    postgresql.ENUM(name='comparison_result_status_enum').drop(op.get_bind())
    postgresql.ENUM(name='requirement_item_type_enum').drop(op.get_bind())
    postgresql.ENUM(name='comparison_run_status_enum').drop(op.get_bind())
