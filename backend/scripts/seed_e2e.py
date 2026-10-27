import sys
import os

# FAIL-CLOSED SAFETY GUARD (Must run before any DB operation)
if os.environ.get("ALLOW_E2E_SEED") != "true":
    print("ABORT: E2E seed cannot run without ALLOW_E2E_SEED=true explicit opt-in.")
    sys.exit(1)

if os.environ.get("APP_ENV") != "test":
    print("ABORT: E2E seed can only run in APP_ENV=test.")
    sys.exit(1)

# Import sqlalchemy specifically for the guard
try:
    from sqlalchemy.engine import make_url
except ImportError:
    print("ABORT: Failed to import sqlalchemy. Cannot verify database URL safety.")
    sys.exit(1)

db_url_str = os.environ.get("DATABASE_URL")
if not db_url_str:
    print("ABORT: DATABASE_URL is not set.")
    sys.exit(1)

try:
    url = make_url(db_url_str)
    if url.host != "db-test" or url.database != "test_db":
        print("ABORT: E2E seed can only run against a test database (host=db-test, database=test_db).")
        sys.exit(1)
except Exception as e:
    print(f"ABORT: Invalid DATABASE_URL format. {e}")
    sys.exit(1)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.models.domain import User, Tenant
from app.api.auth import get_password_hash
from app.core.crypto import encrypt_aead


def run_e2e_seed():
    engine = create_engine(settings.DATABASE_URL)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()

    try:
        # Asegurar tenant base
        tenant = db.query(Tenant).filter_by(id="mega_tenant").first()
        if not tenant:
            tenant = Tenant(id="mega_tenant", name="Mega Tenant", can_manage_users=True)
            db.add(tenant)
            db.commit()

        # 1. Usuario admin con contrasena adminpassword para E2E general
        admin_user = db.query(User).filter_by(username="admin").first()
        hashed = get_password_hash("adminpassword")
        if not admin_user:
            admin_user = User(
                username="admin",
                password_hash=hashed,
                role="ADMIN",
                is_active=True,
                tenant_id="mega_tenant",
                tenant_resolution_status="RESOLVED",
                must_change_password=False,
                session_version=1
            )
            db.add(admin_user)
            db.commit()
            print("E2E User 'admin' created.")
        else:
            admin_user.password_hash = hashed
            admin_user.failed_login_count = 0
            admin_user.locked_until = None
            admin_user.is_active = True
            admin_user.session_version = 1
            db.commit()
            print("E2E User 'admin' already exists. Password hash updated and account unlocked.")

        # 2. Usuario p14_mfa_operator con MFA TOTP para pruebas de autenticacion de 2 factores (P14 R2-02, R2-17)
        mfa_user = db.query(User).filter_by(username="p14_mfa_operator").first()
        mfa_hashed = get_password_hash("MfaOperatorPass123!")
        totp_secret = "JBSWY3DPEHPK3PXP"
        mfa_key = getattr(settings, "MFA_ENCRYPTION_KEY", "deterministic_test_mfa_key_32b_!")
        enc_secret = encrypt_aead(totp_secret, mfa_key, key_id="v1")

        if not mfa_user:
            mfa_user = User(
                username="p14_mfa_operator",
                password_hash=mfa_hashed,
                role="OPERATOR",
                is_active=True,
                tenant_id="mega_tenant",
                tenant_resolution_status="RESOLVED",
                must_change_password=False,
                mfa_status="ENABLED",
                mfa_secret=enc_secret,
                session_version=1
            )
            db.add(mfa_user)
            db.commit()
            print("E2E User 'p14_mfa_operator' created.")
        else:
            mfa_user.password_hash = mfa_hashed
            mfa_user.role = "OPERATOR"
            mfa_user.mfa_status = "ENABLED"
            mfa_user.mfa_secret = enc_secret
            mfa_user.failed_login_count = 0
            mfa_user.locked_until = None
            mfa_user.is_active = True
            mfa_user.session_version = 1
            db.commit()
            print("E2E User 'p14_mfa_operator' updated.")

    except Exception as e:
        db.rollback()
        print(f"Error durante el E2E seed: {e}")
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    run_e2e_seed()
