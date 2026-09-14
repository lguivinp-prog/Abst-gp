"""v6_sprint9_rag

Revision ID: 888888888888
Revises: 777777777777
Create Date: 2026-08-09 19:04:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '888888888888'
down_revision = '777777777777'
branch_labels = None
depends_on = None

def upgrade() -> None:
    # 1. Update ai_interaction_logs
    op.add_column('ai_interaction_logs', sa.Column('retrieval_strategy_version', sa.String(length=50), nullable=True))
    op.add_column('ai_interaction_logs', sa.Column('retrieved_chunks', postgresql.JSONB(astext_type=sa.Text()), nullable=True))

    # 2. document_chunks
    op.create_table(
        'document_chunks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('document_id', sa.Integer(), nullable=False),
        sa.Column('case_id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.String(length=50), nullable=False),
        sa.Column('page', sa.Integer(), nullable=True),
        sa.Column('chunk_index', sa.Integer(), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('hash', sa.String(length=255), nullable=False),
        sa.Column('source_type', sa.String(length=50), nullable=False),
        sa.Column('chunk_metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['case_id'], ['case_files.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_document_chunks_case_id'), 'document_chunks', ['case_id'], unique=False)
    op.create_index(op.f('ix_document_chunks_document_id'), 'document_chunks', ['document_id'], unique=False)
    op.create_index(op.f('ix_document_chunks_id'), 'document_chunks', ['id'], unique=False)
    op.create_index(op.f('ix_document_chunks_tenant_id'), 'document_chunks', ['tenant_id'], unique=False)

def downgrade() -> None:
    op.drop_table('document_chunks')
    op.drop_column('ai_interaction_logs', 'retrieved_chunks')
    op.drop_column('ai_interaction_logs', 'retrieval_strategy_version')
