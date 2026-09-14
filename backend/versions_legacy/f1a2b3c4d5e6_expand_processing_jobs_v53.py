"""expand_processing_jobs_v53

Revision ID: f1a2b3c4d5e6
Revises: e0bb13aab365
Create Date: 2026-08-03 20:20:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, Sequence[str], None] = '8527a001a1bc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema to support persistent ProcessingJob layer in PostgreSQL."""
    op.add_column('processing_jobs', sa.Column('job_id', sa.String(length=100), nullable=True))
    op.add_column('processing_jobs', sa.Column('case_id', sa.Integer(), nullable=True))
    op.add_column('processing_jobs', sa.Column('tenant_id', sa.String(length=50), server_default='mega_tenant', nullable=False))
    op.add_column('processing_jobs', sa.Column('user_id', sa.Integer(), nullable=True))
    op.add_column('processing_jobs', sa.Column('job_type', sa.String(length=50), server_default='REQUIREMENT_OCR', nullable=False))
    op.add_column('processing_jobs', sa.Column('progress', sa.Integer(), server_default='0', nullable=False))
    op.add_column('processing_jobs', sa.Column('status_message', sa.String(length=255), nullable=True))
    op.add_column('processing_jobs', sa.Column('idempotency_key', sa.String(length=128), nullable=True))
    op.add_column('processing_jobs', sa.Column('result_summary', sa.Text(), nullable=True))
    op.add_column('processing_jobs', sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True))

    op.create_index(op.f('ix_processing_jobs_job_id'), 'processing_jobs', ['job_id'], unique=True)
    op.create_index(op.f('ix_processing_jobs_case_id'), 'processing_jobs', ['case_id'], unique=False)
    op.create_index(op.f('ix_processing_jobs_tenant_id'), 'processing_jobs', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_processing_jobs_idempotency_key'), 'processing_jobs', ['idempotency_key'], unique=False)
    op.create_foreign_key('fk_processing_jobs_case_id', 'processing_jobs', 'case_files', ['case_id'], ['id'], ondelete='CASCADE')
    op.create_foreign_key('fk_processing_jobs_tenant_id', 'processing_jobs', 'tenants', ['tenant_id'], ['id'])
    op.create_foreign_key('fk_processing_jobs_user_id', 'processing_jobs', 'users', ['user_id'], ['id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('fk_processing_jobs_user_id', 'processing_jobs', type_='foreignkey')
    op.drop_constraint('fk_processing_jobs_tenant_id', 'processing_jobs', type_='foreignkey')
    op.drop_constraint('fk_processing_jobs_case_id', 'processing_jobs', type_='foreignkey')
    op.drop_index(op.f('ix_processing_jobs_idempotency_key'), table_name='processing_jobs')
    op.drop_index(op.f('ix_processing_jobs_tenant_id'), table_name='processing_jobs')
    op.drop_index(op.f('ix_processing_jobs_case_id'), table_name='processing_jobs')
    op.drop_index(op.f('ix_processing_jobs_job_id'), table_name='processing_jobs')
    op.drop_column('processing_jobs', 'updated_at')
    op.drop_column('processing_jobs', 'result_summary')
    op.drop_column('processing_jobs', 'idempotency_key')
    op.drop_column('processing_jobs', 'status_message')
    op.drop_column('processing_jobs', 'progress')
    op.drop_column('processing_jobs', 'job_type')
    op.drop_column('processing_jobs', 'user_id')
    op.drop_column('processing_jobs', 'tenant_id')
    op.drop_column('processing_jobs', 'case_id')
    op.drop_column('processing_jobs', 'job_id')
