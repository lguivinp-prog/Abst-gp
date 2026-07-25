import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta, timezone
from app.api.routing import TenantRouter
from app.models.domain import SystemSettings

def test_tenant_router_auto_mode():
    class DummySettings:
        active_ring = 2
        
    class DummyAssignment:
        routing_mode = "AUTO"
        assigned_ring = 1
        override_until = None
        
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = DummyAssignment()
    mock_db.query.return_value.first.return_value = DummySettings()
    
    with patch("app.api.routing.redis_conn.get", return_value=None):
        with patch("app.api.routing.redis_conn.setex"):
            route = TenantRouter.get_tenant_routing("tenant_xyz", mock_db)
            
    assert route["routing_mode"] == "AUTO"
    assert route["engine"] == "v2"
    
def test_tenant_router_auto_mode_exceeds_active():
    class DummySettings:
        active_ring = 1
        
    class DummyAssignment:
        routing_mode = "AUTO"
        assigned_ring = 2
        override_until = None
        
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = DummyAssignment()
    mock_db.query.return_value.first.return_value = DummySettings()
    
    with patch("app.api.routing.redis_conn.get", return_value=None):
        with patch("app.api.routing.redis_conn.setex"):
            route = TenantRouter.get_tenant_routing("tenant_xyz", mock_db)
            
    assert route["routing_mode"] == "AUTO"
    assert route["engine"] == "v1"

def test_tenant_router_force_v2_override():
    class DummySettings:
        active_ring = 1
        
    class DummyAssignment:
        routing_mode = "FORCE_V2"
        assigned_ring = None
        override_until = datetime.now(timezone.utc) + timedelta(minutes=10)
        
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = DummyAssignment()
    mock_db.query.return_value.first.return_value = DummySettings()
    
    with patch("app.api.routing.redis_conn.get", return_value=None):
        with patch("app.api.routing.redis_conn.setex") as mock_setex:
            route = TenantRouter.get_tenant_routing("tenant_xyz", mock_db)
            
            # Check TTL
            call_args = mock_setex.call_args[0]
            assert 0 < call_args[1] <= 300 # Should use TTL based on override if <= 300, wait, remaining is 600 so min(300, 600) = 300
            assert call_args[1] == 300
            
    assert route["routing_mode"] == "FORCE_V2"
    assert route["engine"] == "v2"
