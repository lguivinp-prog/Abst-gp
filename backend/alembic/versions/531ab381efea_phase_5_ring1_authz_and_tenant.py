"""phase 5 ring1 authz and tenant

Revision ID: 531ab381efea
Revises: 476e2601363c
Create Date: 2026-07-19 11:20:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '531ab381efea'
down_revision = '476e2601363c'
branch_labels = None
depends_on = None

def upgrade() -> None:
    # 1. Update users table
    op.add_column('users', sa.Column('must_change_password', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('users', sa.Column('created_by_user_id', sa.Integer(), nullable=True))
    op.add_column('users', sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('users', sa.Column('failed_login_count', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('users', sa.Column('locked_until', sa.DateTime(timezone=True), nullable=True))
    op.add_column('users', sa.Column('password_changed_at', sa.DateTime(timezone=True), nullable=True))
    
    op.create_foreign_key('fk_users_created_by', 'users', 'users', ['created_by_user_id'], ['id'])
    
    # partial unique index for admin
    op.create_index('ix_users_admin_singleton', 'users', ['role'], unique=True, postgresql_where=sa.text("role = 'ADMIN'"))

    # 2. Update case_files table
    op.add_column('case_files', sa.Column('assigned_to_user_id', sa.Integer(), nullable=True))
    op.add_column('case_files', sa.Column('assigned_by_user_id', sa.Integer(), nullable=True))
    op.add_column('case_files', sa.Column('assigned_at', sa.DateTime(timezone=True), nullable=True))
    
    op.create_foreign_key('fk_cases_assigned_to', 'case_files', 'users', ['assigned_to_user_id'], ['id'])
    op.create_foreign_key('fk_cases_assigned_by', 'case_files', 'users', ['assigned_by_user_id'], ['id'])

    # 3. Update audit_logs table
    # entity_id is currently Integer. We want to change it to String.
    op.alter_column('audit_logs', 'entity_id',
               existing_type=sa.Integer(),
               type_=sa.String(),
               existing_nullable=False)
    op.add_column('audit_logs', sa.Column('status', sa.String(), nullable=True))

    # 4. Create rollout_tenant_assignments table
    op.create_table('rollout_tenant_assignments',
        sa.Column('tenant_id', sa.String(length=50), nullable=False),
        sa.Column('assigned_ring', sa.Integer(), nullable=True),
        sa.Column('assignment_version', sa.String(length=20), nullable=False),
        sa.Column('routing_mode', sa.String(length=50), nullable=False, server_default='AUTO'),
        sa.Column('override_until', sa.DateTime(timezone=True), nullable=True),
        sa.Column('reason', sa.String(length=100), nullable=True),
        sa.Column('assigned_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('tenant_id')
    )


def downgrade() -> None:
    # 4. Drop rollout_tenant_assignments
    op.drop_table('rollout_tenant_assignments')

    # 3. Revert audit_logs
    op.drop_column('audit_logs', 'status')
    # Casting string back to integer can fail if non-integers are present.
    op.alter_column('audit_logs', 'entity_id',
               existing_type=sa.String(),
               type_=sa.Integer(),
               existing_nullable=False,
               postgresql_using='entity_id::integer')

    # 2. Revert case_files
    op.drop_constraint('fk_cases_assigned_by', 'case_files', type_='foreignkey')
    op.drop_constraint('fk_cases_assigned_to', 'case_files', type_='foreignkey')
    op.drop_column('case_files', 'assigned_at')
    op.drop_column('case_files', 'assigned_by_user_id')
    op.drop_column('case_files', 'assigned_to_user_id')

    # 1. Revert users
    op.drop_index('ix_users_admin_singleton', table_name='users', postgresql_where=sa.text("role = 'ADMIN'"))
    op.drop_constraint('fk_users_created_by', 'users', type_='foreignkey')
    op.drop_column('users', 'password_changed_at')
    op.drop_column('users', 'locked_until')
    op.drop_column('users', 'failed_login_count')
    op.drop_column('users', 'last_login_at')
    op.drop_column('users', 'created_by_user_id')
    op.drop_column('users', 'must_change_password')
