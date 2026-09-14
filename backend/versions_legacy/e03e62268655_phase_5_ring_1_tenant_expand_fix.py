"""phase_5_ring_1_tenant_expand_fix

Revision ID: e03e62268655
Revises: 910786f497cb
Create Date: 2026-07-21 01:14:58.082081

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e03e62268655'
down_revision: Union[str, Sequence[str], None] = '910786f497cb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    context = op.get_context()
    
    # 1. SystemSettings: Singleton and default logic
    if context.as_sql:
        # En modo offline no podemos inspeccionar la BD, generamos un script genérico o evitamos la falla.
        # Imprimimos el statement para que quede documentado en el volcado SQL
        op.execute("INSERT INTO system_settings (id, active_ring) SELECT 1, 0 WHERE NOT EXISTS (SELECT 1 FROM system_settings)")
    else:
        conn = op.get_bind()
        res = conn.execute(sa.text("SELECT id, active_ring FROM system_settings")).fetchall()
        if len(res) == 0:
            # Insert canonical row
            conn.execute(sa.text("INSERT INTO system_settings (id, active_ring) VALUES (1, 0)"))
        elif len(res) == 1:
            row = res[0]
            if row[0] != 1:
                raise Exception("system_settings contains a row with id != 1. Aborting migration.")
            if row[1] != 0:
                raise Exception(f"system_settings contains active_ring={row[1]}. Expected 0. Aborting migration.")
        else:
            raise Exception("system_settings contains multiple rows. Aborting migration.")
        
    # Add constraint
    op.execute("ALTER TABLE system_settings ADD CONSTRAINT check_system_settings_singleton CHECK (id = 1)")
    
    # 2. Guardrail temporal: NO NEW NULLs in Expand
    op.execute("ALTER TABLE users ADD CONSTRAINT chk_users_tenant_id_not_null CHECK (tenant_id IS NOT NULL) NOT VALID")
    op.execute("ALTER TABLE case_files ADD CONSTRAINT chk_case_files_tenant_id_not_null CHECK (tenant_id IS NOT NULL) NOT VALID")
    op.execute("ALTER TABLE audit_logs ADD CONSTRAINT chk_audit_logs_tenant_id_not_null CHECK (tenant_id IS NOT NULL) NOT VALID")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("ALTER TABLE audit_logs DROP CONSTRAINT IF EXISTS chk_audit_logs_tenant_id_not_null")
    op.execute("ALTER TABLE case_files DROP CONSTRAINT IF EXISTS chk_case_files_tenant_id_not_null")
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS chk_users_tenant_id_not_null")
    op.execute("ALTER TABLE system_settings DROP CONSTRAINT IF EXISTS check_system_settings_singleton")
