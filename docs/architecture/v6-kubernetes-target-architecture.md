# V6 Kubernetes Target Architecture Design

This document establishes the strategic architectural design for deploying the Abast-GP Document Intelligence Pipeline (V6) into an Enterprise Kubernetes environment.

## 1. Workloads Architecture

### API Tier (FastAPI)
- **Deployment**: Standard Kubernetes `Deployment` object.
- **Replicas**: Minimum 3 replicas across different Availability Zones (AZs) for high availability.
- **Probes**:
  - `livenessProbe`: `/health` endpoint to detect deadlocks.
  - `readinessProbe`: `/ready` endpoint checking DB and Redis connectivity.
- **Resources**:
  - `requests`: CPU 500m, Mem 512Mi
  - `limits`: CPU 1000m, Mem 1Gi

### General Worker (Redis Queue)
- **Deployment**: Standard Kubernetes `Deployment`.
- **Queue Model**: Consumes non-blocking background jobs (e.g., cleanup, metadata syncing) from Redis.
- **Health Model**: Internal heartbeat mechanism reported to Redis; `livenessProbe` checks local worker process responsiveness.

### OCR Worker V2
- **Scaling Strategy**: Isolated `Deployment` independent of General Workers due to heavy CPU requirements.
- **Workspace**: Configured with `emptyDir` backed by memory (`Medium: Memory`) or fast local NVMe for temporary file materialization, avoiding network-attached storage latency.
- **Object Storage Access**: Interacts strictly via IAM Roles for Service Accounts (IRSA/OIDC) to retrieve source PDFs and upload parsed JSON artifacts.

## 2. Autoscaling

### API (HPA)
- **Mechanism**: Horizontal Pod Autoscaler.
- **Triggers**: Target average CPU utilization at 70%, or memory utilization at 80%. Target HTTP requests per second (custom metrics via Prometheus Adapter).
- **Limits**: Min 3, Max 20 pods.

### Async Workers (KEDA)
- **Mechanism**: Kubernetes Event-driven Autoscaling (KEDA).
- **Triggers**: Redis List Length (queue depth) and pending processing backlog.
- **Limits**:
  - OCR Worker: Min 1, Max 50 (to prevent compute exhaustion and DB connection pool saturation).
  - General Worker: Min 1, Max 10.
- **Risks**: Rapid scaling of OCR workers can overwhelm the PostgreSQL connection pool. Mitigation: Implement PgBouncer.

## 3. PostgreSQL Strategy

### CloudNativePG vs Managed PostgreSQL

| Feature | CloudNativePG (Operator) | Managed PostgreSQL (RDS/CloudSQL) |
| :--- | :--- | :--- |
| **Backup & WAL** | Integrated with S3/MinIO via Barman. | Fully managed automated snapshots. |
| **PITR** | Granular PITR out of the box using WAL archives. | Supported up to 35 days standard. |
| **Failover** | Automated failover relying on Raft consensus and Patroni/repmgr. | Native multi-AZ synchronous replication failover. |
| **Operation** | Requires active SRE monitoring of storage classes, CPU limits, and operator health. | Zero-touch infrastructure. |
| **Cost** | Only raw compute/storage costs. | Premium pricing for managed services. |

**Decision**: For Enterprise Production, **Managed PostgreSQL (e.g., AWS RDS)** is highly recommended to offload the immense operational burden of stateful database maintenance, freeing the team to focus on the document pipeline. CloudNativePG is an excellent fallback for on-premise deployments or restricted sovereign cloud environments.

## 4. Object Storage Strategy

- **Provider**: AWS S3 for Cloud deployments, MinIO for on-premise/hybrid deployments.
- **Buckets**: Segregation of temporary uploads vs long-term storage buckets.
- **Lifecycle**: Automatic expiration rules on temporary buckets for abandoned uploads (backup to the Celery cron cleanup).
- **IAM**: Strict enforcement of Least Privilege using OIDC/IRSA. API service account has `Put` for presigned URLs; OCR worker has `Get` for source and `Put` for artifacts.
- **Tenant Isolation**: Mandatory logical isolation utilizing `prefix: {tenant_id}/`.
- **Integrity**: Enforced SHA-256 metadata matching on `Complete Upload` callback.

## 5. Secrets Management

- **Evaluation**:
  - *Kubernetes Secrets*: Base64 encoded (not encrypted at rest without specific KMS configuration). Insufficient for Enterprise.
  - *External Secrets Operator (ESO)*: Syncs secrets from external KMS (AWS Secrets Manager, Azure KeyVault) into native K8s secrets.
  - *HashiCorp Vault*: Highly robust, allows dynamic secrets, but high operational overhead.
- **Decision**: **External Secrets Operator** is recommended as the baseline. It integrates natively with cloud providers while preventing hardcoded `.env` files.

## 6. Networking

- **Namespaces**: Logical isolation (e.g., `abast-gp-prod`, `abast-gp-staging`).
- **Services**: `ClusterIP` for internal routing.
- **Ingress**: NGINX Ingress Controller or Cloud Native ALB/Gateway API to handle TLS termination.
- **Network Policies**: Default Deny-All policy. Whitelist API -> DB, API -> Redis, Worker -> Redis. Prevent Worker -> API direct communication.

## 7. Observability

- **Stack**: kube-prometheus-stack (Prometheus Operator, Grafana, Alertmanager).
- **Metrics**:
  - *Kubernetes*: CPU, Mem, Network IO per pod.
  - *Application (FastAPI)*: Request latency, error rates (HTTP 5xx, 4xx).
  - *OCR Metrics*: `ocr_processing_duration_seconds`, `workspace_materialization_seconds`.
  - *Storage*: `storage_errors_total`, `checksum_failures_total`.

## 8. Migration Strategy

- **Phase 1: Docker Compose Certified** (Current). Validation of pure business logic and storage abstractions.
- **Phase 2: Kubernetes Staging**. Deploying the K8s manifests in a non-production cluster to tune KEDA and HPA thresholds.
- **Phase 3: Progressive Rollout (Canary/Blue-Green)**. Traffic shadowing to validate the API performance. Dual writing to local storage and Object Storage (Optional, though V6 completely moves to Object Storage).
- **Phase 4: Production**. 100% traffic shift.
- **Rollback**: In the event of catastrophic failure, because V6 avoids data migration of old assets initially, traffic can be redirected back to the V5.5 infrastructure.
