"""add p13 technical evaluation report fields and constraints

Revision ID: f8a920bc1234
Revises: e7f891ab0123
Create Date: 2026-10-17 10:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f8a920bc1234'
down_revision: Union[str, Sequence[str], None] = 'e7f891ab0123'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Agregar columnas a generated_outputs sin alterar registros historicos
    op.add_column(
        'generated_outputs',
        sa.Column('report_kind', sa.String(length=50), server_default='CONDICIONES', nullable=False)
    )
    op.add_column(
        'generated_outputs',
        sa.Column('approved_by', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    )
    op.add_column(
        'generated_outputs',
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        'generated_outputs',
        sa.Column('approval_notes', sa.Text(), nullable=True)
    )
    op.add_column(
        'generated_outputs',
        sa.Column('rejected_by', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    )
    op.add_column(
        'generated_outputs',
        sa.Column('rejected_at', sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        'generated_outputs',
        sa.Column('rejection_reason', sa.Text(), nullable=True)
    )
    op.add_column(
        'generated_outputs',
        sa.Column('idempotency_key', sa.String(length=128), nullable=True)
    )
    op.add_column(
        'generated_outputs',
        sa.Column('request_hash', sa.String(length=64), nullable=True)
    )
    op.add_column(
        'generated_outputs',
        sa.Column('snapshot_hash', sa.String(length=64), nullable=True)
    )
    op.add_column(
        'generated_outputs',
        sa.Column('html_hash', sa.String(length=64), nullable=True)
    )
    op.add_column(
        'generated_outputs',
        sa.Column('pdf_hash', sa.String(length=64), nullable=True)
    )
    op.add_column(
        'generated_outputs',
        sa.Column('pdf_storage_path', sa.String(length=512), nullable=True)
    )

    # 2. Indice unico parcial de version para P13 (no renumera ni modifica filas legadas)
    op.create_index(
        'uq_generated_outputs_p13_version',
        'generated_outputs',
        ['case_id', 'report_kind', 'version_number'],
        unique=True,
        postgresql_where=sa.text("report_kind = 'INFORME_TECNICO_EVALUACION'")
    )

    # 3. Indice unico parcial de idempotencia para P13
    op.create_index(
        'uq_generated_outputs_p13_idempotency',
        'generated_outputs',
        ['case_id', 'report_kind', 'idempotency_key'],
        unique=True,
        postgresql_where=sa.text("report_kind = 'INFORME_TECNICO_EVALUACION' AND idempotency_key IS NOT NULL")
    )

    # 4. Indice unico parcial para plantillas P13 (respeta plantillas legadas que pudieran tener duplicados)
    op.create_index(
        'uq_output_templates_p13',
        'output_templates',
        ['type', 'entity_name', 'version'],
        unique=True,
        postgresql_where=sa.text("type = 'INFORME_TECNICO_EVALUACION'")
    )

    # 5. Agregar columna checksum a output_templates
    op.add_column(
        'output_templates',
        sa.Column('checksum', sa.String(length=64), nullable=True)
    )


def downgrade() -> None:
    # 0. Eliminar columna checksum de output_templates
    op.drop_column('output_templates', 'checksum')

    # 1. Eliminar indices unicos parciales
    op.drop_index('uq_output_templates_p13', table_name='output_templates')
    op.drop_index('uq_generated_outputs_p13_idempotency', table_name='generated_outputs')
    op.drop_index('uq_generated_outputs_p13_version', table_name='generated_outputs')

    # 2. Eliminar columnas agregadas a generated_outputs
    op.drop_column('generated_outputs', 'pdf_storage_path')
    op.drop_column('generated_outputs', 'pdf_hash')
    op.drop_column('generated_outputs', 'html_hash')
    op.drop_column('generated_outputs', 'snapshot_hash')
    op.drop_column('generated_outputs', 'request_hash')
    op.drop_column('generated_outputs', 'idempotency_key')
    op.drop_column('generated_outputs', 'rejection_reason')
    op.drop_column('generated_outputs', 'rejected_at')
    op.drop_column('generated_outputs', 'rejected_by')
    op.drop_column('generated_outputs', 'approval_notes')
    op.drop_column('generated_outputs', 'approved_at')
    op.drop_column('generated_outputs', 'approved_by')
    op.drop_column('generated_outputs', 'report_kind')
