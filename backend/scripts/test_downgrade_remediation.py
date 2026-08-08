import os
import sys
from sqlalchemy import create_engine, text

db_url = "postgresql://test_user:test_password@localhost:15432/v49_remediation_db"
engine = create_engine(db_url)

def setup_users(count):
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM users WHERE role = 'ADMIN'"))
        for i in range(count):
            conn.execute(text(f"""
                INSERT INTO users (username, password_hash, role, is_active, tenant_id, tenant_resolution_status)
                VALUES ('admin_{i}', 'hash', 'ADMIN', true, 'mega_tenant', 'RESOLVED')
            """))

if __name__ == '__main__':
    command = sys.argv[1]
    if command == "setup_1":
        setup_users(1)
    elif command == "setup_2":
        setup_users(2)
