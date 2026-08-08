"""v5_4_observability_and_heartbeat

Revision ID: b2c3d4e5f6a7
Revises: f1a2b3c4d5e6
Create Date: 2026-08-03 21:55:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, Sequence[str], None] = 'f1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema for V5.4 Observability, ProcessingMetrics and WorkerHeartbeat."""
    # 1. Extender processing_jobs con columnas de resiliencia
    op.add_column('processing_jobs', sa.Column('attempt_count', sa.Integer(), server_default='1', nullable=False))
    op.add_column('processing_jobs', sa.Column('max_retries', sa.Integer(), server_default='3', nullable=False))
    op.add_column('processing_jobs', sa.Column('failure_classification', sa.String(length=50), nullable=True))
    op.add_column('processing_jobs', sa.Column('last_heartbeat_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('processing_jobs', sa.Column('worker_name', sa.String(length=100), nullable=True))

    # 2. Crear tabla worker_heartbeats
    op.create_table(
        'worker_heartbeats',
        sa.Column('worker_name', sa.String(length=100), primary_key=True, nullable=False),
        sa.Column('worker_type', sa.String(length=50), nullable=False),
        sa.Column('hostname', sa.String(length=100), server_default='localhost', nullable=False),
        sa.Column('status', sa.String(length=30), server_default='IDLE', nullable=False),
        sa.Column('current_job_id', sa.String(length=100), nullable=True),
        sa.Column('tenant_id', sa.String(length=50), nullable=True),
        sa.Column('last_seen', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name='fk_worker_heartbeats_tenant_id', onupdate='RESTRICT', ondelete='RESTRICT')
    )
    op.create_index(op.f('ix_worker_heartbeats_worker_type'), 'worker_heartbeats', ['worker_type'], unique=False)
    op.create_index(op.f('ix_worker_heartbeats_last_seen'), 'worker_heartbeats', ['last_seen'], unique=False)

    # 3. Crear tabla processing_metrics
    op.create_table(
        'processing_metrics',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column('job_id', sa.String(length=100), nullable=False),
        sa.Column('tenant_id', sa.String(length=50), server_default='mega_tenant', nullable=False),
        sa.Column('case_id', sa.Integer(), nullable=True),
        sa.Column('job_type', sa.String(length=50), nullable=False),
        sa.Column('queue_time_ms', sa.Integer(), server_default='0', nullable=False),
        sa.Column('processing_time_ms', sa.Integer(), server_default='0', nullable=False),
        sa.Column('total_time_ms', sa.Integer(), server_default='0', nullable=False),
        sa.Column('worker_name', sa.String(length=100), server_default='unassigned', nullable=False),
        sa.Column('pages_processed', sa.Integer(), server_default='0', nullable=False),
        sa.Column('success', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('error_code', sa.String(length=50), nullable=True),
        sa.Column('error_category', sa.String(length=50), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['job_id'], ['processing_jobs.job_id'], name='fk_processing_metrics_job_id', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name='fk_processing_metrics_tenant_id', onupdate='RESTRICT', ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['case_id'], ['case_files.id'], name='fk_processing_metrics_case_id', ondelete='CASCADE')
    )
    op.create_index(op.f('ix_processing_metrics_id'), 'processing_metrics', ['id'], unique=False)
    op.create_index(op.f('ix_processing_metrics_job_id'), 'processing_metrics', ['job_id'], unique=False)
    op.create_index(op.f('ix_processing_metrics_tenant_id'), 'processing_metrics', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_processing_metrics_case_id'), 'processing_metrics', ['case_id'], unique=False)
    op.create_index(op.f('ix_processing_metrics_job_type'), 'processing_metrics', ['job_type'], unique=False)
    op.create_index(op.f('ix_processing_metrics_success'), 'processing_metrics', ['success'], unique=False)
    op.create_index(op.f('ix_processing_metrics_created_at'), 'processing_metrics', ['created_at'], unique=False)
    op.create_index('ix_processing_metrics_tenant_created', 'processing_metrics', ['tenant_id', 'created_at'], unique=False)
    op.create_index('ix_processing_metrics_type_created', 'processing_metrics', ['job_type', 'created_at'], unique=False)
    op.create_index('ix_processing_metrics_success_created', 'processing_metrics', ['success', 'created_at'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    # 1. Dropear processing_metrics
    op.drop_index('ix_processing_metrics_success_created', table_name='processing_metrics')
    op.drop_index('ix_processing_metrics_type_created', table_name='processing_metrics')
    op.drop_index('ix_processing_metrics_tenant_created', table_name='processing_metrics')
    op.drop_index(op.f('ix_processing_metrics_created_at'), table_name='processing_metrics')
    op.drop_index(op.f('ix_processing_metrics_success'), table_name='processing_metrics')
    op.drop_index(op.f('ix_processing_metrics_job_type'), table_name='processing_metrics')
    op.drop_index(op.f('ix_processing_metrics_case_id'), table_name='processing_metrics')
    op.drop_index(op.f('ix_processing_metrics_tenant_id'), table_name='processing_metrics')
    op.drop_index(op.f('ix_processing_metrics_job_id'), table_name='processing_metrics')
    op.drop_index(op.f('ix_processing_metrics_id'), table_name='processing_metrics')
    op.drop_table('processing_metrics')

    # 2. Dropear worker_heartbeats
    op.drop_index(op.f('ix_worker_heartbeats_last_seen'), table_name='worker_heartbeats')
    op.drop_index(op.f('ix_worker_heartbeats_worker_type'), table_name='worker_heartbeats')
    op.drop_table('worker_heartbeats')

    # 3. Eliminar columnas de processing_jobs
    op.drop_column('processing_jobs', 'worker_name')
    op.drop_column('processing_jobs', 'last_heartbeat_at')
    op.drop_column('processing_jobs', 'failure_classification')
    op.drop_column('processing_jobs', 'max_retries')
    op.drop_column('processing_jobs', 'attempt_count')
