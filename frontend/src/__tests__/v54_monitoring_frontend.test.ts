import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import type {
  WorkerListResponse,
  LatencyReportResponse,
  ErrorAnalyticsResponse,
  RecoverySummaryResponse,
  RecoveryTriggerResponse,
  WorkerStatusItem,
} from '../types/monitoring';

describe('V5.4 Frontend SRE Monitoring - Contracts & Logic Validation', () => {
  it('should validate WorkerListResponse contract and dynamic liveness states', () => {
    const workerMock: WorkerStatusItem = {
      worker_name: 'quotation-worker-1',
      worker_type: 'quotation_worker',
      hostname: 'host-worker-node-1',
      status: 'BUSY',
      current_job_id: 'job-quot-abc-123',
      tenant_id: 'tenant-inst-01',
      last_seen: '2026-08-04T12:00:00Z',
      started_at: '2026-08-04T08:00:00Z',
      is_healthy: true,
      seconds_since_last_seen: 5.2,
      uptime_seconds: 14400,
    };

    const workerList: WorkerListResponse = {
      total_workers: 3,
      active_workers: 2,
      unresponsive_workers: 1,
      offline_workers: 0,
      workers: [workerMock],
      timestamp: '2026-08-04T12:00:05Z',
    };

    assert.equal(workerList.total_workers, 3);
    assert.equal(workerList.active_workers, 2);
    assert.equal(workerList.unresponsive_workers, 1);
    assert.equal(workerList.workers[0].status, 'BUSY');
    assert.equal(workerList.workers[0].current_job_id, 'job-quot-abc-123');
    assert.equal(workerList.workers[0].is_healthy, true);
  });

  it('should validate LatencyReportResponse contract and SLA percentiles', () => {
    const latencyReport: LatencyReportResponse = {
      time_window_hours: 24,
      tenant_id: 'tenant-inst-01',
      total_samples: 120,
      global_metrics: {
        job_type: 'GLOBAL',
        sample_count: 120,
        p50_ms: 1250.5,
        p95_ms: 4500.0,
        p99_ms: 8200.0,
        avg_ms: 1850.2,
        min_ms: 320.0,
        max_ms: 9100.0,
      },
      metrics_by_job_type: [
        {
          job_type: 'QUOTATION_EXTRACTION',
          sample_count: 80,
          p50_ms: 1100.0,
          p95_ms: 3800.0,
          p99_ms: 5500.0,
          avg_ms: 1400.0,
          min_ms: 320.0,
          max_ms: 6000.0,
        },
        {
          job_type: 'COMPARISON_EVALUATION',
          sample_count: 40,
          p50_ms: 2200.0,
          p95_ms: 7100.0,
          p99_ms: 9100.0,
          avg_ms: 2750.0,
          min_ms: 850.0,
          max_ms: 9100.0,
        },
      ],
      timestamp: '2026-08-04T12:00:00Z',
    };

    assert.equal(latencyReport.total_samples, 120);
    assert.equal(latencyReport.global_metrics.p50_ms, 1250.5);
    assert.equal(latencyReport.global_metrics.p95_ms, 4500.0);
    assert.equal(latencyReport.global_metrics.p99_ms, 8200.0);
    assert.equal(latencyReport.metrics_by_job_type.length, 2);
    assert.equal(latencyReport.metrics_by_job_type[0].job_type, 'QUOTATION_EXTRACTION');
  });

  it('should validate ErrorAnalyticsResponse contract and taxonomy categorization', () => {
    const errorAnalytics: ErrorAnalyticsResponse = {
      time_window_hours: 24,
      tenant_id: 'tenant-inst-01',
      total_processed: 500,
      failed_jobs: 15,
      failure_rate_percent: 3.0,
      errors_by_category: {
        TRANSIENT_INFRA: 10,
        CORRUPT_INPUT: 3,
        BUSINESS_RULE: 2,
      },
      errors_by_code: {
        REDIS_CONNECTION_TIMEOUT: 7,
        DB_LOCK_TIMEOUT: 3,
        CORRUPT_PDF_FILE: 3,
        INVALID_TAX_ID: 2,
      },
      errors_by_job_type: {
        QUOTATION_EXTRACTION: 12,
        COMPARISON_EVALUATION: 3,
      },
      timestamp: '2026-08-04T12:00:00Z',
    };

    assert.equal(errorAnalytics.total_processed, 500);
    assert.equal(errorAnalytics.failed_jobs, 15);
    assert.equal(errorAnalytics.failure_rate_percent, 3.0);
    assert.equal(errorAnalytics.errors_by_category.TRANSIENT_INFRA, 10);
    assert.equal(errorAnalytics.errors_by_category.CORRUPT_INPUT, 3);
    assert.equal(errorAnalytics.errors_by_code.REDIS_CONNECTION_TIMEOUT, 7);
  });

  it('should validate RecoverySummaryResponse and RecoveryTriggerResponse contracts', () => {
    const recoverySummary: RecoverySummaryResponse = {
      stale_processing_count: 2,
      stale_queued_count: 1,
      recovered_jobs_count: 14,
      failed_final_count: 3,
      last_execution: '2026-08-04T11:45:00Z',
      stale_processing_jobs: [
        {
          job_id: 'job-stale-001',
          job_type: 'QUOTATION_EXTRACTION',
          status: 'PROCESSING',
          attempt_count: 1,
          max_retries: 3,
          created_at: '2026-08-04T11:30:00Z',
          started_at: '2026-08-04T11:30:05Z',
          last_heartbeat_at: '2026-08-04T11:30:10Z',
          stale_duration_sec: 90.0,
        },
      ],
      stale_queued_jobs: [
        {
          job_id: 'job-stale-002',
          job_type: 'COMPARISON_EVALUATION',
          status: 'QUEUED',
          attempt_count: 0,
          max_retries: 3,
          created_at: '2026-08-04T11:00:00Z',
          started_at: null,
          last_heartbeat_at: null,
          stale_duration_sec: 400.0,
        },
      ],
    };

    assert.equal(recoverySummary.stale_processing_count, 2);
    assert.equal(recoverySummary.stale_processing_jobs[0].job_id, 'job-stale-001');
    assert.equal(recoverySummary.stale_queued_jobs[0].stale_duration_sec, 400.0);

    const triggerResult: RecoveryTriggerResponse = {
      message: 'Reconciliation cycle completed successfully',
      total_scanned: 3,
      stale_processing_count: 2,
      stale_queued_count: 1,
      recovered_retried: 2,
      marked_failed_final: 1,
      marked_failed_max_retries: 0,
      skipped_terminal: 0,
      job_details: [
        { job_id: 'job-stale-001', outcome: 'RECOVERED_RETRY' },
      ],
      timestamp: '2026-08-04T12:05:00Z',
      tenant_id: 'tenant-inst-01',
    };

    assert.equal(triggerResult.total_scanned, 3);
    assert.equal(triggerResult.recovered_retried, 2);
    assert.equal(triggerResult.marked_failed_final, 1);
    assert.equal(triggerResult.tenant_id, 'tenant-inst-01');
  });
});
