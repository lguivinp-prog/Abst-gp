import json
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.models.domain import User, Tenant, AuditLog, UserTenantQuarantine

class QuarantineServiceError(Exception):
    pass

class QuarantineAlreadyResolvedError(QuarantineServiceError):
    pass

def _validate_actor(db: Session, actor_username: str) -> User:
    actor = db.query(User).filter(User.username == actor_username).first()
    if not actor:
        raise QuarantineServiceError(f"Actor '{actor_username}' not found.")
    if not actor.is_active:
        raise QuarantineServiceError(f"Actor '{actor_username}' is not active.")
    if actor.role != 'ADMIN':
        raise QuarantineServiceError(f"Actor '{actor_username}' lacks administrative privileges.")
    return actor

def resolve_user(db: Session, username: str, tenant_id: str, resolution_reference: str, actor_username: str):
    """
    Resolve a quarantined user to a specific tenant.
    Locks in order: UserTenantQuarantine, User.
    """
    actor = _validate_actor(db, actor_username)

    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise QuarantineServiceError(f"Tenant '{tenant_id}' not found.")
        
    user_basic = db.query(User.id).filter(User.username == username).first()
    if not user_basic:
        raise QuarantineServiceError(f"User '{username}' not found.")
        
    # Lock quarantine record
    quarantine_record = db.query(UserTenantQuarantine).filter(
        UserTenantQuarantine.user_id == user_basic.id
    ).with_for_update().first()
    
    if not quarantine_record:
        raise QuarantineServiceError(f"Quarantine record for user '{username}' missing.")
        
    if quarantine_record.status == 'RESOLVED' or quarantine_record.resolved_at is not None:
         raise QuarantineAlreadyResolvedError(f"Quarantine record for user '{username}' is already resolved.")

    # Lock user for update
    user = db.query(User).filter(User.id == user_basic.id).with_for_update().first()
    if not user:
        raise QuarantineServiceError(f"User '{username}' not found.")
        
    if user.tenant_resolution_status == 'RESOLVED':
        raise QuarantineAlreadyResolvedError(f"User '{username}' is already resolved.")
        
    if user.tenant_resolution_status != 'QUARANTINED':
        raise QuarantineServiceError(f"User '{username}' is not in quarantine.")

    # Perform resolution
    user.tenant_id = tenant.id
    user.tenant_resolution_status = 'RESOLVED'
    
    quarantine_record.status = 'RESOLVED'
    quarantine_record.resolved_at = datetime.now(timezone.utc)
    quarantine_record.resolution_reference = resolution_reference
    
    # Audit log correctly assigns user_id to the human actor
    audit_log = AuditLog(
        action="QUARANTINE_RESOLVED",
        entity_type="users",
        entity_id=str(user.id),
        user_id=actor.id,
        tenant_id=tenant.id,
        details=json.dumps({
            "previous_status": "QUARANTINED",
            "new_status": "RESOLVED",
            "resolution_reference": resolution_reference
        })
    )
    db.add(audit_log)
    return user

def backfill_quarantine_users(db: Session, actor_username: str, operation_id: str, dry_run: bool = True) -> dict:
    actor = _validate_actor(db, actor_username)
    
    # Check idempotency
    existing_run = db.query(AuditLog).filter(
        AuditLog.action == "QUARANTINE_BACKFILL",
        AuditLog.entity_id == operation_id
    ).first()
    
    if existing_run:
        raise QuarantineServiceError(f"Backfill operation '{operation_id}' was already executed.")

    # Detect ambiguous users (those without tenant_id that should be quarantined)
    # Exclude those that are already in quarantine
    query = text("""
        SELECT u.id, u.username
        FROM users u
        LEFT JOIN user_tenant_quarantine utq ON u.id = utq.user_id
        WHERE u.tenant_id IS NULL AND utq.user_id IS NULL
    """)
    ambiguous_users = db.execute(query).fetchall()
    
    result = {
        "operation_id": operation_id,
        "dry_run": dry_run,
        "users_found": len(ambiguous_users),
        "quarantined_count": 0,
        "details": []
    }
    
    if dry_run:
        return result
        
    for user_row in ambiguous_users:
        user_id = user_row[0]
        # Lock user
        user = db.query(User).filter(User.id == user_id).with_for_update().first()
        if user and user.tenant_id is None and user.tenant_resolution_status != 'QUARANTINED':
            user.tenant_resolution_status = 'QUARANTINED'
            user.is_active = False
            
            quarantine = UserTenantQuarantine(
                user_id=user.id,
                reason_code="MISSING_TENANT_DURING_V4_BACKFILL",
                status="QUARANTINED"
            )
            db.add(quarantine)
            result["quarantined_count"] += 1
            result["details"].append({"user_id": user_id, "username": user_row[1]})
            
    # Audit log
    audit_log = AuditLog(
        action="QUARANTINE_BACKFILL",
        entity_type="system",
        entity_id=operation_id,
        user_id=actor.id,
        tenant_id=None,
        details=json.dumps({
            "users_quarantined": result["quarantined_count"],
            "operation_id": operation_id
        })
    )
    db.add(audit_log)
    
    return result
