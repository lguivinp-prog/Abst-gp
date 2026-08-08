import sys
import os
import argparse
import getpass

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.models.domain import User, BootstrapLedger
from app.api.auth import get_password_hash
from app.core.env_guard import validate_migration_environment, EnvGuardError
import hashlib

def create_admin(password_file: str = None, operation_id: str = "bootstrap"):
    db_url = settings.DATABASE_URL
    app_env = os.environ.get("APP_ENV", "production")
    
    # 6. abst_gp siempre rechazado en entornos no compatibles
    try:
        validate_migration_environment(app_env, db_url, dict(os.environ))
    except EnvGuardError as e:
        print(f"EnvironmentGuard Error: {e}")
        sys.exit(1)

    password = None
    if password_file:
        # 4. --password-file con controles POSIX seguros
        if os.name == 'posix':
            try:
                st = os.stat(password_file)
                if (st.st_mode & 0o777) != 0o600:
                    print(f"Error: Password file {password_file} must have 0600 permissions.")
                    sys.exit(1)
            except OSError as e:
                print(f"Error accessing password file: {e}")
                sys.exit(1)
        
        try:
            with open(password_file, 'r') as f:
                password = f.read().strip()
        except Exception as e:
            print(f"Error reading password file: {e}")
            sys.exit(1)
    else:
        # 5. Modo interactivo únicamente con TTY real
        if not sys.stdin.isatty():
            print("Error: Interactive mode requires a real TTY. Use --password-file for automated scripts.")
            sys.exit(1)
        password = getpass.getpass("Enter new ADMIN password: ")
        if not password:
            print("Error: Password cannot be empty.")
            sys.exit(1)

    # 1. Política de contraseñas centralizada (at least min length 8 here or caught by schema/hash logic)
    if len(password) < 8:
        print("Error: Password must be at least 8 characters long.")
        sys.exit(1)
        
    if len(password.encode('utf-8')) > 72:
        print("Error: Password exceeds maximum length of 72 bytes.")
        sys.exit(1)

    payload_hash = hashlib.sha256(password.encode('utf-8')).hexdigest()

    engine = create_engine(db_url)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()

    try:
        # 7. Advisory lock global constante, independiente del tenant
        lock_id = 99991234
        # Acquire transaction-level advisory lock
        db.execute(text(f"SELECT pg_advisory_xact_lock({lock_id})"))
        
        # 9. Ledger idempotente
        ledger_entry = db.query(BootstrapLedger).filter_by(operation_id=operation_id).first()
        if ledger_entry:
            if ledger_entry.payload_hash == payload_hash:
                print("SUCCESS + IDEMPOTENT")
                return
            else:
                print("SUCCESS + CONFLICT")
                sys.exit(1)

        existing_admin = db.query(User).filter(User.role == "ADMIN").first()
        if existing_admin:
            print("SUCCESS + ADMIN_ALREADY_EXISTS")
            return

        hashed = get_password_hash(password)
        
        admin_user = User(
            username="bootstrap_admin",
            password_hash=hashed,
            role="ADMIN",
            is_active=True,
            must_change_password=True,
            tenant_id="mega_tenant",
            tenant_resolution_status="RESOLVED"
        )
        db.add(admin_user)
        
        new_ledger = BootstrapLedger(
            operation_id=operation_id,
            payload_hash=payload_hash
        )
        db.add(new_ledger)
        
        db.commit()
        print("SUCCESS")
    except ValueError as e:
        db.rollback()
        print(f"Error: {e}")
        sys.exit(1)
    except Exception as e:
        db.rollback()
        print(f"Error: {e}")
        sys.exit(1)
    finally:
        db.close()

def main():
    parser = argparse.ArgumentParser(prog="admin_bootstrap", description="Bootstrap initial ADMIN user")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    create_parser = subparsers.add_parser("create")
    create_parser.add_argument("--password-file", type=str, help="Path to password file", default=None)
    create_parser.add_argument("--operation-id", type=str, help="Operation ID for idempotency", default="bootstrap")
    
    args = parser.parse_args()
    
    if args.command == "create":
        create_admin(args.password_file, args.operation_id)

if __name__ == "__main__":
    main()
