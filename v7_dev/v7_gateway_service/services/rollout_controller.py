import hashlib
from datetime import datetime
from services.migration_control import EngineState
from services.capacity_guard import capacity_guard, CapacityState
from services.tenant_capacity import tenant_capacity_service

class TenantRolloutAssignment:
    def __init__(self, tenant_id: str, wave: int, engine_state: EngineState, status: str, approved_by: str = "auto", rollback_reason: str = None, weight: float = 1.0):
        self.tenant_id = tenant_id
        self.wave = wave
        self.engine_state = engine_state
        self.status = status # PENDING, MIGRATING, ACTIVE_V7, ROLLED_BACK, EXCLUDED
        self.approved_by = approved_by
        self.created_at = datetime.utcnow()
        self.rollback_reason = rollback_reason
        self.weight = weight

class RolloutController:
    def __init__(self):
        self.current_wave = 0
        self.wave_percentages = {1: 0, 2: 10, 3: 30, 4: 60, 5: 100}
        self.tenant_registry = {}
        self.global_rollback = False
        self.is_paused = False
        
        # Telemetry variables for Universal Gate and Dashboard
        self.active_isolation_violations = 0
        self.faiss_stale = False
        self.slo_p95_ok = True
        self.celery_backlog = False
        self.cost_within_budget = True

    def validate_universal_gate(self, target_wave: int):
        print(f"[AUDIT] UNIVERSAL_GATE_CHECK: Wave {target_wave}")
        if capacity_guard.get_state() in [CapacityState.CRITICAL, CapacityState.WARNING]:
            return False, "CapacityGuard is not HEALTHY"
            
        sim = self.simulate_wave(target_wave)
        if sim["status"] != "SAFE":
            return False, "simulate_wave() is not SAFE"
            
        if self.active_isolation_violations > 0:
            return False, "Tenant isolation violations detected"
            
        if self.faiss_stale:
            return False, "FAISS fallback is stale/out-of-sync"
            
        if self.celery_backlog:
            return False, "Celery/Redis backlog is critical"
            
        if not self.slo_p95_ok:
            return False, "SLO P95/P99 violated"
            
        if not self.cost_within_budget:
            return False, "Cost projection exceeds budget"
            
        print(f"[AUDIT] UNIVERSAL_GATE_PASSED: Wave {target_wave}")
        return True, "SAFE"

    def simulate_wave(self, target_wave: int):
        print(f"[AUDIT] WAVE_SIMULATION_RUN: Target Wave {target_wave}")
        if target_wave not in self.wave_percentages:
            return {"status": "UNSAFE", "reason": "Invalid wave"}
            
        percentage = self.wave_percentages[target_wave]
        total_projected_load = 0.0
        
        tenants = tenant_capacity_service.registry.list_active_tenants()
        for t in tenants:
            if self._hash_tenant(t) < percentage:
                total_projected_load += tenant_capacity_service.get_tenant_score(t)
                
        safe_capacity = capacity_guard.total_capacity_available * 0.50
        warning_capacity = capacity_guard.total_capacity_available * 0.75
        
        if total_projected_load > warning_capacity:
            return {"status": "UNSAFE", "forecasted_load": total_projected_load, "safe_limit": safe_capacity}
        elif total_projected_load > safe_capacity:
            return {"status": "WARNING", "forecasted_load": total_projected_load, "safe_limit": safe_capacity}
        return {"status": "SAFE", "forecasted_load": total_projected_load, "safe_limit": safe_capacity}

    def set_wave(self, wave_number: int):
        passed, reason = self.validate_universal_gate(wave_number)
        if not passed:
            print(f"[AUDIT] ROLLOUT_BLOCKED: Universal Gate failed - {reason}")
            return False
            
        print(f"[AUDIT] WAVE_APPROVED: Wave {wave_number}")
        print(f"[AUDIT] ROLL_OUT_STARTED: Wave {wave_number}")
        self.current_wave = wave_number
        self.global_rollback = False
        self.is_paused = False
        return True

    def assign_tenant(self, tenant_id: str, wave: int, engine_state: EngineState, status: str = "ACTIVE_V7"):
        cap_state = capacity_guard.get_state()
        weight = tenant_capacity_service.get_tenant_score(tenant_id)
        
        if status in ["MIGRATING", "ACTIVE_V7"]:
            if cap_state in [CapacityState.CRITICAL, CapacityState.WARNING] or self.is_paused:
                print(f"[AUDIT] ROLLOUT_BLOCKED: Tenant {tenant_id} blocked due to capacity/pause")
                return False
                
            if not capacity_guard.check_capacity(weight):
                print(f"[AUDIT] CAPACITY_WARNING: Tenant {tenant_id} is too large for current available capacity")
                return False

        print(f"[AUDIT] TENANT_ASSIGNED: {tenant_id} to {engine_state.value}")
        if status == "MIGRATING":
            print(f"[AUDIT] TENANT_MIGRATION_STARTED: {tenant_id}")
        elif status == "ACTIVE_V7":
            print(f"[AUDIT] TENANT_MIGRATION_COMPLETED: {tenant_id}")
            
        self.tenant_registry[tenant_id] = TenantRolloutAssignment(
            tenant_id=tenant_id,
            wave=wave,
            engine_state=engine_state,
            status=status,
            weight=weight
        )
        return True

    def _hash_tenant(self, tenant_id: str) -> int:
        # Deterministic SHA-256 for stable hashing across processes
        return int(hashlib.sha256(tenant_id.encode('utf-8')).hexdigest(), 16) % 100

    def evaluate_system_state(self):
        cap_state = capacity_guard.get_state()
        if cap_state == CapacityState.CRITICAL and not self.is_paused:
            print("[AUDIT] ROLLOUT_PAUSED")
            self.is_paused = True
        elif cap_state == CapacityState.HEALTHY and self.is_paused:
            print("[AUDIT] ROLLOUT_RESUMED")
            self.is_paused = False

    def get_tenant_state(self, tenant_id: str) -> EngineState:
        if self.global_rollback:
            return EngineState.FAISS_ONLY
            
        self.evaluate_system_state()

        if tenant_id in self.tenant_registry:
            assignment = self.tenant_registry[tenant_id]
            if assignment.status != "ROLLED_BACK":
                return assignment.engine_state
            return EngineState.FAISS_ONLY

        if self.current_wave > 0:
            percentage = self.wave_percentages.get(self.current_wave, 0)
            if self._hash_tenant(tenant_id) < percentage:
                weight = tenant_capacity_service.get_tenant_score(tenant_id)
                cap_state = capacity_guard.get_state()
                if not self.is_paused and cap_state != CapacityState.WARNING and capacity_guard.check_capacity(weight):
                    return EngineState.PGVECTOR_PRIMARY_SYNC
                else:
                    return EngineState.FAISS_ONLY
                
        return EngineState.FAISS_ONLY

    def rollback_tenant(self, tenant_id: str, reason: str):
        print(f"[AUDIT] TENANT_ROLLBACK: {tenant_id} - Reason: {reason}")
        if tenant_id in self.tenant_registry:
            self.tenant_registry[tenant_id].status = "ROLLED_BACK"
            self.tenant_registry[tenant_id].rollback_reason = reason
        else:
            self.tenant_registry[tenant_id] = TenantRolloutAssignment(
                tenant_id=tenant_id,
                wave=self.current_wave,
                engine_state=EngineState.FAISS_ONLY,
                status="ROLLED_BACK",
                rollback_reason=reason,
                weight=tenant_capacity_service.get_tenant_score(tenant_id)
            )

    def rollback_wave(self, wave_number: int, reason: str):
        print(f"[AUDIT] WAVE_ROLLBACK: Wave {wave_number} - Reason: {reason}")
        for tenant_id, assignment in self.tenant_registry.items():
            if assignment.wave == wave_number and assignment.status != "ROLLED_BACK":
                self.rollback_tenant(tenant_id, reason)
        if self.current_wave == wave_number:
            self.current_wave -= 1
            self.is_paused = False

    def rollback_global(self, reason: str):
        print(f"[AUDIT] GLOBAL_ROLLBACK: Reason: {reason}")
        self.global_rollback = True
        self.current_wave = 0
        self.is_paused = True

    def rollback_emergency(self, reason: str, initiator: str = "auto", affected_count: int = 0):
        ts = datetime.utcnow().isoformat()
        print(f"[AUDIT] EMERGENCY_ROLLBACK_TRIGGERED - Reason: {reason} - Initiator: {initiator} - Timestamp: {ts} - Affected: {affected_count}")
        self.global_rollback = True
        self.current_wave = 0
        self.is_paused = True

rollout_controller = RolloutController()
