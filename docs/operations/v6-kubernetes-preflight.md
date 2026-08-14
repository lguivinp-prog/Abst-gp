# V6 Kubernetes Preflight Architecture Review

This document serves as the final Architectural Decision Record (ADR) before initializing Kubernetes deployment manifests and Helm charts for Abast-GP V6.0 Cloud Native Pipeline. 

## 1. Local Docker State Validation
The local Docker environment has been surgically sanitized:
- **Status**: `CLEAN`
- **Active Projects**: `verification`, `abst-gp` (V6 base).
- **Legacy Projects**: `lg-contrataciones` legacy components have been safely removed. 
- **Preserved**: All V5.5 DR volumes, Redis data, MinIO objects, and PostgreSQL `pgdata`.

## 2. Kubernetes Target Architecture

The target architecture focuses on decoupling the heavy OCR processing from the API layer to guarantee stability.

- **`backend-api`**: Deployed as a scalable `Deployment` (min 3 replicas) using Horizontal Pod Autoscaler (HPA) targeting 70% CPU / 80% Memory.
- **`worker-general`**: Deployed as a `Deployment` managed by KEDA to process lightweight Redis queue metadata jobs.
- **`ocr-worker-v2`**: Isolated `Deployment` specifically built for heavy PaddleOCR extraction. Scaled by KEDA based on Redis queue depth. Requires nodes with high CPU constraints or GPUs if available.

## 3. PostgreSQL Strategy

A critical decision is managing stateful PostgreSQL in Kubernetes vs consuming it as a managed service.

| Feature | CloudNativePG (Operator) | Managed PostgreSQL (RDS/CloudSQL) |
| :--- | :--- | :--- |
| **DR & RPO/RTO** | Requires Barman S3 archiving. Higher RTO during major cluster crashes. | Multi-AZ sync replication guarantees near zero RPO. Sub-minute RTO for failover. |
| **Backups & WAL**| Operator-managed, requires persistent volumes and S3 integration. | 1-click automated snapshots and 35-day PITR retention. |
| **Operation** | High. Requires SRE expertise for Patroni/Raft consensus and PVC monitoring. | Low (Zero-touch infrastructure). |
| **Complexity** | High complexity inside the K8s cluster. | Extremely low. |

**Decision Recommended**: **Managed PostgreSQL (AWS RDS or equivalent)**. 
*Reasoning*: To focus engineering efforts on the Document Intelligence pipeline rather than stateful DB management. CloudNativePG will be the fallback exclusively for Air-Gapped or On-Premise deployments.

## 4. Storage Strategy

- **Object Storage**: Direct integration with AWS S3 (or MinIO for On-Prem). Buckets isolated via prefixes per `tenant_id`. Implements lifecycle rules to delete `EXPIRED` uncompleted uploads after 24 hours.
- **PVC (Persistent Volume Claims)**: PVCs will only be used for Redis persistence (AOF) if deployed in-cluster, and Prometheus metrics.
- **Temporary OCR Workspace**: The `ocr-worker-v2` pods will use `emptyDir` volumes backed by `Memory` (RAM Disk) to ensure ultra-fast temporary file materialization without introducing EBS/Network-disk latencies.
- **Backups**: Relying on Cross-Region Replication (CRR) for S3 and native bucket versioning.

## 5. Secrets Management

| Mechanism | Description | Security | Operational Overhead |
| :--- | :--- | :--- | :--- |
| **Kubernetes Secrets** | Base64 encoded inside the cluster. | Weak (unless encrypted at rest via KMS). | Very Low. |
| **External Secrets (ESO)**| Syncs from AWS Secrets Manager / Azure KeyVault to K8s secrets natively. | High. | Medium. |
| **HashiCorp Vault** | Dynamic, short-lived credentials with deep identity integrations. | Extremely High. | High. |

**Decision Recommended**: **External Secrets Operator (ESO)**.
*Reasoning*: Provides enterprise-grade security without the extreme operational overhead of running HashiCorp Vault. Prevents `.env` files from leaking into Git or ConfigMaps.

