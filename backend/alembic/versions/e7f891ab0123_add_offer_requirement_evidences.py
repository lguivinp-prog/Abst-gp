"""add offer requirement evidences table

Revision ID: e7f891ab0123
Revises: 52a123bc45de
Create Date: 2026-10-15 08:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e7f891ab0123'
down_revision: Union[str, Sequence[str], None] = '52a123bc45de'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Agregar columna traceability_regime a case_files
    op.add_column('case_files', sa.Column('traceability_regime', sa.String(length=50), server_default='P12_STRICT', nullable=False))
    # Expedientes preexistentes a P12 se clasifican bajo régimen histórico P11
    op.execute("UPDATE case_files SET traceability_regime = 'HISTORICAL_P11';")

    # 2. Crear tabla offer_requirement_evidences
    op.create_table(
        'offer_requirement_evidences',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('case_id', sa.Integer(), nullable=False),
        sa.Column('supplier_offer_id', sa.Integer(), nullable=False),
        sa.Column('requirement_id', sa.Integer(), nullable=False),
        sa.Column('offer_evidence_id', sa.Integer(), nullable=False),
        sa.Column('document_id', sa.Integer(), nullable=True),
        sa.Column('source_document', sa.String(length=255), nullable=True),
        sa.Column('page', sa.Integer(), nullable=True),
        sa.Column('fragment', sa.Text(), nullable=True),
        sa.Column('verification_status', sa.String(length=50), server_default='PENDING', nullable=False),
        sa.Column('verified_by', sa.Integer(), nullable=True),
        sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['case_id'], ['case_files.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['supplier_offer_id'], ['supplier_offers.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['requirement_id'], ['case_requirement_matrices.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['offer_evidence_id'], ['offer_evidences.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['document_id'], ['uploaded_documents.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['verified_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('requirement_id', 'offer_evidence_id', name='uq_requirement_offer_evidence')
    )
    op.create_index(op.f('ix_offer_requirement_evidences_id'), 'offer_requirement_evidences', ['id'], unique=False)
    op.create_index(op.f('ix_offer_requirement_evidences_case_id'), 'offer_requirement_evidences', ['case_id'], unique=False)
    op.create_index(op.f('ix_offer_requirement_evidences_supplier_offer_id'), 'offer_requirement_evidences', ['supplier_offer_id'], unique=False)
    op.create_index(op.f('ix_offer_requirement_evidences_requirement_id'), 'offer_requirement_evidences', ['requirement_id'], unique=False)
    op.create_index(op.f('ix_offer_requirement_evidences_offer_evidence_id'), 'offer_requirement_evidences', ['offer_evidence_id'], unique=False)
    op.create_index(op.f('ix_offer_requirement_evidences_verification_status'), 'offer_requirement_evidences', ['verification_status'], unique=False)

    # 3. Crear tabla de archivo histórico para preservar duplicados de evaluaciones con todos sus metadatos
    op.create_table(
        'archived_offer_evaluations',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('original_evaluation_id', sa.Integer(), nullable=False),
        sa.Column('supplier_offer_id', sa.Integer(), nullable=False),
        sa.Column('requirement_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('explanation', sa.Text(), nullable=True),
        sa.Column('evaluation_confidence', sa.Float(), nullable=True),
        sa.Column('validated_by', sa.Integer(), nullable=True),
        sa.Column('validated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('archived_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('archival_reason', sa.String(length=100), server_default='MIGRATION_DUPLICATE_P12', nullable=False),
        sa.PrimaryKeyConstraint('id')
    )

    # 4. CORRECCIÓN 4: Estrategia transaccional de archivo histórico y uso de columna real created_at en audit_logs
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM (
                    SELECT supplier_offer_id, requirement_id
                    FROM offer_evaluations
                    GROUP BY supplier_offer_id, requirement_id
                    HAVING count(*) > 1
                ) dupes
            ) THEN
                -- A. Preservar duplicados en tabla de archivo histórico con todos sus datos
                INSERT INTO archived_offer_evaluations (
                    original_evaluation_id, supplier_offer_id, requirement_id,
                    status, explanation, evaluation_confidence, validated_by, validated_at, created_at
                )
                SELECT 
                    oe.id, oe.supplier_offer_id, oe.requirement_id,
                    oe.status, oe.explanation, oe.evaluation_confidence, oe.validated_by, oe.validated_at, oe.created_at
                FROM offer_evaluations oe
                WHERE oe.id NOT IN (
                    SELECT MAX(id)
                    FROM offer_evaluations
                    GROUP BY supplier_offer_id, requirement_id
                );

                -- B. Registrar en audit_logs utilizando la columna real created_at (no timestamp)
                INSERT INTO audit_logs (action, entity_type, entity_id, details, status, created_at)
                SELECT 
                    'ARCHIVE_DUPLICATE_EVALUATION',
                    'OfferEvaluation',
                    oe.id::text,
                    json_build_object(
                        'original_id', oe.id,
                        'supplier_offer_id', oe.supplier_offer_id,
                        'requirement_id', oe.requirement_id,
                        'status', oe.status,
                        'explanation', oe.explanation,
                        'validated_by', oe.validated_by
                    )::text,
                    'ARCHIVED',
                    NOW()
                FROM offer_evaluations oe
                WHERE oe.id NOT IN (
                    SELECT MAX(id)
                    FROM offer_evaluations
                    GROUP BY supplier_offer_id, requirement_id
                );

                -- C. Eliminar duplicados de la tabla activa tras asegurar su preservación completa
                DELETE FROM offer_evaluations
                WHERE id NOT IN (
                    SELECT MAX(id)
                    FROM offer_evaluations
                    GROUP BY supplier_offer_id, requirement_id
                );
            END IF;
        END $$;
    """)

    # 5. Restricción única en offer_evaluations
    op.create_unique_constraint(
        'uq_offer_evaluations_offer_req',
        'offer_evaluations',
        ['supplier_offer_id', 'requirement_id']
    )


