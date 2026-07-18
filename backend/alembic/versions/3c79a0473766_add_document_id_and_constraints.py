"""add_document_id_and_constraints

Revision ID: 3c79a0473766
Revises: c23e67366d79
Create Date: 2026-07-18 01:49:21.282099

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3c79a0473766'
down_revision: Union[str, Sequence[str], None] = 'c23e67366d79'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add document_id column
    op.add_column('parsed_sections', sa.Column('document_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_parsed_sections_document_id', 'parsed_sections', 'uploaded_documents', ['document_id'], ['id'], ondelete='CASCADE')
    
    # 2. Add Unique constraint
    op.create_unique_constraint('uq_comparison_run_requirement', 'comparison_results', ['run_id', 'requirement_item_id'])

    # 3. Safe Backfill: Only update parsed_sections where the case has EXACTLY ONE requirement document.
    op.execute("""
        UPDATE parsed_sections ps
        SET document_id = doc.id
        FROM  (
            SELECT case_id, min(id) as id
            FROM uploaded_documents
            WHERE document_type = 'requirement'
            GROUP BY case_id
            HAVING count(id) = 1
        ) doc
        WHERE ps.case_id = doc.case_id
          AND ps.document_id IS NULL
    """)


def downgrade() -> None:
    op.drop_constraint('uq_comparison_run_requirement', 'comparison_results', type_='unique')
    op.drop_constraint('fk_parsed_sections_document_id', 'parsed_sections', type_='foreignkey')
    op.drop_column('parsed_sections', 'document_id')
