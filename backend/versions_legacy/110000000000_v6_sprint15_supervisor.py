"""v6_sprint15_supervisor

Revision ID: 110000000000
Revises: 100000000000
Create Date: 2026-08-09 20:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '110000000000'
down_revision = '100000000000'
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table(
        'case_operational_snapshots',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('case_id', sa.Integer(), nullable=False),
        sa.Column('current_status', sa.String(length=50), nullable=False),
        sa.Column('pending_actions', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('risk_level', sa.String(length=20), server_default='LOW', nullable=False),
        sa.Column('risk_reason', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('last_activity', sa.String(length=255), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['case_id'], ['case_files.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('case_id')
    )
    op.create_index(op.f('ix_case_operational_snapshots_case_id'), 'case_operational_snapshots', ['case_id'], unique=True)
    op.create_index(op.f('ix_case_operational_snapshots_id'), 'case_operational_snapshots', ['id'], unique=False)

def downgrade() -> None:
    pass
