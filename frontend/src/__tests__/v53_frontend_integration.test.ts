import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { normalizeJobStatus } from '../features/cases/hooks/useJobPolling';
import type { ProcessingJobResponse, QuotationUploadResponse, ComparisonRunResponse } from '../types';

describe('V5.3 Frontend Unit Tests - State Normalization & Contracts', () => {
  it('should normalize job statuses correctly across V5.3 and legacy formats', () => {
    // READY states
    assert.equal(normalizeJobStatus('READY', 100), 'READY');
    assert.equal(normalizeJobStatus('finished', 100), 'READY');
    assert.equal(normalizeJobStatus('FINISHED', 50), 'READY');
    assert.equal(normalizeJobStatus('PROCESSING', 100), 'READY');

    // FAILED states
    assert.equal(normalizeJobStatus('FAILED', 50), 'FAILED');
    assert.equal(normalizeJobStatus('failed', 0), 'FAILED');
    assert.equal(normalizeJobStatus('ERROR', 20), 'FAILED');

    // QUEUED states
    assert.equal(normalizeJobStatus('QUEUED', 0), 'QUEUED');
    assert.equal(normalizeJobStatus('queued', 0), 'QUEUED');
    assert.equal(normalizeJobStatus('deferred', 0), 'QUEUED');

    // PROCESSING states
    assert.equal(normalizeJobStatus('PROCESSING', 25), 'PROCESSING');
    assert.equal(normalizeJobStatus('started', 40), 'PROCESSING');
    assert.equal(normalizeJobStatus(undefined, 30), 'PROCESSING');
    assert.equal(normalizeJobStatus(undefined, 100), 'READY');
  });

  it('should conform to ProcessingJobResponse TypeScript contract', () => {
    const asyncJob: ProcessingJobResponse = {
      job_id: 'job-quot-12345',
      case_id: 42,
      document_id: 10,
      job_type: 'QUOTATION_EXTRACTION',
      worker_type: 'quotation_worker',
      status: 'PROCESSING',
      progress: 45,
      message: 'Extrayendo condiciones de la cotización...',
      case_status: 'WAITING_QUOTATION',
      result_summary: { fields_extracted: 5 },
      created_at: '2026-08-04T00:00:00Z',
      started_at: '2026-08-04T00:00:01Z',
      finished_at: null,
      error_message: null
    };

    assert.equal(asyncJob.job_id, 'job-quot-12345');
    assert.equal(asyncJob.status, 'PROCESSING');
    assert.equal(asyncJob.progress, 45);
    assert.equal(asyncJob.worker_type, 'quotation_worker');
    assert.equal(asyncJob.result_summary?.fields_extracted, 5);
  });

  it('should support both Async V5.3 and Sync V5.2.1 Quotation upload responses', () => {
    // Async V5.3 response
    const asyncResponse: QuotationUploadResponse = {
      message: 'Quotation upload processing queued',
      job_id: 'job-quot-999',
      status: 'QUEUED'
    };
    assert.ok(asyncResponse.job_id);
    assert.equal(asyncResponse.status, 'QUEUED');

    // Sync V5.2.1 fallback response
    const syncResponse: QuotationUploadResponse = {
      message: 'Cotización procesada exitosamente'
    };
    assert.equal(syncResponse.job_id, undefined);
    assert.equal(syncResponse.message, 'Cotización procesada exitosamente');
  });

  it('should support both Async V5.3 and Sync V5.2.1 Comparison run responses', () => {
    // Async V5.3 response
    const asyncResponse: ComparisonRunResponse = {
      message: 'Comparison job queued',
      job_id: 'job-comp-888',
      status: 'QUEUED',
      alreadyCompleted: false,
      already_completed: false
    };
    assert.ok(asyncResponse.job_id);
    assert.equal(asyncResponse.status, 'QUEUED');
    assert.equal(asyncResponse.alreadyCompleted, false);

    // Sync V5.2.1 fallback response
    const syncResponse: ComparisonRunResponse = {
      message: 'Comparison already completed',
      alreadyCompleted: true,
      already_completed: true
    };
    assert.equal(syncResponse.job_id, undefined);
    assert.equal(syncResponse.alreadyCompleted, true);
  });

  it('should simulate async job polling lifecycle successfully', async () => {
    const jobSteps: ProcessingJobResponse[] = [
      { job_id: 'j1', status: 'QUEUED', progress: 0, message: 'En cola' },
      { job_id: 'j1', status: 'PROCESSING', progress: 30, message: 'Extrayendo texto...' },
      { job_id: 'j1', status: 'PROCESSING', progress: 80, message: 'Procesando tablas...' },
      { job_id: 'j1', status: 'READY', progress: 100, message: 'Completado' }
    ];

    let stepIndex = 0;
    const fetchNextStatus = () => {
      const step = jobSteps[stepIndex];
      if (stepIndex < jobSteps.length - 1) stepIndex++;
      return step;
    };

    let current = fetchNextStatus();
    assert.equal(normalizeJobStatus(current.status, current.progress), 'QUEUED');

    current = fetchNextStatus();
    assert.equal(normalizeJobStatus(current.status, current.progress), 'PROCESSING');
    assert.equal(current.progress, 30);

    current = fetchNextStatus();
    assert.equal(normalizeJobStatus(current.status, current.progress), 'PROCESSING');
    assert.equal(current.progress, 80);

    current = fetchNextStatus();
    assert.equal(normalizeJobStatus(current.status, current.progress), 'READY');
    assert.equal(current.progress, 100);
  });

  it('should simulate async job failure and capture error_message', async () => {
    const failedJob: ProcessingJobResponse = {
      job_id: 'j2',
      status: 'FAILED',
      progress: 40,
      message: 'Error en worker',
      error_message: 'Corrupted PDF structure at page 3'
    };

    assert.equal(normalizeJobStatus(failedJob.status, failedJob.progress), 'FAILED');
    assert.equal(failedJob.error_message, 'Corrupted PDF structure at page 3');
  });
});
