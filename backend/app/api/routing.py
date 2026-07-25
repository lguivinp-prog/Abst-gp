from datetime import datetime, timezone
import json
from sqlalchemy.orm import Session
from app.core.redis import redis_conn
from app.models.domain import RolloutTenantAssignment, SystemSettings
import logging

logger = logging.getLogger(__name__)

CACHE_TTL = 300  # 5 minutes

class TenantRouter:
    @staticmethod
    def get_tenant_routing(tenant_id: str, db: Session) -> dict:
        """
        Retrieves the routing assignment for a tenant.
        Caches raw RolloutTenantAssignment. Resolves engine dynamically with SystemSettings.
        """
        cache_key = f"tenant_assignment:{tenant_id}"
        assignment_data = None
        
        try:
            cached_val = redis_conn.get(cache_key)
            if cached_val:
                assignment_data = json.loads(cached_val)
        except Exception as e:
            logger.warning(f"Redis cache failed for {tenant_id}: {e}")
            
        if not assignment_data:
            assignment = db.query(RolloutTenantAssignment).filter(
                RolloutTenantAssignment.tenant_id == tenant_id
            ).first()
            
            if assignment:
                assignment_data = {
                    "routing_mode": assignment.routing_mode,
                    "assigned_ring": assignment.assigned_ring,
                    "override_until": assignment.override_until.isoformat() if assignment.override_until else None
                }
                
                # Calculate TTL
                ttl = CACHE_TTL
                if assignment.override_until:
                    now = datetime.now(timezone.utc)
                    if assignment.override_until > now:
                        remaining = int((assignment.override_until - now).total_seconds())
                        ttl = min(CACHE_TTL, remaining)
                    else:
                        ttl = CACHE_TTL
                
                try:
                    redis_conn.setex(cache_key, ttl, json.dumps(assignment_data))
                except Exception as e:
                    logger.warning(f"Redis set failed for {tenant_id}: {e}")
            else:
                assignment_data = {
                    "routing_mode": "FORCE_LEGACY",
                    "assigned_ring": None,
                    "override_until": None
                }
        
        # Get active_ring (could be cached globally, but querying DB for now)
        sys_settings = db.query(SystemSettings).first()
        active_ring = sys_settings.active_ring if sys_settings else 0
        
        route_info = {
            "tenant_id": tenant_id,
            "routing_mode": assignment_data["routing_mode"],
            "assigned_ring": assignment_data["assigned_ring"],
            "engine": "v1"
        }
        
        override_dt = datetime.fromisoformat(assignment_data["override_until"]) if assignment_data["override_until"] else None
        
        if override_dt and override_dt > datetime.now(timezone.utc):
            route_info["engine"] = "v2" if route_info["routing_mode"] == "FORCE_V2" else "v1"
        else:
            if route_info["routing_mode"] == "FORCE_V2":
                route_info["engine"] = "v2"
            elif route_info["routing_mode"] == "FORCE_LEGACY":
                route_info["engine"] = "v1"
            else: # AUTO
                ring = route_info["assigned_ring"]
                if ring is None or ring <= 0:
                    route_info["engine"] = "v1"
                elif 1 <= ring <= active_ring:
                    route_info["engine"] = "v2"
                else:
                    route_info["engine"] = "v1"
                    
        return route_info

    @staticmethod
    def invalidate_cache(tenant_id: str):
        try:
            redis_conn.delete(f"tenant_assignment:{tenant_id}")
        except Exception as e:
            logger.warning(f"Redis invalidation failed for {tenant_id}: {e}")
