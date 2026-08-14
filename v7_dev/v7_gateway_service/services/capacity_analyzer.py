from datetime import datetime
from enum import Enum

class AdjustmentState(Enum):
    PROPOSED = "PROPOSED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    APPLIED = "APPLIED"

class ModelAdjustmentRequest:
    def __init__(self, request_id: str, proposed_weights: dict, reason: str):
        self.request_id = request_id
        self.proposed_weights = proposed_weights
        self.reason = reason
        self.state = AdjustmentState.PROPOSED
        self.created_at = datetime.utcnow()

    def approve(self):
        self.state = AdjustmentState.APPROVED
        print(f"[AUDIT] MODEL_ADJUSTMENT_APPROVED: {self.request_id}")
        
    def apply(self):
        self.state = AdjustmentState.APPLIED
        print(f"[AUDIT] MODEL_ADJUSTMENT_APPLIED: {self.request_id}")

class CapacityDeltaAnalyzer:
    def __init__(self):
        self.last_prediction = 0.0
        self.last_actual = 0.0
        self.pending_adjustments = {}

    def record_prediction(self, wave: int, predicted_load: float):
        self.last_prediction = predicted_load
        print(f"[AUDIT] WAVE_PREDICTION: Wave {wave} predicted {predicted_load}")
        
    def run_simulated_soak_test(self, wave: int, actual_load: float):
        print(f"[AUDIT] SIMULATED_SOAK_TEST: Wave {wave} actual load observed {actual_load}")
        self.last_actual = actual_load
        return self.analyze_delta(wave)

    def analyze_delta(self, wave: int):
        if self.last_prediction == 0:
            return None
            
        prediction_error = self.last_actual - self.last_prediction
        error_pct = (prediction_error / self.last_prediction) * 100 if self.last_prediction > 0 else 0
        
        print(f"[AUDIT] CAPACITY_DELTA: Wave {wave} - Predicted: {self.last_prediction}, Actual: {self.last_actual}, Error: {error_pct:.2f}%")
        
        # If error > 10%, propose adjustment
        if error_pct > 10.0:
            req_id = f"adj_w{wave}_{int(datetime.utcnow().timestamp())}"
            # Naive proposal: Increase QPS weight from 0.60 to 0.70 to be more conservative
            adj = ModelAdjustmentRequest(
                request_id=req_id,
                proposed_weights={"qps_weight": 0.70, "index_weight": 0.20, "growth_weight": 0.10},
                reason=f"Actual load exceeded prediction by {error_pct:.2f}%"
            )
            self.pending_adjustments[req_id] = adj
            print(f"[AUDIT] MODEL_ADJUSTMENT_REQUEST_PROPOSED: {req_id}")
            
        return {
            "prediction_error": prediction_error,
            "error_percentage": error_pct
        }

capacity_analyzer = CapacityDeltaAnalyzer()
