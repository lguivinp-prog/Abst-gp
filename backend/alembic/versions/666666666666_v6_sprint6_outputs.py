"""v6_sprint6_outputs

Revision ID: 666666666666
Revises: 555555555555
Create Date: 2026-08-09 18:47:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '666666666666'
down_revision = '555555555555'
branch_labels = None
depends_on = None

def upgrade() -> None:
    # 1. order_preparation_profiles
    op.create_table(
        'order_preparation_profiles',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('supplier_selection_final_id', sa.Integer(), nullable=False),
        sa.Column('supplier_data', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('contracting_data', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('improvements_data', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['supplier_selection_final_id'], ['supplier_selection_final.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('supplier_selection_final_id')
    )
    op.create_index(op.f('ix_order_preparation_profiles_id'), 'order_preparation_profiles', ['id'], unique=False)
    op.create_index(op.f('ix_order_preparation_profiles_supplier_selection_final_id'), 'order_preparation_profiles', ['supplier_selection_final_id'], unique=False)

    # 2. output_templates
    op.create_table(
        'output_templates',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('type', sa.String(length=50), nullable=False),
        sa.Column('version', sa.String(length=20), nullable=False),
        sa.Column('entity_name', sa.String(), nullable=False),
        sa.Column('validity', sa.String(length=50), nullable=True),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=50), server_default='ACTIVE', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_output_templates_id'), 'output_templates', ['id'], unique=False)

    # 3. generated_outputs
    op.add_column('generated_outputs', sa.Column('template_id', sa.Integer(), nullable=True))
    op.add_column('generated_outputs', sa.Column('content_rendered', sa.Text(), nullable=True))
    op.add_column('generated_outputs', sa.Column('generation_hash', sa.String(), nullable=True))
    op.add_column('generated_outputs', sa.Column('generated_by', sa.Integer(), nullable=True))
    op.add_column('generated_outputs', sa.Column('generated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True))
    op.add_column('generated_outputs', sa.Column('template_version', sa.String(length=20), nullable=True))
    op.add_column('generated_outputs', sa.Column('accuracy_gate_result', sa.String(length=50), nullable=True))
    op.add_column('generated_outputs', sa.Column('source_snapshot', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('generated_outputs', sa.Column('status', sa.String(length=50), server_default='GENERATED', nullable=False))
    
    op.create_foreign_key(None, 'generated_outputs', 'users', ['generated_by'], ['id'], ondelete='SET NULL')
    op.create_foreign_key(None, 'generated_outputs', 'output_templates', ['template_id'], ['id'], ondelete='RESTRICT')
    
    # case_id index was already created in initial_models, or maybe not. initial_models only created index for id.
    op.create_index(op.f('ix_generated_outputs_case_id'), 'generated_outputs', ['case_id'], unique=False)

def downgrade() -> None:
    op.drop_table('generated_outputs')
    op.drop_table('output_templates')
    op.drop_table('order_preparation_profiles')
