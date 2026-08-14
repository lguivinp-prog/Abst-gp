# V6 Kubernetes Disaster Recovery Strategy

This document outlines the conceptual Disaster Recovery framework for the Abast-GP V6.0 Kubernetes Enterprise environment. 

> **Important Constraint**: The V5.5 Gates A-I DR certification relied heavily on host-level Docker Compose persistence mechanisms (pg_basebackup on host volumes). A Kubernetes environment requires a modernized approach. We cannot directly reuse Gates A-I; they must be adapted to Cloud Native paradigms.

## 1. Cluster & Namespace Recovery
- **Tooling**: Velero.
- **Strategy**: Regular backups of Kubernetes resources (Deployments, Services, ConfigMaps, Secrets, Ingress) to Object Storage.
- **Recovery Action**: In the event of a total cluster loss, Velero restores the `abast-gp-prod` namespace into a secondary failover cluster.

## 2. Secrets & Configuration Recovery
- **Strategy**: GitOps (ArgoCD / Flux) combined with External Secrets Operator (ESO).
- **Recovery Action**: Configuration is declarative and stored in a secure Git repository. Secrets are restored seamlessly by ESO connecting to the Cloud Provider's KMS (e.g., AWS Secrets Manager).

## 3. PostgreSQL Recovery
- **Managed DB Approach**: Rely on the Cloud Provider's automated snapshots and Point-in-Time Recovery (PITR).
- **CloudNativePG Approach**: Rely on Barman WAL archiving to Object Storage.
- **Recovery Action**: Restore the database to a secondary AZ/Region. Update the application's Secret pointing to the new DB host.

## 4. Object Storage Recovery
- **Strategy**: Cross-Region Replication (CRR) and Bucket Versioning.
- **Recovery Action**: In case of a regional MinIO/S3 outage, application traffic is routed to the replicated bucket in the failover region. Versioning protects against accidental or malicious deletion of documents.

## 5. Worker & Queue Reconciliation
- **Strategy**: Redis Persistence (AOF) + KEDA.
- **Recovery Action**: If a cluster dies mid-processing, pending jobs in Redis are persisted. When the failover cluster boots, KEDA immediately scales the OCR Workers to consume the backlog. Any jobs that were "in-flight" during the crash will time out (visibility timeout) and be returned to the queue for reprocessing, guaranteeing At-Least-Once processing.

## 6. Validation Pipeline (Future Implementation)
The new DR validation suite will simulate Kubernetes chaos:
- Node termination (Chaos Mesh).
- Pod evictions.
- Simulating S3 outages by blocking network traffic to AWS IPs.
- Evaluating the `RTO` for Kubernetes to spin up replacement OCR workers on fresh nodes.
