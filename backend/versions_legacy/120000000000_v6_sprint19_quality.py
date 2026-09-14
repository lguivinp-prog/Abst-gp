"""v6_sprint19_quality

Revision ID: 120000000000
Revises: 110000000000
Create Date: 2026-08-09 21:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '120000000000'
down_revision = '110000000000'
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table(
        'document_quality_thresholds',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('min_dpi', sa.Integer(), server_default='150', nullable=False),
        sa.Column('max_rotation_degrees', sa.Float(), server_default='5.0', nullable=False),
        sa.Column('min_blur_score', sa.Float(), server_default='100.0', nullable=False),
        sa.Column('min_contrast_ratio', sa.Float(), server_default='4.5', nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table(
        'document_quality_assessments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('document_id', sa.Integer(), nullable=False),
        sa.Column('quality_status', sa.String(length=50), nullable=False),
        sa.Column('dpi_estimate', sa.Integer(), nullable=True),
        sa.Column('rotation_detected', sa.Boolean(), nullable=True),
        sa.Column('blur_score', sa.Float(), nullable=True),
        sa.Column('ocr_expected_quality', sa.String(length=20), nullable=True),
        sa.Column('issues', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('analyzer_version', sa.String(length=20), server_default='1.0', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_document_quality_assessments_document_id'), 'document_quality_assessments', ['document_id'], unique=False)
    op.create_index(op.f('ix_document_quality_assessments_id'), 'document_quality_assessments', ['id'], unique=False)

def downgrade() -> None:
    pass
