"""quarantine_mixed_v1_v2

Revision ID: 476e2601363c
Revises: 12fd022d7f66
Create Date: 2026-07-18 23:32:38.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '476e2601363c'
down_revision: Union[str, Sequence[str], None] = '12fd022d7f66'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Identify ambiguous legacy cases using COUNT(*) and BOOL_OR.
    op.execute("""
        CREATE TEMP TABLE ambiguous_cases_temp AS
        WITH ambiguous_cases AS (
            SELECT ud.case_id,
                   COUNT(ud.id) as doc_count,
                   COUNT(ud.id) FILTER (WHERE ud.ocr_engine_used IS NULL OR ud.ocr_engine_used = 'v1') as legacy_doc_count
            FROM uploaded_documents ud
            WHERE ud.case_id IS NOT NULL
            GROUP BY ud.case_id
            HAVING COUNT(*) > 1
               AND BOOL_OR(
                   ud.ocr_engine_used IS NULL
                   OR ud.ocr_engine_used = 'v1'
               )
        )
        SELECT ac.case_id, ac.doc_count, ac.legacy_doc_count, cf.status as original_status
        FROM ambiguous_cases ac
        JOIN case_files cf ON ac.case_id = cf.id
    """)

    # 2. Backup affected records before deletion.
    op.execute("""
        CREATE TABLE IF NOT EXISTS quarantine_backup_comparison_runs (LIKE comparison_runs);
        CREATE TABLE IF NOT EXISTS quarantine_backup_comparison_results (LIKE comparison_results);
        CREATE TABLE IF NOT EXISTS quarantine_backup_requirement_items (LIKE requirement_items);
        CREATE TABLE IF NOT EXISTS quarantine_backup_parsed_sections (LIKE parsed_sections);
        CREATE TABLE IF NOT EXISTS quarantine_manifest (
            case_id INTEGER PRIMARY KEY,
            original_status VARCHAR,
            doc_count INTEGER,
            legacy_doc_count INTEGER,
            quarantined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    op.execute("""
        INSERT INTO quarantine_manifest (case_id, original_status, doc_count, legacy_doc_count)
        SELECT case_id, original_status, doc_count, legacy_doc_count FROM ambiguous_cases_temp
        ON CONFLICT DO NOTHING
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
        SET status = 'FAILED'
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
    raise RuntimeError(
        "Migration 476e2601363c is irreversible; "
        "restore the pre-migration database snapshot."
    )
