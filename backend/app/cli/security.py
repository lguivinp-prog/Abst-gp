"""
Herramienta CLI de Consola Local Segura para ABST-GP V6 (P14 Hardening).
Permite el aprovisionamiento fuera de banda del SUPERADMIN, rotacion de MFA
y procedimientos de rescate fisico de emergencia (P14-R1-15).
"""

import sys
import os
import getpass
import argparse
from datetime import datetime, timezone
from typing import Optional

from app.core.database import SessionLocal
from app.core.config import settings
from app.core.crypto import encrypt_aead, hash_recovery_code, generate_recovery_codes
from app.core.mfa import generate_totp_secret, get_totp_provisioning_uri, MfaStatus
from app.models.domain import User, Tenant, UserRecoveryCode, UserSession
from app.api.auth import get_password_hash, verify_password


def provision_superadmin(username: str, password: Optional[str] = None):
    """
    Aprovisionamiento seguro fuera de banda del SUPERADMIN unico (P14-R1-15).
    Idempotente: falla si ya existe una cuenta SUPERADMIN en la base de datos.
    """
    db = SessionLocal()
    try:
        # 1. Comprobacion de unicidad estricta (Singleton)
        existing_superadmin = db.query(User).filter(User.role == "SUPERADMIN").first()
        if existing_superadmin:
            print(f"[ERROR] Verificacion de singleton fallida: Ya existe el SUPERADMIN '{existing_superadmin.username}'.")
            print("El aprovisionamiento es estrictamente de un solo uso por instalacion.")
            sys.exit(1)

        # 2. Comprobar colision de username
        existing_user = db.query(User).filter(User.username == username).first()
        if existing_user:
            print(f"[ERROR] Ya existe un usuario con el nombre '{username}'.")
            sys.exit(1)

        # 3. Obtener contrasena de forma segura (interactiva o env var preferida sobre argv)
        if not password:
            env_pwd = os.getenv("SUPERADMIN_PASSWORD")
            if env_pwd:
                password = env_pwd
            else:
                password = getpass.getpass(f"Ingrese contrasena segura para SUPERADMIN '{username}' (min 12 caracteres): ")
                confirm = getpass.getpass("Confirme la contrasena: ")
                if password != confirm:
                    print("[ERROR] Las contrasenas no coinciden.")
                    sys.exit(1)

        if len(password) < 12:
            print("[ERROR] La contrasena de SUPERADMIN debe tener al menos 12 caracteres.")
            sys.exit(1)

        # 4. Asegurar existencia del tenant del sistema
        system_tenant = db.query(Tenant).filter(Tenant.id == "system").first()
        if not system_tenant:
            system_tenant = Tenant(
                id="system",
                name="Plataforma ABST-GP Master",
                can_manage_users=True
            )
            db.add(system_tenant)
            db.flush()

        # 5. Generar secreto TOTP y cifrar con AEAD versionada
        raw_secret = generate_totp_secret()
        mfa_encryption_key = getattr(settings, "MFA_ENCRYPTION_KEY", "deterministic_test_mfa_key_32b_!")
        encrypted_secret = encrypt_aead(raw_secret, mfa_encryption_key, key_id="v1")

        # 6. Crear cuenta SUPERADMIN
        new_superadmin = User(
            username=username,
            password_hash=get_password_hash(password),
            role="SUPERADMIN",
            tenant_id="system",
            is_active=True,
            must_change_password=False,
            mfa_status=MfaStatus.ENABLED.value,
            mfa_secret=encrypted_secret,
            session_version=1,
            created_at=datetime.now(timezone.utc)
        )
        db.add(new_superadmin)
        db.flush()

        # 7. Generar codigos de rescate break-glass
        recovery_codes = generate_recovery_codes(8)
        for code in recovery_codes:
            db.add(UserRecoveryCode(
                user_id=new_superadmin.id,
                code_hash=hash_recovery_code(code),
                created_at=datetime.now(timezone.utc)
            ))

        db.commit()

        uri = get_totp_provisioning_uri(raw_secret, username)

        print("\n" + "=" * 65)
        print(" [EXITO] SUPERADMIN APROVISIONADO CORRECTAMENTE FUERA DE BANDA")
        print("=" * 65)
        print(f" Usuario:       {username}")
        print(f" Rol:           SUPERADMIN (Plataforma)")
        print(f" Tenant:        system")
        print(f" MFA Status:    ENABLED (Obligatorio)")
        print(f" Secreto Base32:{raw_secret}")
        print(f" URI OTP:       {uri}")
        print("-" * 65)
        print(" CODIGOS DE RESCATE (BREAK-GLASS) - GUARDELOS EN LUGAR SEGURO:")
        for idx, c in enumerate(recovery_codes, 1):
            print(f"  [{idx}] {c}")
        print("=" * 65 + "\n")

    finally:
        db.close()


