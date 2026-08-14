# Staging vs Production Delta

*Este documento compara el entorno Cloud de Staging (Minimum Architecture) con la topología de Producción prevista. Las diferencias ayudan a delimitar la representatividad de Staging.*

| Dimension | Staging | Production Intended | Risk | Coverage | Mitigation | Status |
|---|---|---|---|---|---|---|
| Orchestrator | EC2 (t3.medium) + Docker | EKS / ECS | LOW | Networking inter-container. | Docker-compose red emulada. | VALIDATED |
| Database | RDS PostgreSQL 16 Single-AZ | RDS PostgreSQL 16 Multi-AZ | LOW | Compatibilidad SQL y versión de pgvector. | Dataset sintético no requiere HA. | VALIDATED |
| DB Proxy | RDS Proxy (Opcional test) | RDS Proxy | MEDIUM | Connection reuse, pool exhaustion. | Ejecutar pruebas exhaustivas de context leakage. | PENDING |
| Cache | ElastiCache Redis (1 node) | ElastiCache Redis Cluster | MEDIUM | Comandos básicos y pub/sub. | Signal Adapter no depende de topología Cluster. | VALIDATED |
| Ingress | ALB Single-Zone HTTPs | ALB Multi-Zone + WAF | LOW | Terminar TLS, timeout headers. | Carga controlada desde runner. | VALIDATED |
| TLS/mTLS | Certificado de prueba (ACM) | Certificado privado mTLS | UNKNOWN | Ingress forwarding. | Fallback a TLS convencional. | PENDING |
| Observability| CloudWatch Logs base | Datadog/ELK completo | LOW | Detección de fallos en Signal Adapters. | Signal Adapters escriben stdout estructurado. | VALIDATED |
| Backup/DR | Ninguno (Destrucción total 48h) | PITR, Multi-region snapshot | LOW | Backup no forma parte de la prueba actual. | Entorno temporal. | VALIDATED |
| Secrets | AWS Secrets Manager (Base) | KMS + IAM Roles for Service Accounts | MEDIUM | Inyección de variables seguras. | Testing aislado. | PENDING |
