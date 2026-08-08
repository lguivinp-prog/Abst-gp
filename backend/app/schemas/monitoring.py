from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


# =========================================================
# 1. WORKER MONITORING SCHEMAS
# =========================================================

class WorkerStatusResponse(BaseModel):
    worker_name: str
    worker_type: str
    hostname: str
    status: str  # IDLE, BUSY, UNRESPONSIVE, OFFLINE
    current_job_id: Optional[str] = None
    tenant_id: Optional[str] = None
    last_seen: datetime
    started_at: datetime
    uptime_seconds: int
    is_healthy: bool

    model_config = {"from_attributes": True}


class WorkerListResponse(BaseModel):
    total_workers: int
    total_active: int
    total_busy: int
    total_unresponsive: int
    total_offline: int
    workers: List[WorkerStatusResponse]


# =========================================================
# 2. LATENCY METRICS SCHEMAS
# =========================================================

class LatencyMetricsResponse(BaseModel):
    job_type: str
    sample_count: int
    p50_ms: float
    p95_ms: float
    p99_ms: float
    avg_ms: float
    min_ms: int
    max_ms: int
    time_window_hours: int


class LatencyReportResponse(BaseModel):
    time_window_hours: int
    total_samples: int
    global_metrics: LatencyMetricsResponse
    metrics_by_job_type: List[LatencyMetricsResponse]


# =========================================================
# 3. ERROR ANALYTICS SCHEMAS
# =========================================================

class ErrorSummaryItem(BaseModel):
    error_category: str
    error_code: str
    job_type: str
    count: int
    percentage: float
    sample_error_message: Optional[str] = None


class ErrorAnalyticsResponse(BaseModel):
    time_window_hours: int
    total_jobs: int
    failed_jobs: int
    failure_rate_percent: float
    errors_by_category: Dict[str, int]
    errors_by_code: Dict[str, int]
    errors_by_job_type: Dict[str, int]
    error_details: List[ErrorSummaryItem]


# =========================================================
# 4. RECOVERY STATUS SCHEMAS
# =========================================================

class StaleJobSummaryItem(BaseModel):
    job_id: str
    job_type: str
    status: str
    attempt_count: int
    max_retries: int
    worker_name: Optional[str] = None
    stale_duration_seconds: Optional[int] = None


class RecoverySummaryResponse(BaseModel):
    stale_processing_count: int
    stale_queued_count: int
    recovered_jobs_count: int
    failed_final_count: int
    last_execution: Optional[datetime] = None
    stale_processing_jobs: List[StaleJobSummaryItem]
    stale_queued_jobs: List[StaleJobSummaryItem]


class RecoveryTriggerResponse(BaseModel):
    message: str
    total_scanned: int
    stale_processing_count: int
    stale_queued_count: int
    recovered_retried: int
    marked_failed_final: int
    marked_failed_max_retries: int
    skipped_terminal: int
    job_details: List[Dict[str, Any]] = []
    timestamp: datetime
    tenant_id: Optional[str] = None

