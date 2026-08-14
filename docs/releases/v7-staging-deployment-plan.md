# Staging Deployment Plan

## Selected Option
**PENDING AUTHORIZATION**

## Environment Topology
- Ingress ALB/Nginx con SSL.
- Gateway FastAPI (2 pods).
- Celery Worker (2 pods).
- RDS PostgreSQL 16 + pgvector.
- ElastiCache Redis.

## Networking
- VPC Aislada, sin acceso a base de datos de producción.

## Artifact Manifest
- Gateway: `abst_api@<digest_pendiente>`
- Worker: `abst_worker@<digest_pendiente>`
- PostgreSQL: `ankane/pgvector:latest@sha256:7f950...`
- Redis: `redis:7-alpine@sha256:4d872...`

## Configuration
- `max_signal_age = 5000ms`
- Hysteresis configurada para fail-closed.

## Security
- `app_service_role` restringido. Sin Superuser. RLS activado.

## Observability
- Exportador SRE activo (`abst_sre_exporter`). Logs sin secrets ni PII.

## Rollback
- Scripts listos para: `rollback_tenant`, `rollback_wave`, `rollback_global`.

## Cleanup
- Entorno debe destruirse tras GO_FOR_PRODUCTION (o tras expirar la ventana de prueba autorizada).

## Cost Estimate
- Pendiente de decisión (Option A vs C).

## Authorization Required
- Se requiere presupuesto y luz verde técnica.
