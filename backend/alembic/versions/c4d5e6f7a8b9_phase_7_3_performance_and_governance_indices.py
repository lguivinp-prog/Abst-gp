"""phase_7_3_performance_and_governance_indices

Revision ID: c4d5e6f7a8b9
Revises: b2c3d4e5f6a7
Create Date: 2026-08-04 18:25:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4d5e6f7a8b9'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add composite indices for high performance queries and tenant capacity governance."""
    # 1. ProcessingJob composite indices
    op.create_index(
        'ix_processing_jobs_tenant_status',
        'processing_jobs',
        ['tenant_id', 'status'],
        unique=False
    )
    op.create_index(
        'ix_processing_jobs_status_heartbeat',
        'processing_jobs',
        ['status', 'last_heartbeat_at'],
        unique=False
    )
    op.create_index(
        'ix_processing_jobs_status_created',
        'processing_jobs',
        ['status', 'created_at'],
        unique=False
    )
    op.create_index(
        'ix_processing_jobs_tenant_created',
        'processing_jobs',
        ['tenant_id', 'created_at'],
        unique=False
    )

    # 2. WorkerHeartbeat composite index
    op.create_index(
        'ix_worker_heartbeats_status_last_seen',
        'worker_heartbeats',
        ['status', 'last_seen'],
        unique=False
    )

    # 3. AuditLog composite indices
    op.create_index(
        'ix_audit_logs_action_entity',
        'audit_logs',
        ['action', 'entity_id'],
        unique=False
    )
    op.create_index(
        'ix_audit_logs_tenant_created',
        'audit_logs',
        ['tenant_id', 'created_at'],
        unique=False
    )


def downgrade() -> None:
    """Drop composite indices."""
    op.drop_index('ix_audit_logs_tenant_created', table_name='audit_logs')
    op.drop_index('ix_audit_logs_action_entity', table_name='audit_logs')
    op.drop_index('ix_worker_heartbeats_status_last_seen', table_name='worker_heartbeats')
    op.drop_index('ix_processing_jobs_tenant_created', table_name='processing_jobs')
    op.drop_index('ix_processing_jobs_status_created', table_name='processing_jobs')
    op.drop_index('ix_processing_jobs_status_heartbeat', table_name='processing_jobs')
    op.drop_index('ix_processing_jobs_tenant_status', table_name='processing_jobs')
