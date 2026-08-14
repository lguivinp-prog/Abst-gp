"""v6_sprint8_ai

Revision ID: 777777777777
Revises: 666666666666
Create Date: 2026-08-09 18:57:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = '777777777777'
down_revision = '666666666666'
branch_labels = None
depends_on = None

def upgrade() -> None:
    # 1. prompt_registries
    op.create_table(
        'prompt_registries',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('version', sa.String(length=20), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=50), server_default='ACTIVE', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_prompt_registries_id'), 'prompt_registries', ['id'], unique=False)

    # 2. ai_interaction_logs
    op.create_table(
        'ai_interaction_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('case_id', sa.Integer(), nullable=True),
        sa.Column('provider', sa.String(length=50), nullable=False),
        sa.Column('model_version', sa.String(length=50), nullable=False),
        sa.Column('prompt_version', sa.String(length=50), nullable=False),
        sa.Column('question', sa.Text(), nullable=False),
        sa.Column('context_hash', sa.String(length=255), nullable=False),
        sa.Column('response', sa.Text(), nullable=False),
        sa.Column('response_hash', sa.String(length=255), nullable=False),
        sa.Column('tokens_used', sa.Integer(), nullable=True),
        sa.Column('timestamp', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['case_id'], ['case_files.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_ai_interaction_logs_case_id'), 'ai_interaction_logs', ['case_id'], unique=False)
    op.create_index(op.f('ix_ai_interaction_logs_id'), 'ai_interaction_logs', ['id'], unique=False)

def downgrade() -> None:
    op.drop_table('ai_interaction_logs')
    op.drop_table('prompt_registries')
