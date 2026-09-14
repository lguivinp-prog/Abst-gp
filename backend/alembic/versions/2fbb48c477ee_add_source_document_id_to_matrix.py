"""add_source_document_id_to_matrix

Revision ID: 2fbb48c477ee
Revises: 1daa48c477ee
Create Date: 2026-09-14 11:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2fbb48c477ee'
down_revision: Union[str, Sequence[str], None] = '1daa48c477ee'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('case_requirement_matrices', sa.Column('source_document_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'fk_case_requirement_matrices_source_document_id',
        'case_requirement_matrices',
        'uploaded_documents',
        ['source_document_id'],
        ['id'],
        ondelete='SET NULL'
    )
    op.create_index(
        op.f('ix_case_requirement_matrices_source_document_id'),
        'case_requirement_matrices',
        ['source_document_id'],
        unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_case_requirement_matrices_source_document_id'), table_name='case_requirement_matrices')
    op.drop_constraint('fk_case_requirement_matrices_source_document_id', 'case_requirement_matrices', type_='foreignkey')
    op.drop_column('case_requirement_matrices', 'source_document_id')
