"""quarantine_ambiguous_legacy_data

Revision ID: 9bec824404a5
Revises: 12fd022d7f66
Create Date: 2026-07-18 12:57:40.839542

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9bec824404a5'
down_revision: Union[str, Sequence[str], None] = '12fd022d7f66'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Identify ambiguous legacy cases using the corrected CTE.
    # A case is ambiguous if it has multiple documents AND at least one was processed by legacy V1.
    op.execute("""
        CREATE TEMP TABLE ambiguous_cases_temp AS
        WITH ambiguous_cases AS (
            SELECT ud.case_id
            FROM uploaded_documents ud
            WHERE ud.case_id IS NOT NULL
            GROUP BY ud.case_id
            HAVING COUNT(*) > 1
               AND BOOL_OR(
                   ud.ocr_engine_used IS NULL
                   OR ud.ocr_engine_used = 'v1'
               )
        )
        SELECT case_id FROM ambiguous_cases
    """)

    # 2. Backup affected records before deletion.
    op.execute("""
        CREATE TABLE IF NOT EXISTS quarantine_backup_comparison_runs (LIKE comparison_runs INCLUDING ALL);
        CREATE TABLE IF NOT EXISTS quarantine_backup_comparison_results (LIKE comparison_results INCLUDING ALL);
        CREATE TABLE IF NOT EXISTS quarantine_backup_requirement_items (LIKE requirement_items INCLUDING ALL);
        CREATE TABLE IF NOT EXISTS quarantine_backup_parsed_sections (LIKE parsed_sections INCLUDING ALL);
    """)

    op.execute("""
        INSERT INTO quarantine_backup_comparison_runs
        SELECT * FROM comparison_runs 
        WHERE case_id IN (SELECT case_id FROM ambiguous_cases_temp)
    """)
    op.execute("""
        INSERT INTO quarantine_backup_comparison_results
        SELECT * FROM comparison_results 
        WHERE run_id IN (SELECT id FROM quarantine_backup_comparison_runs)
    """)
    op.execute("""
        INSERT INTO quarantine_backup_parsed_sections
        SELECT * FROM parsed_sections 
        WHERE case_id IN (SELECT case_id FROM ambiguous_cases_temp)
    """)
    op.execute("""
        INSERT INTO quarantine_backup_requirement_items
        SELECT * FROM requirement_items 
        WHERE parsed_section_id IN (SELECT id FROM quarantine_backup_parsed_sections)
    """)

    # 3. Put ambiguous cases in quarantine / requires reprocessing.
    op.execute("""
        UPDATE case_files
        SET status = 'REQUIRES_REPROCESSING'
        WHERE id IN (SELECT case_id FROM ambiguous_cases_temp)
    """)

    # 4. Invalidate or delete the ambiguous legacy records.
    op.execute("""
        DELETE FROM comparison_results 
        WHERE run_id IN (SELECT id FROM comparison_runs WHERE case_id IN (SELECT case_id FROM ambiguous_cases_temp))
    """)
    op.execute("""
        UPDATE comparison_runs 
        SET status = 'FAILED', failure_detail = 'Quarantined due to ambiguous legacy OCR'
        WHERE case_id IN (SELECT case_id FROM ambiguous_cases_temp)
    """)
    op.execute("""
        DELETE FROM requirement_items 
        WHERE parsed_section_id IN (SELECT id FROM parsed_sections WHERE case_id IN (SELECT case_id FROM ambiguous_cases_temp))
    """)
    op.execute("""
        DELETE FROM parsed_sections 
        WHERE case_id IN (SELECT case_id FROM ambiguous_cases_temp)
    """)

    op.execute("DROP TABLE ambiguous_cases_temp")

def downgrade() -> None:
    # Downgrade reverts status and drops backup tables if needed, 
    # but we cannot automatically restore the deleted data without complex logic.
    pass
