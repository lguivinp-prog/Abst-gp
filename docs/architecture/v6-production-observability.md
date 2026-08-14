# V6 Production Observability

This document defines the metrics required to monitor the new Object Storage and V2 Upload and Worker flows in production. The goal is to provide granular observability into the lifecycle of documents from upload initiation through processing and final availability.

## 1. Upload Metrics

To monitor the client-side interaction with presigned URLs and the Abast-GP API:

- **`upload_duration_seconds`** (Histogram)
  - **Description**: Total time taken for the client to complete the upload flow (from `initiate` to `complete`).
  - **Labels**: `tenant_id`, `file_size_bucket`
- **`upload_failures_total`** (Counter)
  - **Description**: Total number of uploads that were initiated but failed to complete or were abandoned.
  - **Labels**: `tenant_id`, `reason` (e.g., timeout, network_error)
- **`checksum_failures_total`** (Counter)
  - **Description**: Number of times the `complete` endpoint rejected an upload due to a SHA-256 mismatch.
  - **Labels**: `tenant_id`
- **`expired_uploads_total`** (Counter)
  - **Description**: Number of upload sessions that reached the `EXPIRED` state due to inactivity (cleaned up by cron).
  - **Labels**: `tenant_id`

## 2. Object Storage Metrics

To monitor the performance and reliability of the underlying storage backend (MinIO/S3):

- **`storage_put_latency_seconds`** (Histogram)
  - **Description**: Latency of HTTP PUT requests to the object storage provider.
  - **Labels**: `backend` (s3/minio), `bucket_name`
- **`storage_get_latency_seconds`** (Histogram)
  - **Description**: Latency of HTTP GET requests from the object storage provider.
  - **Labels**: `backend` (s3/minio), `bucket_name`
- **`storage_errors_total`** (Counter)
  - **Description**: Total number of HTTP 4xx or 5xx errors returned by the object storage provider.
  - **Labels**: `backend`, `error_code`

## 3. OCR Worker Metrics

To monitor the async worker pipeline and its interaction with object storage:

- **`ocr_processing_duration_seconds`** (Histogram)
  - **Description**: End-to-end processing time for a single OCR job, excluding queue waiting time.
  - **Labels**: `worker_id`, `tenant_id`, `file_size_bucket`
- **`workspace_materialization_seconds`** (Histogram)
  - **Description**: Time taken to download the original document from object storage to the worker's local temporary workspace.
  - **Labels**: `worker_id`
- **`artifact_upload_duration_seconds`** (Histogram)
  - **Description**: Time taken to upload the extracted artifacts (`structured_{id}.json`, `validation_artifacts.json`) back to object storage.
  - **Labels**: `worker_id`

## Implementation Strategy

These metrics will be exposed via a `/metrics` Prometheus endpoint in the FastAPI backend and scraped every 15s. Grafana dashboards will be created (in Phase 2 of K8s migration) to visualize anomalies, specifically SLA breaches on `ocr_processing_duration_seconds` and spikes in `checksum_failures_total`.
