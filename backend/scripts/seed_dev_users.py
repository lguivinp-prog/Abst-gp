import sys
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.models.domain import User
from app.api.auth import get_password_hash

def seed_users():
    print("Starting development users seed...")
    db_url = settings.DATABASE_URL
    if not db_url:
        print("Error: DATABASE_URL not set in environment.")
        sys.exit(1)

    engine = create_engine(db_url)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()

    default_password = "Operator123!"

    try:
        users_to_seed = [
            {"username": "admin", "role": "ADMIN", "tenant_id": "mega_tenant"},
            {"username": "operator", "role": "OPERATOR", "tenant_id": "mega_tenant"}
        ]

        for u in users_to_seed:
            existing = db.query(User).filter_by(username=u["username"]).first()
            if existing:
                existing.password_hash = get_password_hash(default_password)
                existing.must_change_password = False
                existing.role = u["role"]
                existing.tenant_id = u["tenant_id"]
                existing.tenant_resolution_status = "RESOLVED"
                print(f"User '{u['username']}' updated with valid bcrypt hash.")
            else:
                new_user = User(
                    username=u["username"],
                    password_hash=get_password_hash(default_password),
                    role=u["role"],
                    is_active=True,
                    tenant_id=u["tenant_id"],
                    tenant_resolution_status="RESOLVED",
                    must_change_password=False
                )
                db.add(new_user)
                print(f"User '{u['username']}' created.")

        db.commit()
        print(f"Seed completed successfully. You can now login with password: {default_password}")

    except Exception as e:
        db.rollback()
        print(f"Error seeding users: {e}")
        sys.exit(1)
    finally:
        db.close()

if __name__ == "__main__":
    seed_users()