def reset_superadmin_mfa(username: str, password: Optional[str] = None):
    """
    Permite al operador de consola reconfigurar MFA para el SUPERADMIN si se extraviaron
    las claves de rescate, exigiendo obligatoriamente la contrasena vigente (P14-R1-15).
    """
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == username, User.role == "SUPERADMIN").first()
        if not user:
            print(f"[ERROR] Cuenta SUPERADMIN '{username}' no encontrada.")
            sys.exit(1)

        if not password:
            env_pwd = os.getenv("SUPERADMIN_PASSWORD")
            if env_pwd:
                password = env_pwd
            else:
                password = getpass.getpass(f"Ingrese contrasena actual para autorizar reseteo MFA de '{username}': ")

        if not verify_password(password, user.password_hash):
            print("[ERROR] Contrasena incorrecta. Accion denegada.")
            sys.exit(1)

        # Generar nuevo secreto y codigos de rescate
        raw_secret = generate_totp_secret()
        mfa_encryption_key = getattr(settings, "MFA_ENCRYPTION_KEY", "deterministic_test_mfa_key_32b_!")
        encrypted_secret = encrypt_aead(raw_secret, mfa_encryption_key, key_id="v1")

        db.query(UserRecoveryCode).filter(UserRecoveryCode.user_id == user.id).delete()
        recovery_codes = generate_recovery_codes(8)
        for code in recovery_codes:
            db.add(UserRecoveryCode(
                user_id=user.id,
                code_hash=hash_recovery_code(code),
                created_at=datetime.now(timezone.utc)
            ))

        user.mfa_secret = encrypted_secret
        user.mfa_status = MfaStatus.ENABLED.value
        user.mfa_last_totp_step = None
        user.session_version += 1
        # Revocar todas las sesiones existentes
        db.query(UserSession).filter(UserSession.user_id == user.id).update({"is_revoked": True})
        db.commit()

        uri = get_totp_provisioning_uri(raw_secret, username)
        print("\n[EXITO] MFA reiniciado satisfactoriamente para SUPERADMIN.")
        print(f" Nuevo Secreto: {raw_secret}")
        print(f" URI OTP:       {uri}")
        print(" Nuevos Codigos de Rescate:")
        for idx, c in enumerate(recovery_codes, 1):
            print(f"  [{idx}] {c}")
    finally:
        db.close()


def unlock_account(username: str):
    """Desbloquea una cuenta bloqueada por exceso de intentos fallidos."""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == username).first()
        if not user:
            print(f"[ERROR] Usuario '{username}' no encontrado.")
            sys.exit(1)
        user.locked_until = None
        user.failed_login_count = 0
        db.commit()
        print(f"[EXITO] Cuenta '{username}' desbloqueada satisfactoriamente.")
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="ABST-GP V6 Security CLI")
    subparsers = parser.add_subparsers(dest="command")

    # Comando 1: provision-superadmin (alias init-superadmin)
    p_prov = subparsers.add_parser("provision-superadmin", help="Aprovisiona la cuenta SUPERADMIN unica fuera de banda")
    p_prov.add_argument("--username", required=True, help="Nombre de usuario del SUPERADMIN")
    p_prov.add_argument("--password", required=False, help="Contrasena (omita para ingreso interactivo seguro)")

    p_init = subparsers.add_parser("init-superadmin", help="Alias de provision-superadmin")
    p_init.add_argument("--username", required=True, help="Nombre de usuario del SUPERADMIN")
    p_init.add_argument("--password", required=False, help="Contrasena (omita para ingreso interactivo seguro)")

    # Comando 2: reset-superadmin-mfa
    p_mfa = subparsers.add_parser("reset-superadmin-mfa", help="Reinicia secreto MFA de SUPERADMIN tras validar contrasena")
    p_mfa.add_argument("--username", required=True, help="Nombre de usuario del SUPERADMIN")
    p_mfa.add_argument("--password", required=False, help="Contrasena vigente")

    # Comando 3: unlock-account
    p_unlock = subparsers.add_parser("unlock-account", help="Desbloquea una cuenta administrativa bloqueada")
    p_unlock.add_argument("--username", required=True, help="Nombre de usuario a desbloquear")

    args = parser.parse_args()

    if args.command in ("provision-superadmin", "init-superadmin"):
        provision_superadmin(args.username, args.password)
    elif args.command == "reset-superadmin-mfa":
        reset_superadmin_mfa(args.username, args.password)
    elif args.command == "unlock-account":
        unlock_account(args.username)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
