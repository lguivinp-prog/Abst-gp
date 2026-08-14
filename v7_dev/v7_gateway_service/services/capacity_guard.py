from enum import Enum

class CapacityState(Enum):
    HEALTHY = "HEALTHY"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"
    PAUSED = "PAUSED"

class CapacityGuardService:
    def __init__(self):
        self.metrics = {
            "cpu_usage": 40.0,
            "ram_usage": 50.0,
            "iops": 1000,
            "redis_memory": 60.0,
            "celery_queue_depth": 0,
            "pgvector_latency": 10.0
        }
        self.current_state = CapacityState.HEALTHY
        self.total_capacity_available = 1000.0  # arbitrary capacity units

    def update_metrics(self, **kwargs):
        for k, v in kwargs.items():
            if k in self.metrics:
                self.metrics[k] = v
        self._evaluate_state()

    def _evaluate_state(self):
        old_state = self.current_state
        
        # Check thresholds
        if self.metrics["cpu_usage"] > 90 or self.metrics["celery_queue_depth"] > 100000 or self.metrics["pgvector_latency"] > 200:
            self.current_state = CapacityState.CRITICAL
        elif self.metrics["cpu_usage"] > 75 or self.metrics["celery_queue_depth"] > 50000 or self.metrics["pgvector_latency"] > 100:
            self.current_state = CapacityState.WARNING
        else:
            self.current_state = CapacityState.HEALTHY
            
        if old_state != self.current_state:
            if self.current_state == CapacityState.WARNING:
                print(f"[AUDIT] CAPACITY_WARNING: System approaching limits")
            elif self.current_state == CapacityState.CRITICAL:
                print(f"[AUDIT] CAPACITY_CRITICAL: Resource exhaustion")

    def get_state(self) -> CapacityState:
        return self.current_state
        
    def check_capacity(self, load_weight: float) -> bool:
        # Check if adding load_weight exceeds total safe capacity (Warning threshold is ~75% utilization)
        # Simplified simulation
        return load_weight <= (self.total_capacity_available * 0.25)

capacity_guard = CapacityGuardService()
