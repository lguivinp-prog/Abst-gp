"""v6_sprint25_admin

Revision ID: 140000000000
Revises: 130000000000
Create Date: 2026-08-09 23:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '140000000000'
down_revision = '130000000000'
branch_labels = None
depends_on = None

def upgrade() -> None:
    # 1. Institutional Telemetry Events
    op.create_table('institutional_telemetry_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.String(), nullable=False),
        sa.Column('system_version', sa.String(), nullable=False),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.Column('avg_rag_latency_ms', sa.Float(), nullable=True),
        sa.Column('avg_ocr_latency_ms', sa.Float(), nullable=True),
        sa.Column('total_cases_processed', sa.Integer(), nullable=True),
        sa.Column('total_supervisor_exceptions', sa.Integer(), nullable=True),
        sa.Column('blocked_by_quality_gate', sa.Integer(), nullable=True),
        sa.Column('api_fallback_events', sa.Integer(), nullable=True),
        sa.Column('rag_human_correction_rate', sa.Float(), nullable=True),
        sa.Column('telemetry_policy_version', sa.String(), nullable=False),
        sa.Column('opt_in_status', sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_institutional_telemetry_events_id'), 'institutional_telemetry_events', ['id'], unique=False)
    op.create_index(op.f('ix_institutional_telemetry_events_tenant_id'), 'institutional_telemetry_events', ['tenant_id'], unique=False)

    # 2. Tenant Configurations
    op.create_table('tenant_configurations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.String(), nullable=False),
        sa.Column('min_dpi_threshold', sa.Integer(), nullable=True),
        sa.Column('min_rag_confidence', sa.Integer(), nullable=True),
        sa.Column('telemetry_opt_in', sa.Boolean(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_tenant_configurations_id'), 'tenant_configurations', ['id'], unique=False)
    op.create_index(op.f('ix_tenant_configurations_tenant_id'), 'tenant_configurations', ['tenant_id'], unique=True)


def downgrade() -> None:
    pass
