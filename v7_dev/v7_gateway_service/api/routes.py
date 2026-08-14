from fastapi import APIRouter, Depends
from models.requests import SanitizeRequest, ValidateRequest, RouteRequest
from models.responses import SanitizeResponse, ValidateResponse, RouteResponse
from services.masking import masking_service
from services.policy import policy_service
from services.routing import routing_service
from security.auth import get_current_user
from audit.event_logger import audit_logger

router = APIRouter(prefix="/v7/gateway", dependencies=[Depends(get_current_user)])

@router.post("/sanitize", response_model=SanitizeResponse)
def sanitize_content(req: SanitizeRequest, current_user: dict = Depends(get_current_user)):
    # Tenant context is now implicitly bound to current_user["tenant_id"] from JWT
    tenant_id = current_user["tenant_id"]
    
    masked = masking_service.mask_text(req.content)
    decision = policy_service.evaluate_request(masked)
    
    versions = {"schema": req.schema_version, "policy": req.policy_version}
    audit_hash = audit_logger.log_event(req.request_id, decision, versions)
    
    return SanitizeResponse(
        request_id=req.request_id,
        masked_content=masked if decision == "ALLOW" else "",
        decision=decision,
        audit_hash=audit_hash
    )

@router.post("/validate", response_model=ValidateResponse)
def validate_response(req: ValidateRequest, current_user: dict = Depends(get_current_user)):
    tenant_id = current_user["tenant_id"]
    decision = policy_service.evaluate_response(req.ai_response, req.evidence_ids)
    
    versions = {"schema": req.schema_version, "policy": req.policy_version}
    audit_hash = audit_logger.log_event(req.request_id, decision, versions)
    
    return ValidateResponse(
        request_id=req.request_id,
        decision=decision,
        audit_hash=audit_hash
    )

@router.post("/route", response_model=RouteResponse)
def route_query(req: RouteRequest, current_user: dict = Depends(get_current_user)):
    tenant_id = current_user["tenant_id"]
    target = routing_service.determine_route(tenant_id)
    
    versions = {"schema": req.schema_version, "policy": req.policy_version}
    audit_hash = audit_logger.log_event(req.request_id, "ROUTE_OK", versions)
    
    return RouteResponse(
        request_id=req.request_id,
        target_engine=target,
        decision="ALLOW",
        audit_hash=audit_hash
    )

@router.get("/dashboard")
def get_dashboard(tenant_id: str = "whale_tenant"):
    from services.rollout_controller import rollout_controller
    from services.capacity_guard import capacity_guard
    from services.tenant_capacity import tenant_capacity_service
    from services.capacity_analyzer import capacity_analyzer
    
    rollbacks = sum(1 for a in rollout_controller.tenant_registry.values() if a.status == "ROLLED_BACK")
    active = sum(1 for a in rollout_controller.tenant_registry.values() if a.status == "ACTIVE_V7")
    
    # Simulate next wave
    next_wave = rollout_controller.current_wave + 1
    sim_result = None
    if next_wave <= 5:
        sim_result = rollout_controller.simulate_wave(next_wave)
        
    error_pct = 0
    if capacity_analyzer.last_prediction > 0:
        error_pct = ((capacity_analyzer.last_actual - capacity_analyzer.last_prediction) / capacity_analyzer.last_prediction) * 100
        
    retirement_state = "RETIREMENT_PENDING" if rollout_controller.current_wave == 5 else "IN_PROGRESS"
        
    return {
        "current_wave": rollout_controller.current_wave,
        "active_tenants": active,
        "rollback_tenants": rollbacks,
        "capacity_status": capacity_guard.get_state().value,
        "predicted_load": capacity_analyzer.last_prediction,
        "actual_load": capacity_analyzer.last_actual,
        "prediction_error": error_pct,
        "model_version": tenant_capacity_service.version,
        "simulation_status": sim_result["status"] if sim_result else "N/A",
        "soak_status": "SIMULATED_SOAK" if rollout_controller.current_wave > 0 else "N/A",
        "security_status": "PASS" if rollout_controller.active_isolation_violations == 0 else "FAIL",
        "cost_status": "PASS" if rollout_controller.cost_within_budget else "FAIL",
        "retirement_status": retirement_state,
        "migration_percentage": rollout_controller.wave_percentages.get(rollout_controller.current_wave, 0),
        "pause_state": rollout_controller.is_paused,
        "global_rollback": rollout_controller.global_rollback
    }
