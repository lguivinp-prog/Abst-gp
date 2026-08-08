export type WorkerLivenessStatus = 'IDLE' | 'BUSY' | 'UNRESPONSIVE' | 'OFFLINE';

export interface WorkerStatusItem {
  worker_name: string;
  worker_type: string;
  hostname: string;
  status: WorkerLivenessStatus;
  current_job_id: string | null;
  tenant_id: string | null;
  last_seen: string;
  started_at: string;
  is_healthy: boolean;
  seconds_since_last_seen: number;
  uptime_seconds: number;
}

export interface WorkerListResponse {
  total_workers: number;
  active_workers: number;
  unresponsive_workers: number;
  offline_workers: number;
  workers: WorkerStatusItem[];
  timestamp: string;
}

export interface LatencyMetricsItem {
  job_type: string;
  sample_count: number;
  p50_ms: number;
  p95_ms: number;
  p99_ms: number;
  avg_ms: number;
  min_ms: number;
  max_ms: number;
}

export interface LatencyReportResponse {
  time_window_hours: number;
  tenant_id: string;
  total_samples: number;
  global_metrics: LatencyMetricsItem;
  metrics_by_job_type: LatencyMetricsItem[];
  timestamp: string;
}

export interface ErrorAnalyticsResponse {
  time_window_hours: number;
  tenant_id: string;
  total_processed: number;
  failed_jobs: number;
  failure_rate_percent: number;
  errors_by_category: Record<string, number>;
  errors_by_code: Record<string, number>;
  errors_by_job_type: Record<string, number>;
  timestamp: string;
}

export interface StaleJobSummaryItem {
  job_id: string;
  job_type: string;
  status: string;
  attempt_count: number;
  max_retries: number;
  created_at: string;
  started_at: string | null;
  last_heartbeat_at: string | null;
  stale_duration_sec: number;
}

export interface RecoverySummaryResponse {
  stale_processing_count: number;
  stale_queued_count: number;
  recovered_jobs_count: number;
  failed_final_count: number;
  last_execution: string | null;
  stale_processing_jobs: StaleJobSummaryItem[];
  stale_queued_jobs: StaleJobSummaryItem[];
}

export interface RecoveryTriggerResponse {
  message: string;
  total_scanned: number;
  stale_processing_count: number;
  stale_queued_count: number;
  recovered_retried: number;
  marked_failed_final: number;
  marked_failed_max_retries: number;
  skipped_terminal: number;
  job_details: Array<Record<string, unknown>>;
  timestamp: string;
  tenant_id: string | null;
}
