from sqlalchemy import create_engine, text
import os
import uuid

db_url = os.environ.get("DATABASE_URL")
engine = create_engine(db_url)
with engine.begin() as conn:
    conn.execute(text("ALTER TABLE users DROP CONSTRAINT IF EXISTS chk_users_tenant_resolution"))
    conn.execute(text("ALTER TABLE users DROP COLUMN IF EXISTS tenant_resolution_status"))
    conn.execute(text("ALTER TABLE users DROP COLUMN IF EXISTS quarantined_at"))
    conn.execute(text("DROP TABLE IF EXISTS user_tenant_quarantine CASCADE"))
    conn.execute(text("UPDATE alembic_version SET version_num = 'e0bb13aab365'"))
    print("Cleaned up back to e0bb13aab365")