## 6. Deployment Strategy

- **Tooling**: **Helm** combined with **GitOps (ArgoCD)**.
- **Reasoning**: Helm provides the necessary templating for environment-specific variables (Staging vs Prod), while ArgoCD ensures that the cluster state always matches the Git repository, strictly avoiding configuration drift. `Kustomize` is discarded as Helm is more expressive for complex conditional logic in the pipeline.

## 7. Order of Implementation

1. **Phase 1: Infrastructure as Code (Terraform)**: Provision Managed PostgreSQL (RDS), Redis (ElastiCache), and S3 Buckets.
2. **Phase 2: Kubernetes Foundations**: Deploy Kube-Prometheus-Stack, External Secrets Operator, and KEDA.
3. **Phase 3: Helm Chart Creation**: Write the Helm charts for `backend-api` and `ocr-worker-v2`.
4. **Phase 4: ArgoCD Deployment**: Connect GitOps to the cluster to deploy the Helm charts.

## 8. Open Decisions

- **Cloud Provider Selection**: Exact target (AWS vs Azure) is still unconfirmed. (Assuming AWS as baseline for RDS/S3 references).
- **Ingress Architecture**: Load Balancer TLS termination vs Ingress Controller TLS termination.

## 9. Risks Detected

1. **Database Connection Pool Exhaustion**: KEDA scaling `ocr-worker-v2` up to 50 pods could easily exhaust PostgreSQL connection pools. 
   - *Mitigation*: Mandatory use of PgBouncer or RDS Proxy in the target architecture.
2. **Memory Exhaustion on OCR Workspace**: Using `emptyDir` backed by Memory means large 500MB PDFs will consume Pod RAM.
   - *Mitigation*: Strict Memory Limits on the OCR pod and explicit file cleanup in the worker code (already implemented in V2).

## 10. Pre-IaC Architecture Gates

This section defines the mandatory architectural requirements that must be resolved before writing any Infrastructure as Code (Terraform) or Kubernetes Manifests. These gates transform the identified risks into strict operational prerequisites.

### 10.1 Database Connection Management
- **Requirement**: Implementation of **PgBouncer** (in-cluster) or **RDS Proxy** (managed).
- **Context**: KEDA will dynamically scale the `ocr-worker-v2` based on Redis queue depth. If a sudden spike in uploaded documents occurs, KEDA may rapidly spin up 50+ OCR pods. Each pod initiates database connections. Without connection pooling, this behavior will exhaust the PostgreSQL max_connections limit, causing cascading outages across the API and other workers.
- **Strategy**: Configure the backend API and all workers to communicate *only* through the connection pooler rather than directly to the DB endpoint.

### 10.2 OCR Worker Resource Governance
- **Requirement**: Strict pod resource limits and graceful large-file handling.
- **Resource Constraints**:
  - `requests`: CPU: 1000m, Memory: 1Gi, Ephemeral-Storage: 1Gi.
  - `limits`: CPU: 4000m, Memory: 4Gi, Ephemeral-Storage: 4Gi.
- **Context**: We selected `emptyDir` backed by `Memory` for the OCR workspace to maximize disk I/O speeds (RAM disk). However, processing extremely large files (e.g., 500MB+ PDFs) in memory could trigger OOMKills on the pod.
- **Strategy for Large PDFs**:
  1. Controlled Rejection: Enforce hard upload limits at the API layer (e.g., max 100MB per file).
  2. Alternative Workspace: If 500MB+ files are a business requirement, fallback to standard NVMe-backed Ephemeral Storage for the workspace instead of `Memory` to prevent Pod eviction.
  3. Streaming: Avoid holding the entire extracted payload in memory; stream results directly to Object Storage.

