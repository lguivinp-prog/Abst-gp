import argparse
import sys
import os
import json
import hashlib
from datetime import datetime, timezone
from sqlalchemy import create_engine, text
from quarantine_logic import classify_user_tenant

import argparse
import sys
import os
import json
import hashlib
from datetime import datetime, timezone
from sqlalchemy import create_engine, text
from quarantine_logic import classify_user_tenant

def generate_manifest(db_url: str, output_file: str):
    engine = create_engine(db_url)
    
    with engine.connect().execution_options(isolation_level="REPEATABLE READ") as conn:
        with conn.begin():
            conn.execute(text("SET TRANSACTION READ ONLY"))
            print("--- Transaction established: REPEATABLE READ, READ ONLY ---")
            for row in conn.execute(text("SHOW transaction_isolation;")):
                print(f"transaction_isolation: {row[0]}")
            for row in conn.execute(text("SHOW transaction_read_only;")):
                print(f"transaction_read_only: {row[0]}")
                
            alembic_head_row = conn.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).fetchone()
            alembic_head = alembic_head_row[0] if alembic_head_row else "UNKNOWN"
            
            # Fetch authoritative fields used in classification
            users = conn.execute(text("SELECT id, username, tenant_id, tenant_resolution_status, is_active FROM users ORDER BY id")).fetchall()
            
            assignments = []
            quarantines = []
            
            fingerprint_items = []
            
            for u in users:
                # Include all users in fingerprint for absolute state hashing, or just NULL tenant_id users.
                # "El fingerprint debe incluir: user_id, tenant_id, tenant_resolution_status, is_active... toda columna realmente usada"
                t_id = u.tenant_id if u.tenant_id is not None else None
                t_res = u.tenant_resolution_status if u.tenant_resolution_status is not None else None
                
                # Canonical representation for the fingerprint
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
                        assignments.append({
                            "action": "ASSIGN",
                            "id": u.id,
                            "reason_code": classification.get("reason_code"),
                            "tenant_id": classification["tenant_id"]
                        })
                    elif classification["action"] == "QUARANTINE":
                        quarantines.append({
                            "action": "QUARANTINE",
                            "id": u.id,
                            "reason_code": classification.get("reason_code")
                        })
            
            # Stable sort for canonical JSON
            fingerprint_items.sort(key=lambda x: x["id"])
            assignments.sort(key=lambda x: x["id"])
            quarantines.sort(key=lambda x: x["id"])
            
            manifest = {
                "alembic_revision": alembic_head,
                "assignments": assignments,
                "assignments_count": len(assignments),
                "classifier_version": "v1.0",
                "fingerprint": fingerprint_items,
                "fixture_identity": "production_snapshot_20260721",
                "manifest_schema_version": "1.0",
                "quarantines": quarantines,
                "quarantines_count": len(quarantines),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
            # Generate canonical JSON strictly: utf-8, no NaN, separated by commas without spaces
            manifest_json = json.dumps(
                manifest, 
                ensure_ascii=False, 
                allow_nan=False, 
                sort_keys=True, 
                separators=(',', ':')
            ).encode('utf-8')
            
            manifest_hash = hashlib.sha256(manifest_json).hexdigest()
            
            with open(output_file, "wb") as f:
                f.write(manifest_json)
                
            with open(output_file + ".sha256", "w") as f:
                f.write(manifest_hash)
                
            print(f"Manifest generated at {output_file}")
            print(f"To Assign: {len(assignments)}")
            print(f"To Quarantine: {len(quarantines)}")
            print(f"Manifest SHA-256 (detached): {manifest_hash}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate deterministic backfill manifest")
    parser.add_argument("--out", required=True, help="Output manifest JSON file")
    args = parser.parse_args()
    
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("DATABASE_URL env var required.")
        sys.exit(1)
        
    generate_manifest(db_url, args.out)
