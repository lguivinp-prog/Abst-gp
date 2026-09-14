"""v6_sprint19_rag

Revision ID: 130000000000
Revises: 120000000000
Create Date: 2026-08-09 21:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '130000000000'
down_revision = '120000000000'
branch_labels = None
depends_on = None

def upgrade() -> None:
    # Adding optimization tracking fields to AIInteractionLog
    op.add_column('ai_interaction_logs', sa.Column('retrieval_time_ms', sa.Integer(), nullable=True))
    op.add_column('ai_interaction_logs', sa.Column('retrieval_strategy_version', sa.String(length=50), nullable=True))
    op.add_column('ai_interaction_logs', sa.Column('chunking_strategy_version', sa.String(length=50), nullable=True))
    op.add_column('ai_interaction_logs', sa.Column('retrieved_chunks', postgresql.JSONB(astext_type=sa.Text()), nullable=True))

def downgrade() -> None:
    pass