### 10.3 Cloud Provider Decision Gate
- **Decision Pending**: **AWS (EKS)** vs **Azure (AKS)**.
- **Comparison Factors**:
  - **Kubernetes Service**: EKS requires manual addon management (VPC CNI, CoreDNS), whereas AKS provides deeper native integration and automated upgrades.
  - **Managed PostgreSQL**: AWS RDS vs Azure Database for PostgreSQL Flexible Server.
  - **Object Storage**: AWS S3 vs Azure Blob Storage (impacts botocore/boto3 dependency in our backend).
  - **Secrets**: AWS Secrets Manager vs Azure KeyVault (impacts External Secrets Operator provider).
  - **Load Balancer**: AWS ALB Controller vs Azure Application Gateway.
  - **Observability**: AWS CloudWatch integration vs Azure Monitor.
- **Requirement**: The CTO must formally sign off on the Cloud Provider to define the IaC provider modules.

### 10.4 TLS Termination Decision
- **Decision Pending**: Where should the SSL/TLS certificates reside?
- **Alternatives**:
  1. **Cloud Load Balancer Termination**: The AWS ALB or Azure AppGateway handles the certificates (via ACM or KeyVault). Traffic inside the cluster is unencrypted HTTP. (Lower operational burden).
  2. **Kubernetes Ingress Termination**: The Cloud Load Balancer passes through TCP port 443 directly to an NGINX Ingress Controller inside the cluster, which uses cert-manager to handle Let's Encrypt certificates. (Higher operational burden, higher internal security).
- **Requirement**: Define termination point to write the correct Terraform networking blocks.

*Conclusion: The preflight architectural review is complete and gated. We are clear to proceed with IaC generation once the above decisions are confirmed.*

## 11. Environment Topology Gate

This gate establishes the final structural rules for multi-environment deployments (`dev`, `staging`, `production`) and Terraform state management before initiating the Infrastructure as Code (IaC) design phase.

### 11.1 Environment Strategy
The pipeline must support full isolation between environments to guarantee zero blast radius from non-production workloads.

**Comparison by Provider:**
- **AWS Strategy**:
  - **Accounts**: Strict multi-account strategy (e.g., `abast-gp-dev`, `abast-gp-prod`) using AWS Organizations to prevent limit exhaustion and IAM cross-contamination.
  - **VPC Strategy**: One VPC per environment/account.
  - **Terraform Isolation**: Separate S3 state buckets and DynamoDB lock tables per account.
- **Azure Strategy**:
  - **Subscriptions/Resource Groups**: Use separate Subscriptions for Prod vs Non-Prod, and distinct Resource Groups (`rg-abast-gp-dev`, `rg-abast-gp-prod`) within them.
  - **Terraform Isolation**: Separate Storage Account containers with Blob Leases for locking per environment.

### 11.2 Terraform State Strategy
Regardless of the cloud provider, the following rules apply to IaC state:
- **Remote Backend**: Local state execution is strictly prohibited. State must be remote (S3/DynamoDB or Azure Blob Storage).
- **State Separation**: The state must be split into logical components (e.g., `network.tfstate`, `data.tfstate`, `eks.tfstate`) to reduce blast radius during applies.
- **Locking**: Native state locking must be enabled.
- **Accidental Destruction Protection**:
  - Terraform state buckets must have **Versioning** enabled and **MFA Delete** / **Resource Locks**.
  - Critical databases (RDS/Flexible Server) must have `prevent_destroy = true` lifecycle blocks.

### 11.3 Cloud Provider Dependencies (Still Open)
The IaC design is currently blocked pending the final CTO decision on:
- **AWS EKS vs Azure AKS** (Determines the entire IaC module tree).
- **TLS Termination Choice** (Determines if we provision an ALB/AppGateway in IaC or just a pure L4 Network Load Balancer).

### 11.4 Database Proxy Alignment
To resolve the Connection Management gate (10.1), the IaC must provision the correct tool based on the provider:
- **AWS**: Terraform will provision **AWS RDS Proxy**, eliminating the need for in-cluster PgBouncer.
- **Azure/Agnostic**: Terraform will provision the required IAM/OIDC roles, but the Kubernetes manifest phase must deploy **PgBouncer** in-cluster via Helm, as Azure Flexible Server lacks a native drop-in proxy equivalent to RDS Proxy for KEDA scaling.
