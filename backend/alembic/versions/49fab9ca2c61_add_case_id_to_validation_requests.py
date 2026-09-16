"""add case_id to validation_requests

Revision ID: 49fab9ca2c61
Revises: 38eda9ca2c50
Create Date: 2026-09-15 19:19:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '49fab9ca2c61'
down_revision = '38eda9ca2c50'
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column('validation_requests', sa.Column('case_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_validation_requests_case_id', 'validation_requests', 'case_files', ['case_id'], ['id'], ondelete='CASCADE')
    op.create_index('ix_validation_requests_case_id', 'validation_requests', ['case_id'])

def downgrade() -> None:
    op.drop_index('ix_validation_requests_case_id', table_name='validation_requests')
    op.drop_constraint('fk_validation_requests_case_id', 'validation_requests', type_='foreignkey')
    op.drop_column('validation_requests', 'case_id')
