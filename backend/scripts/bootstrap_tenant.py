import sys
import os
import argparse
import getpass
from datetime import datetime, timezone

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def check_index_status(session, index_name):
    sql = text("""
        SELECT 
            i.indisvalid, 
            i.indisready, 
            i.indisunique,
            pg_get_expr(i.indpred, i.indrelid) as predicate, 
            pg_get_indexdef(i.indexrelid) as indexdef,
            t.relname as table_name,
            n.nspname as schema_name,
            (
                SELECT string_agg(a.attname, ', ')
                FROM unnest(i.indkey) WITH ORDINALITY AS k(attnum, ord)
                JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = k.attnum
            ) as indexed_columns
        FROM pg_class c
        JOIN pg_index i ON c.oid = i.indexrelid
        JOIN pg_class t ON t.oid = i.indrelid
        JOIN pg_namespace n ON t.relnamespace = n.oid
        WHERE c.relname = :idx_name AND n.nspname = 'public'
    """)
    res = session.execute(sql, {"idx_name": index_name}).fetchone()
    if not res:
        return None
    valid, ready, is_unique, predicate, indexdef, table_name, schema_name, indexed_columns = res
    return {
        "valid": valid,
        "ready": ready,
        "is_unique": is_unique,
        "predicate": predicate,
        "indexdef": indexdef,
        "table_name": table_name,
        "schema_name": schema_name,
        "indexed_columns": indexed_columns
    }

def bootstrap_tenant(db_url: str, tenant_id: str, tenant_name: str, admin_username: str):
    engine = create_engine(db_url)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    with SessionLocal() as session:
        try:
            lock_id = hash(tenant_id) & 0x7FFFFFFF
            session.execute(text("SELECT pg_advisory_xact_lock(:lock_id)"), {"lock_id": lock_id})
            
            print(f"Acquired lock for tenant '{tenant_id}'. Checking state...")
            
            # Introspección de índices
            singleton = check_index_status(session, "ix_users_admin_singleton")
            tenant_idx = check_index_status(session, "ix_users_admin_tenant")
            
            is_expand_phase = singleton and singleton["valid"] and singleton["ready"]
            
            if is_expand_phase:
                if tenant_id != 'mega_tenant':
                    print(f"Bootstrap is blocked for new tenants while ix_users_admin_singleton exists. Execute Contract migration first.")
                    session.rollback()
                    return
                # Si es mega_tenant en fase Expand, revisar ADMIN legacy sin tenant_id
                legacy_admin = session.execute(text("SELECT id FROM users WHERE role = 'ADMIN' AND tenant_id IS NULL")).fetchone()
                if legacy_admin:
                    print("Legacy ADMIN (tenant_id IS NULL) detected. Backfill required. Aborting.")
                    session.rollback()
                    return
                # Revisar si hay un ADMIN para mega_tenant ya migrado
                existing_mega_admin = session.execute(text("SELECT id FROM users WHERE role = 'ADMIN' AND tenant_id = 'mega_tenant'")).fetchone()
                if existing_mega_admin:
                    print("Mega-Tenant ADMIN already initialized. No-op successful.")
                    session.rollback()
                    return
            else:
                # Post-contract: ix_users_admin_tenant should exist and singleton should not
                if not tenant_idx or not tenant_idx["valid"] or not tenant_idx["ready"]:
                    print("ix_users_admin_tenant is missing or invalid. Check migrations.")
                    session.rollback()
                    return
                if (tenant_idx["table_name"] != "users" or 
                    tenant_idx["schema_name"] != "public" or 
                    not tenant_idx["is_unique"] or 
                    "role = 'ADMIN'" not in (tenant_idx["predicate"] or "").replace("::text", "") or 
                    tenant_idx["indexed_columns"] != "tenant_id"):
                    print(f"Index ix_users_admin_tenant does not meet structural requirements: {tenant_idx}")
                    session.rollback()
                    return
                    
                existing_admin = session.execute(text("SELECT id FROM users WHERE tenant_id = :t AND role = 'ADMIN'"), {"t": tenant_id}).fetchone()
                if existing_admin:
                    print(f"ADMIN for tenant '{tenant_id}' already initialized. No-op successful.")
                    session.rollback()
                    return

            tenant_exists = session.execute(text("SELECT 1 FROM tenants WHERE id = :id"), {"id": tenant_id}).scalar()
            if not tenant_exists:
                session.execute(
                    text("INSERT INTO tenants (id, name, created_at) VALUES (:id, :name, :created_at)"),
                    {"id": tenant_id, "name": tenant_name, "created_at": datetime.now(timezone.utc)}
                )

            rollout_state = session.execute(text("SELECT routing_mode FROM rollout_tenant_assignments WHERE tenant_id = :t"), {"t": tenant_id}).fetchone()
            if not rollout_state:
                session.execute(
                    text("INSERT INTO rollout_tenant_assignments (tenant_id, routing_mode, assignment_version, assigned_at) VALUES (:t, 'FORCE_LEGACY', 'v1', :at)"),
                    {"t": tenant_id, "at": datetime.now(timezone.utc)}
                )
            elif rollout_state[0] != 'FORCE_LEGACY':
                print("Assignment mode incompatible with bootstrap defaults. Aborting.")
                session.rollback()
                return

            existing_user = session.execute(text("SELECT id FROM users WHERE username = :u"), {"u": admin_username}).fetchone()
            if existing_user:
                print(f"Username '{admin_username}' globally taken. Aborting.")
                session.rollback()
                return

            password = getpass.getpass(prompt=f"Enter password for new ADMIN '{admin_username}': ")
            confirm = getpass.getpass(prompt="Confirm password: ")
            if password != confirm or len(password) < 8:
                print("Invalid password. Aborting.")
                session.rollback()
                return

            pwd_hash = get_password_hash(password)
            user_id = session.execute(
                text("INSERT INTO users (username, password_hash, role, is_active, must_change_password, tenant_id) VALUES (:u, :p, 'ADMIN', true, true, :t) RETURNING id"),
                {"u": admin_username, "p": pwd_hash, "t": tenant_id}
            ).scalar()

            session.execute(
                text("INSERT INTO audit_logs (user_id, action, entity_type, entity_id, status, details, tenant_id) VALUES (:u, 'CREATE', 'USER', :e, 'SUCCESS', 'Bootstrapped first ADMIN', :t)"),
                {"u": user_id, "e": str(user_id), "t": tenant_id}
            )

            session.commit()
            print("Bootstrap completed successfully.")

        except Exception as e:
            session.rollback()
            print(f"Error during bootstrap: {str(e)}")
            sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--tenant-name", required=True)
    parser.add_argument("--admin-username", required=True)
    args = parser.parse_args()
    
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("DATABASE_URL env var required.")
        sys.exit(1)
        
    bootstrap_tenant(db_url, args.tenant_id, args.tenant_name, args.admin_username)
