import pytest
import uuid
from fastapi.testclient import TestClient
from app.api.routers.v6_admin import router
from app.models.v6.tenant_config import TenantConfiguration, TenantConfigurationHistory
from sqlalchemy.orm import Session
from app.services.v6.governance.admin_service import AdminGovernanceService
from fastapi import FastAPI
from app.models.domain import User
from app.api.deps import require_admin_it, get_db

app = FastAPI()
app.include_router(router, prefix="/api/v6/admin")

# Dependency overriding for tests
def override_require_admin_it():
    return User(id=5, role="ADMIN_IT", tenant_id="tenantA")

app.dependency_overrides[require_admin_it] = override_require_admin_it
def test_admin_api_thresholds_validation(db_session: Session):
    tenant_id = f"tenant_admin_api_{uuid.uuid4().hex[:8]}"

    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[require_admin_it] = lambda: User(
        id=5,
        role="ADMIN_IT",
        tenant_id=tenant_id,
    )

    client = TestClient(app)

    # Pre-create config
    config = AdminGovernanceService(db_session).get_configuration(tenant_id)
    assert config.configuration_version == 1

    # Test valid update
    res = client.put(
        "/api/v6/admin/config/thresholds",
        json={"min_dpi": 200, "reason": "Test"},
    )
    assert res.status_code == 200
    assert res.json()["new_version"] == 2

    # Test destructive out-of-bounds update
    res_bad = client.put(
        "/api/v6/admin/config/thresholds",
        json={"min_dpi": 10},
    )
    assert res_bad.status_code == 400
    assert "out of bounds" in res_bad.json()["detail"]

    # Check history
    history = (
        db_session.query(TenantConfigurationHistory)
        .filter_by(tenant_id=tenant_id)
        .first()
    )
    assert history is not None
    assert history.version == 2
    assert history.new_value == "200"

def test_telemetry_scheduler(db_session: Session):
    from app.services.v6.telemetry.telemetry_scheduler import InstitutionalTelemetryScheduler

    tenant_opt_in = f"telemetry_on_{uuid.uuid4().hex[:8]}"
    tenant_opt_out = f"telemetry_off_{uuid.uuid4().hex[:8]}"

    # Set one tenant to True, one to False
    c1 = TenantConfiguration(
        tenant_id=tenant_opt_in,
        telemetry_opt_in=True,
    )
    c2 = TenantConfiguration(
        tenant_id=tenant_opt_out,
        telemetry_opt_in=False,
    )
    db_session.add(c1)
    db_session.add(c2)
    db_session.commit()

    scheduler = InstitutionalTelemetryScheduler(db_session)
    processed = scheduler.run_weekly_job()

    # Privacy check: Only the opt-in tenant should be processed
    assert tenant_opt_in in processed
    assert tenant_opt_out not in processed
