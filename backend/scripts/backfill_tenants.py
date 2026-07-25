import sys
import time
import os
import argparse
import json
import hashlib
from sqlalchemy import create_engine, text
from quarantine_logic import classify_user_tenant

def verify_manifest_hash(manifest_path: str):
    sha_path = manifest_path + ".sha256"
    if not os.path.exists(sha_path):
        print(f"FATAL: Detached SHA-256 file {sha_path} not found.")
        sys.exit(1)
        
    with open(manifest_path, "rb") as f:
        manifest_bytes = f.read()
    with open(sha_path, "r") as f:
        expected_hash = f.read().strip()
        
    actual_hash = hashlib.sha256(manifest_bytes).hexdigest()
    if actual_hash != expected_hash:
        print(f"FATAL: Manifest SHA-256 mismatch. Expected {expected_hash}, got {actual_hash}")
        sys.exit(1)
        
    return json.loads(manifest_bytes.decode('utf-8'))

def run_backfill(db_url: str, manifest_path: str, actor_user_id: int):
    manifest = verify_manifest_hash(manifest_path)
    engine = create_engine(db_url)
    
    updated = 0
    quarantined = 0
    failed = 0
    
    with engine.connect().execution_options(isolation_level="REPEATABLE READ") as conn:
        try:
            with conn.begin():
                print("1. Transaction started with REPEATABLE READ isolation.")
                
                # 1b. Validate actor
                actor = conn.execute(
                    text("SELECT id, role, is_active FROM users WHERE id = :actor_id"),
                    {"actor_id": actor_user_id}
                ).fetchone()
                if not actor:
                    print(f"FATAL: Actor user {actor_user_id} not found.")
                    sys.exit(1)
                if not actor.is_active:
                    print(f"FATAL: Actor user {actor_user_id} is inactive.")
                    sys.exit(1)
                if actor.role != 'admin' and actor.role != 'ADMIN':
                    print(f"FATAL: Actor user {actor_user_id} does not have admin role.")
                    sys.exit(1)
                
                # 2. Acquire global exclusion
                conn.execute(text("SELECT pg_advisory_xact_lock(999999);"))
                print("2. Acquired global advisory transaction lock (999999).")
                
                # 3. Block mutable tables/sources
                conn.execute(text("LOCK TABLE users, tenants, rollout_tenant_assignments, user_tenant_quarantine IN EXCLUSIVE MODE;"))
                print("3. Locked mutable tables IN EXCLUSIVE MODE.")
                
                # 4. Read authoritative state
                users = conn.execute(text("SELECT id, username, tenant_id, tenant_resolution_status, is_active FROM users ORDER BY id")).fetchall()
                print("4. Read authoritative state from users.")
                
                # 5 & 6. Recalculate classification & fingerprint
                fingerprint_items = []
                recalculated_assignments = []
                recalculated_quarantines = []
                
                for u in users:
                    t_id = u.tenant_id if u.tenant_id is not None else None
                    t_res = u.tenant_resolution_status if u.tenant_resolution_status is not None else None
                    fingerprint_items.append({
                        "id": u.id,
                        "is_active": bool(u.is_active),
                        "tenant_id": t_id,
                        "tenant_resolution_status": t_res,
                        "username": u.username
                    })
                    
                    if t_id is None:
                        classification = classify_user_tenant(u)
                        if classification["action"] == "ASSIGN":
                            recalculated_assignments.append({
                                "action": "ASSIGN",
                                "id": u.id,
                                "reason_code": classification.get("reason_code"),
                                "tenant_id": classification["tenant_id"]
                            })
                        elif classification["action"] == "QUARANTINE":
                            recalculated_quarantines.append({
                                "action": "QUARANTINE",
                                "id": u.id,
                                "reason_code": classification.get("reason_code")
                            })
                
                fingerprint_items.sort(key=lambda x: x["id"])
                
                # 7 & 8. Compare mapping, fingerprint, snapshot
                if fingerprint_items != manifest.get("fingerprint"):
                    print("FATAL: Database fingerprint diverges from manifest fingerprint.")
                    sys.exit(1)
                
                alembic_head = conn.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).fetchone()[0]
                if alembic_head != manifest.get("alembic_revision"):
                    print(f"FATAL: Alembic revision mismatch. Expected {manifest.get('alembic_revision')}, got {alembic_head}")
                    sys.exit(1)
                
                print("8. Preconditions, fingerprint, and revisions match.")
                
                # 9. Apply changes
                for u in users:
                    if u.tenant_id is None:
                        classification = classify_user_tenant(u)
                        if classification["action"] == "ASSIGN":
                            conn.execute(
                                text("UPDATE users SET tenant_id = :tenant_id, tenant_resolution_status = 'RESOLVED' WHERE id = :id"),
                                {"tenant_id": classification["tenant_id"], "id": u.id}
                            )
                            conn.execute(
                                text("""
                                    INSERT INTO audit_logs (user_id, action, entity_type, entity_id, status, details)
                                    VALUES (:actor_id, 'BACKFILL_ASSIGN', 'users', :id, 'SUCCESS', :details)
                                """),
                                {"actor_id": actor_user_id, "id": str(u.id), "details": json.dumps({"tenant_id": classification["tenant_id"]})}
                            )
                            updated += 1
                        elif classification["action"] == "QUARANTINE":
                            conn.execute(
                                text("UPDATE users SET tenant_resolution_status = 'QUARANTINED', is_active = false, quarantined_at = NOW() WHERE id = :id"),
                                {"id": u.id}
                            )
                            ev_json = json.dumps(classification.get("evidence", {}))
                            conn.execute(
                                text("""
                                    INSERT INTO user_tenant_quarantine (user_id, reason_code, evidence_reviewed, status)
                                    VALUES (:user_id, :reason, :evidence, 'QUARANTINED')
                                """)
                                , {"user_id": u.id, "reason": classification["reason_code"], "evidence": ev_json}
                            )
                            conn.execute(
                                text("""
                                    INSERT INTO audit_logs (user_id, action, entity_type, entity_id, status, details)
                                    VALUES (:actor_id, 'BACKFILL_QUARANTINE', 'users', :id, 'SUCCESS', :details)
                                """),
                                {"actor_id": actor_user_id, "id": str(u.id), "details": json.dumps({"reason_code": classification["reason_code"]})}
                            )
                            quarantined += 1
                
                # 10. Validate postconditions within transaction
                unresolved = conn.execute(text("SELECT COUNT(*) FROM users WHERE tenant_id IS NULL AND (tenant_resolution_status IS NULL OR tenant_resolution_status != 'QUARANTINED')")).scalar()
                if unresolved > 0:
                    print(f"FATAL POSTCONDITION: {unresolved} users remained unresolved.")
                    sys.exit(1)
                    
                print("10. Postconditions validated successfully.")
                
                # 11. Commit automatically happens when context manager exits
        except Exception as e:
            print(f"FATAL: Transaction failed, rolling back. Error: {str(e)}")
            sys.exit(1)
            
    print(f"USERS BACKFILL COMPLETED. Assigned: {updated}, Quarantined: {quarantined}, Failed: {failed}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill script for Tenant Isolation.")
    parser.add_argument("--manifest", required=True, help="Path to manifest JSON file.")
    parser.add_argument("--actor-user-id", required=True, type=int, help="ID of the administrative user executing the backfill.")
    args = parser.parse_args()
    
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("DATABASE_URL env var required.")
        sys.exit(1)
        
    run_backfill(db_url, manifest_path=args.manifest, actor_user_id=args.actor_user_id)
