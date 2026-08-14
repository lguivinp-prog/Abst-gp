class TenantRegistryInterface:
    def list_active_tenants(self):
        raise NotImplementedError
    
    def get_tenant_profile(self, tenant_id: str):
        raise NotImplementedError
        
    def get_capacity_metrics(self):
        raise NotImplementedError

class MockTenantRegistry(TenantRegistryInterface):
    def __init__(self):
        self.tenants = {
            "whale_tenant": {"qps": 300, "index_size_mb": 5000, "chunk_growth": 500},
            "medium_tenant": {"qps": 50, "index_size_mb": 1000, "chunk_growth": 50},
            "small_tenant": {"qps": 5, "index_size_mb": 100, "chunk_growth": 10}
        }
        # Add synthetic tenants to represent the population
        for i in range(100):
            self.tenants[f"tenant_{i}"] = {"qps": 10, "index_size_mb": 200, "chunk_growth": 20}
            
    def list_active_tenants(self):
        return list(self.tenants.keys())
        
    def get_tenant_profile(self, tenant_id: str):
        return self.tenants.get(tenant_id, {"qps": 10, "index_size_mb": 100, "chunk_growth": 10})
        
    def get_capacity_metrics(self):
        return {"total_qps": 1000}

class TenantCapacityService:
    def __init__(self, registry: TenantRegistryInterface):
        self.registry = registry
        self.weights = {
            "qps_weight": 0.60,
            "index_weight": 0.025,
            "growth_weight": 0.15
        }
        self.version = "v1"
        
    def apply_adjustment(self, adjustment_req):
        if adjustment_req.state == "APPROVED" or adjustment_req.state.value == "APPROVED":
            self.weights = adjustment_req.proposed_weights
            self.version = "v2"
            adjustment_req.apply()
        
    def get_tenant_score(self, tenant_id: str) -> float:
        profile = self.registry.get_tenant_profile(tenant_id)
        score = (profile["qps"] * self.weights["qps_weight"]) + \
                (profile["index_size_mb"] * self.weights["index_weight"]) + \
                (profile["chunk_growth"] * self.weights["growth_weight"])
        return score
        
tenant_capacity_service = TenantCapacityService(MockTenantRegistry())
