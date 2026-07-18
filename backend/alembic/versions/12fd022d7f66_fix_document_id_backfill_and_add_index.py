"""fix_document_id_backfill_and_add_index

Revision ID: 12fd022d7f66
Revises: 3c79a0473766
Create Date: 2026-07-18 02:25:26.173261

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '12fd022d7f66'
down_revision: Union[str, Sequence[str], None] = '3c79a0473766'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Reassign quotation sections that were incorrectly assigned to requirement document
    # A ParsedSection that is not referenced by any RequirementItem is a quotation section.
    op.execute("""
        UPDATE parsed_sections
        SET document_id = (
            SELECT id FROM uploaded_documents 
            WHERE case_id = parsed_sections.case_id 
              AND document_type = 'quotation' 
            LIMIT 1
        )
        WHERE document_id IS NOT NULL 
          AND id NOT IN (SELECT parsed_section_id FROM requirement_items WHERE parsed_section_id IS NOT NULL)
          AND EXISTS (
              SELECT 1 FROM uploaded_documents 
              WHERE case_id = parsed_sections.case_id 
                AND document_type = 'quotation'
          )
    """)

    # 1.1 Delete orphaned parsed_sections
    op.execute("DELETE FROM parsed_sections WHERE document_id IS NULL")

    # 2. Make document_id non-nullable
    op.alter_column('parsed_sections', 'document_id',
               existing_type=sa.Integer(),
               nullable=False)

    # 3. Add index
    op.create_index(
        "ix_parsed_sections_document_id",
        "parsed_sections",
        ["document_id"],
    )

def downgrade() -> None:
    op.drop_index("ix_parsed_sections_document_id", table_name="parsed_sections")
    op.alter_column('parsed_sections', 'document_id',
               existing_type=sa.Integer(),
               nullable=True)
