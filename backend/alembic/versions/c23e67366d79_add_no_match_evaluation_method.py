"""add_no_match_evaluation_method

Revision ID: c23e67366d79
Revises: e74f1c1d81b9
Create Date: 2026-07-17 21:55:48.184681

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c23e67366d79'
down_revision: Union[str, Sequence[str], None] = 'e74f1c1d81b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # En PostgreSQL 12+ ALTER TYPE ... ADD VALUE se puede hacer dentro de bloque transaccional.
    # En versiones anteriores requiere disable_transaction. 
    # Usaremos COMMIT por seguridad si falla el bloque normal de Alembic.
    op.execute("ALTER TYPE comparison_evaluation_method_enum ADD VALUE IF NOT EXISTS 'NO_MATCH'")

def downgrade() -> None:
    """Downgrade schema."""
    # Eliminar valores de ENUM no está soportado nativamente en PostgreSQL 
    # sin recrear el tipo completo. Dado que NO_MATCH es un valor terminal seguro, 
    # se deja persistente en el downgrade.
    pass