def downgrade() -> None:
    # 1. Eliminar restricción única si existe
    op.execute("ALTER TABLE offer_evaluations DROP CONSTRAINT IF EXISTS uq_offer_evaluations_offer_req;")

    # 2. Restaurar registros archivados a offer_evaluations si existe la tabla (con verificación estricta)
    op.execute("""
        DO $$
        DECLARE
            v_archived_count INT;
            v_collision_count INT;
            v_restored_count INT;
            v_mismatch_count INT;
        BEGIN
            IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'archived_offer_evaluations') THEN
                SELECT COUNT(*) INTO v_archived_count FROM archived_offer_evaluations;

                IF v_archived_count > 0 THEN
                    -- A. Detectar colisiones de IDs antes de intentar inserción
                    SELECT COUNT(*) INTO v_collision_count
                    FROM archived_offer_evaluations a
                    INNER JOIN offer_evaluations oe ON a.original_evaluation_id = oe.id;

                    IF v_collision_count > 0 THEN
                        RAISE EXCEPTION 'Downgrade abortado: Se detectaron % colisiones de ID entre archived_offer_evaluations y offer_evaluations. Imposible restaurar sin sobreescritura destructiva.', v_collision_count;
                    END IF;

                    -- B. Restaurar registros sin ON CONFLICT DO NOTHING
                    INSERT INTO offer_evaluations (id, supplier_offer_id, requirement_id, status, explanation, evaluation_confidence, validated_by, validated_at, created_at)
                    SELECT original_evaluation_id, supplier_offer_id, requirement_id, status, explanation, evaluation_confidence, validated_by, validated_at, created_at
                    FROM archived_offer_evaluations;

                    -- C. Verificar que todos los registros fueron restaurados
                    SELECT COUNT(*) INTO v_restored_count
                    FROM offer_evaluations oe
                    WHERE oe.id IN (SELECT original_evaluation_id FROM archived_offer_evaluations);

                    IF v_restored_count <> v_archived_count THEN
                        RAISE EXCEPTION 'Downgrade abortado: Mismatch en cantidad de registros restaurados. Esperados: %, Restaurados: %', v_archived_count, v_restored_count;
                    END IF;

                    -- D. Comprobar identificadores y campos originales
                    SELECT COUNT(*) INTO v_mismatch_count
                    FROM archived_offer_evaluations a
                    JOIN offer_evaluations oe ON a.original_evaluation_id = oe.id
                    WHERE a.supplier_offer_id <> oe.supplier_offer_id
                       OR a.requirement_id <> oe.requirement_id
                       OR a.status <> oe.status
                       OR COALESCE(a.explanation, '') <> COALESCE(oe.explanation, '');

                    IF v_mismatch_count > 0 THEN
                        RAISE EXCEPTION 'Downgrade abortado: Discrepancia en campos de registros restaurados. % inconsistencias.', v_mismatch_count;
                    END IF;
                END IF;

                -- E. Solo tras verificar que todos los registros están 100% restaurados e íntegros, eliminar la tabla de archivo
                DROP TABLE archived_offer_evaluations;
            END IF;
        END $$;
    """)

    # 3. Eliminar indices y tabla offer_requirement_evidences si existen
    op.execute("DROP TABLE IF EXISTS offer_requirement_evidences CASCADE;")

    # 4. Eliminar columna traceability_regime de case_files si existe
    op.execute("ALTER TABLE case_files DROP COLUMN IF EXISTS traceability_regime;")
