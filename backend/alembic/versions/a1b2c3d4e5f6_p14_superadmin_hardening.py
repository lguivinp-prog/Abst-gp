"""add p14 superadmin hardening mfa and intrusion audit

Revision ID: a1b2c3d4e5f6
Revises: f8a920bc1234
Create Date: 2026-10-18 16:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'f8a920bc1234'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Tenant delegation flag y tenant del sistema 'system'
    op.add_column(
        'tenants',
        sa.Column('can_manage_users', sa.Boolean(), server_default='false', nullable=False)
    )
    op.execute(
        "INSERT INTO tenants (id, name, can_manage_users, created_at) "
        "VALUES ('system', 'Plataforma ABST-GP Master', false, NOW()) "
        "ON CONFLICT (id) DO NOTHING"
    )

    # 2. Columnas de seguridad, MFA y sesion en users
    op.add_column(
        'users',
        sa.Column('mfa_status', sa.String(length=30), server_default='DISABLED', nullable=False)
    )
    op.add_column(
        'users',
        sa.Column('mfa_secret', sa.Text(), nullable=True)
    )
    op.add_column(
        'users',
        sa.Column('mfa_last_totp_step', sa.BigInteger(), nullable=True)
    )
    op.add_column(
        'users',
        sa.Column('mfa_last_verified_at', sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        'users',
        sa.Column('session_version', sa.Integer(), server_default='1', nullable=False)
    )

    # 3. Indice singleton estricto para SUPERADMIN
    op.create_index(
        'ix_users_superadmin_singleton',
        'users',
        ['role'],
        unique=True,
        postgresql_where=sa.text("role = 'SUPERADMIN'")
    )

    # 4. Tabla de codigos de rescate break-glass
    op.create_table(
        'user_recovery_codes',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('code_hash', sa.String(length=128), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('used_at', sa.DateTime(timezone=True), nullable=True)
    )
    op.create_index('ix_user_recovery_codes_user_id', 'user_recovery_codes', ['user_id'])

    # 5. Tabla de sesiones activas revocables
    op.create_table(
        'user_sessions',
        sa.Column('id', sa.String(length=64), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.Column('user_agent', sa.String(length=255), nullable=True),
        sa.Column('session_version', sa.Integer(), server_default='1', nullable=False),
        sa.Column('is_revoked', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('last_activity_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False)
    )
    op.create_index('ix_user_sessions_user_id', 'user_sessions', ['user_id'])

    # 6. Tabla de eventos de intrusion y alertas de seguridad
    op.create_table(
        'security_intrusion_events',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('ip_address', sa.String(length=45), nullable=False),
        sa.Column('user_identifier', sa.String(length=100), nullable=True),
        sa.Column('tenant_id', sa.String(length=50), nullable=True),
        sa.Column('event_type', sa.String(length=50), nullable=False),
        sa.Column('severity', sa.String(length=20), nullable=False),
        sa.Column('details', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('occurred_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)
    )
    op.create_index('ix_security_events_ip_time', 'security_intrusion_events', ['ip_address', 'occurred_at'])
    op.create_index('ix_security_events_type_time', 'security_intrusion_events', ['event_type', 'occurred_at'])

    # 7. Tabla outbox de alertas para envio fuera de banda
    op.create_table(
        'security_alert_outbox',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('event_id', sa.Integer(), sa.ForeignKey('security_intrusion_events.id', ondelete='CASCADE'), nullable=False),
        sa.Column('channel', sa.String(length=50), nullable=False),
        sa.Column('destination', sa.String(length=255), nullable=True),
        sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('status', sa.String(length=20), server_default='PENDING', nullable=False),
        sa.Column('attempts', sa.Integer(), server_default='0', nullable=False),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_attempt_at', sa.DateTime(timezone=True), nullable=True)
    )
    # 8. Tabla de concesiones de auditoria multitenant (R3-01)
    op.create_table(
        'audit_delegation_grants',
        sa.Column('id', sa.String(length=64), primary_key=True),
        sa.Column('target_tenant_id', sa.String(length=50), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('granted_to_user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('granted_by_user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('scope', sa.String(length=50), server_default='READ_ONLY_AUDIT', nullable=False),
        sa.Column('reason', sa.String(length=255), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('is_revoked', sa.Boolean(), server_default='false', nullable=False)
    )
    op.create_index('ix_audit_delegation_target_user', 'audit_delegation_grants', ['target_tenant_id', 'granted_to_user_id'])


def downgrade() -> None:
    # Salvaguarda de seguridad (P14-R1-16): impedir downgrade destructivo si existen identidades activas
    bind = op.get_bind()
    try:
        active_count = bind.execute(
            sa.text("SELECT count(*) FROM users WHERE tenant_id = 'system' OR role = 'SUPERADMIN'")
        ).scalar()
        if active_count and active_count > 0:
            raise RuntimeError(
                "Downgrade abortado por salvaguarda de seguridad (P14-R1-16): existen identidades activas en tenant 'system' o con rol SUPERADMIN. "
                "El downgrade destructivo no esta permitido con identidades aprovisionadas. "
                "Requiere intervencion administrativa autorizada y respaldo previo."
            )
    except Exception as e:
        if "Downgrade abortado" in str(e):
            raise
        # Si la tabla users no existe o no tiene las columnas, continuar con la limpieza normal
        pass

    op.drop_index('ix_audit_delegation_target_user', table_name='audit_delegation_grants')
    op.drop_table('audit_delegation_grants')
    op.drop_table('security_alert_outbox')
    op.drop_table('security_intrusion_events')
    op.drop_table('user_sessions')
    op.drop_table('user_recovery_codes')
    op.drop_index('ix_users_superadmin_singleton', table_name='users')
    op.drop_column('users', 'session_version')
    op.drop_column('users', 'mfa_last_verified_at')
    op.drop_column('users', 'mfa_last_totp_step')
    op.drop_column('users', 'mfa_secret')
    op.drop_column('users', 'mfa_status')
    
    # R3-11: Preservar datos de negocio historicos (eliminado DELETE FROM suppliers)
    try:
        dep_count = bind.execute(
            sa.text("SELECT count(*) FROM suppliers WHERE tenant_id = 'system'")
        ).scalar()
        if not dep_count or dep_count == 0:
            op.execute("DELETE FROM tenants WHERE id = 'system'")
    except Exception:
        pass
    op.drop_column('tenants', 'can_manage_users')

