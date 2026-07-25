from sqlalchemy import create_engine, text
import os
import uuid

db_url = os.environ.get("DATABASE_URL")
engine = create_engine(db_url)
with engine.begin() as conn:
    users = []
    for i in range(1500):
        if i < 500:
            username = f"ambiguous_user_{uuid.uuid4()}"
        else:
            username = f"normal_user_{uuid.uuid4()}"
            
        users.append({
            "username": username,
            "password_hash": "hash123",
            "role": "readonly",
            "is_active": True,
            "must_change_password": False
        })
        
    conn.execute(text("INSERT INTO users (username, password_hash, role, is_active, must_change_password, tenant_id) VALUES (:username, :password_hash, :role, :is_active, :must_change_password, NULL)"), users)
    print("Inserted 1500 users")
