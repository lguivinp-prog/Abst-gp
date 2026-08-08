# INFORME OBLIGATORIO DE ETAPA 0: EVALUACIÓN FACTUAL DEL REPOSITORIO

**Fase:** FASE 7.4 — Disaster Recovery, Business Continuity & RPO/RTO Certification  
**Etapa:** ETAPA 0 — Evaluación Factual del Repositorio (Non-Destructive Baseline)  
**Fecha/Hora:** 2026-08-06T15:55:50Z (UTC)  
**Estado:** `PASS` (Evaluación de Etapa 0 completada con éxito)  
**Compuertas Fase 7.4:** `NOT MEASURED` (Conforme a las reglas de Etapa 0)

---

## 1. Ruta Raíz Canónica
- **Ruta:** `C:/Users/PC/Documents/AbastLG/abst-v4_9-remediation-clean`
- **Clasificación:** `OBSERVED` / `EXECUTED` (Salida de `git rev-parse --show-toplevel`, Exit Code: 0)

## 2. Rama Actual
- **Rama:** `feature/phase5-ring1`
- **Clasificación:** `OBSERVED` / `EXECUTED` (Salida de `git branch --show-current`, Exit Code: 0)

## 3. Commit HEAD
- **Commit:** `38ea7f715fad6ab5a9b700d316e0b15052507c8a`
- **Mensaje:** `Apply V4.8.1 Release Candidate Patch`
- **Fecha:** `2026-07-25T09:15:19-05:00`
- **Clasificación:** `OBSERVED` / `EXECUTED` (Salida de `git rev-parse HEAD`, Exit Code: 0)

## 4. `git status`
- **Estado:** `ahead 1` respecto a `origin/feature/phase5-ring1`.
- **Archivos Modificados/Eliminados:** 28 archivos rastreados (backend, alembic, frontend).
- **Archivos Untracked:** Directorios y archivos de remediación y verificación (`artifacts/`, `verification/`, `docs/`, `backend/tests/dr/`, etc.).
- **Clasificación:** `OBSERVED` / `EXECUTED` (Salida de `git status --short --branch`, Exit Code: 0)

## 5. Últimos 15 Commits
- `38ea7f7` (2026-07-25): Apply V4.8.1 Release Candidate Patch
- `827c19f` (2026-07-19): Fix quarantine backup table sequences and clean up old tests
- `23394dd` (2026-07-18): Correct quarantine migration and clean up temp files
- `754b4ce` (2026-07-17): Fix document_id migration, constraints and comparison engine
- `8d9157f` (2026-07-17): docs: add project context and continuity documentation
- `648bb23` (2026-07-17): fix: stabilize OCR V2 integration pipeline and E2E validation
- `92a6be9` (2026-07-16): test: add authz model and migration contract tests
- `364b75e` (2026-07-16): docs(security): finalize authentication and authorization design
- `7daaf34` (2026-07-16): chore: add reportlab to test requirements
- `74fe02a` (2026-07-16): chore: integrate alembic test harness
- `4554fcb` (2026-07-16): test: run integrations against alembic-managed schema
- `25f0510` (2026-07-16): merge: verified core baseline and isolated test harness
- `0ccf034` (2026-07-16): test: add deterministic e2e tests for V1 and V2 and fix schema setup for API tests
- `3f25b27` (2026-07-16): fix: reject empty requirement extraction
- `8ae3527` (2026-07-15): fix: preserve narrative introductions in structure parsing
- **Clasificación:** `OBSERVED` / `EXECUTED` (Salida de `git log -n 15`, Exit Code: 0)

## 6. Estructura Relevante del Repositorio
- `backend/`: Código de backend FastAPI, modelos SQLAlchemy, migraciones Alembic, workers RQ y servicios de arquitectura.
- `backend/app/core/`: `config.py`, `database.py`, `redis.py`, `telemetry.py`.
- `backend/app/services/`: `job_repository.py`, `job_recovery_engine.py`, `capacity_governor.py`, `alert_engine.py`, `monitoring_service.py`.
- `backend/app/worker/`: `ocr_worker_tasks.py`, `quotation_tasks.py`, `comparison_tasks.py`, `fallback_dispatcher.py`, `fallback_monitor.py`.
- `backend/tests/`: Suites `unit/`, `api/`, `performance/`, `dr/`, `e2e/`.
- `verification/`: Scripts de verificación automatizada y Compose de aislamiento (`docker-compose.dr.yml`, `run-dr-gates.ps1`, `dr/`).
- `artifacts/verification/`: Almacén de evidencias y métricas de fases.
- `docs/`: Runbooks y políticas (`docs/runbooks/disaster-recovery.md`, `docs/policies/backup-retention.md`).
- **Clasificación:** `OBSERVED`

## 7. Archivos de Fase 7.4 Existentes
- `verification/docker-compose.dr.yml`
- `verification/run-dr-gates.ps1`
- `verification/dr/create_backup.py`
- `verification/dr/restore_backup.py`
- `verification/dr/validate_database.py`
- `verification/dr/validate_documents.py`
- `verification/dr/rebuild_redis.py`
- `verification/dr/reconcile_jobs.py`
- `verification/dr/measure_rpo_rto.py`
- `verification/dr/generate_report.py`
- `backend/tests/dr/test_disaster_recovery.py`
- `docs/runbooks/disaster-recovery.md`
- `docs/policies/backup-retention.md`
- **Clasificación:** `OBSERVED`

## 8. Tecnología de Backup Existente
- **Implementación Actual:** `verification/dr/create_backup.py` implementa generación de base backup (`pg_dump` con fallback SQL determinista), snapshot comprimido `.tar.gz` de `UPLOADS_DIR`, sincronización de segmentos WAL, y generación de `backup-manifest.json` firmado con `HMAC-SHA256`.
- **Clasificación:** `OBSERVED`

## 9. Configuración PostgreSQL Declarada y Efectiva
- **Declarada en DR Compose:** `postgres:16-alpine`, puertos `5433:5432`, volumen `dr-db-data`.
- **Declarada en Main Compose:** `postgres:15-alpine`, volumen `pgdata`.
- **Parámetros WAL en DR:** `archive_mode=on`, `wal_level=replica`, `archive_command=test ! -f /wal_archive/%f && cp %p /wal_archive/%f`, `archive_timeout=60`.
- **Clasificación:** `OBSERVED`

## 10. Configuración WAL y Archivación
- **Modo:** `archive_mode = on`
- **Nivel:** `wal_level = replica`
- **Directorio de Destino:** `/wal_archive` (mapeado a volumen `dr-wal-archive`)
- **Timeout:** `archive_timeout = 60` (fuerza segmentación WAL al menos cada 60s para garantizar RPO $\le$ 5 min).
- **Clasificación:** `OBSERVED`

## 11. Volúmenes y Rutas Documentales
- **Volúmenes DR:**
  - `dr-db-data`: Almacenamiento PostgreSQL 16.
  - `dr-wal-archive`: Archivo continuo de WAL para PITR.
  - `dr-backup-vault`: Vault inmutable de backups y manifiestos.
  - `dr-redis-data`: Almacenamiento volátil de Redis.
  - `dr-uploads`: Directorio documental `/app/dr_uploads` (PDFs, expedientes).
- **Validación de Rutas:** Prohibición estricta de path traversal, rutas absolutas externas y aislamiento multi-tenant por prefijo de `tenant_id`.
- **Clasificación:** `OBSERVED`

## 12. Archivos Compose
- `docker-compose.yml`: Servicios `redis`, `db`, `api`, `web`, `worker`, `worker-ocr`.
- `verification/docker-compose.dr.yml`: Servicios `db-dr` (PG16 + WAL Archiving), `redis-dr` (Redis 7), `backend-dr`, `worker-dr`.
- `docker-compose.test.yml` / `verification/docker-compose.test.yml`: Entornos de prueba.
- **Clasificación:** `OBSERVED` / `EXECUTED`

## 13. Modelos y Nombres de Tablas Reales
En `backend/app/models/domain.py`:
1. `validation_document_cases` (`ValidationDocumentCase`)
2. `ocr_processing_runs` (`OCRProcessingRun`)
3. `tenants` (`Tenant`)
4. `users` (`User`)
5. `user_tenant_quarantine` (`UserTenantQuarantine`)
6. `system_settings` (`SystemSettings`)
7. `case_files` (`CaseFile`)
8. `uploaded_documents` (`UploadedDocument`)
9. `parsed_sections` (`ParsedSection`)
10. `quotation_extractions` (`QuotationExtraction`)
11. `final_condition_comparisons` (`FinalConditionComparison`)
12. `generated_outputs` (`GeneratedOutput`)
13. `audit_logs` (`AuditLog`)
14. `processing_jobs` (`ProcessingJob`)
15. `processing_metrics` (`ProcessingMetrics`)
16. `worker_heartbeats` (`WorkerHeartbeat`)
17. `comparison_runs` (`ComparisonRun`)
18. `requirement_items` (`RequirementItem`)
19. `comparison_results` (`ComparisonResult`)
20. `rollout_tenant_assignments` (`RolloutTenantAssignment`)
21. `bootstrap_ledger` (`BootstrapLedger`)
- **Clasificación:** `OBSERVED`

## 14. Migraciones y Revisión Alembic
- **Total Revisiones:** 25 migraciones en `backend/alembic/versions/`.
- **Head Actual:** `c4d5e6f7a8b9_phase_7_3_performance_and_governance_indices.py` (agrega índices compuestos para capacidad multi-tenant y optimización de conteos).
- **Clasificación:** `OBSERVED`

## 15. Colas Redis y Workers
- **Broker:** Redis 7 (efímero, transaccionalidad delegada a PostgreSQL).
- **Colas Declaradas:** `default`, `ocr_tasks`, `quotation_tasks`, `comparison_tasks`.
- **Workers:** RQ Workers (`worker`, `worker-ocr`, `worker-dr`) instrumentados con heartbeats periódicos en `worker_heartbeats`.
- **Clasificación:** `OBSERVED`

## 16. Servicios de Jobs, Recovery, Monitoring, Telemetry y Alerting
- `JobRepository`: Capa canónica y única autorizada para mutaciones de estado de `ProcessingJob`.
- `JobRecoveryEngine`: Motor de detección y reconciliación de jobs colgados por caída de workers.
- `TenantCapacityGovernor`: Gobernador de capacidad y anti-starvation multi-tenant.
- `AlertEngine`: Motor de despacho y registro de alertas operacionales y DR.
- `telemetry.py`: Exportador de métricas Prometheus de baja cardinalidad (`abst_dr_backup_total`, `abst_dr_restore_duration_seconds`, etc.).
- **Clasificación:** `OBSERVED`

## 17. Tests y Gates Existentes
- `backend/tests/dr/test_disaster_recovery.py`: Cobertura de Escenarios A a G + Telemetría + Métricas.
- `backend/tests/performance/test_performance_and_capacity.py`: Escenarios de concurrencia y capacidad.
- `backend/tests/e2e/test_full_document_pipeline.py`: Pipeline E2E integral.
- `backend/tests/unit/`: Tests unitarios de todos los componentes.
- **Clasificación:** `OBSERVED`

## 18. Artefactos Históricos
- `artifacts/verification/v5.2.1/`
- `artifacts/verification/v5.3/`
- `artifacts/verification/capacity/`
- `artifacts/verification/dr/`
- **Clasificación:** `OBSERVED`

## 19. Divergencias Respecto del Prompt
1. **Versión de PostgreSQL en Compose Principal:** `docker-compose.yml` tiene `postgres:15-alpine`, mientras `verification/docker-compose.dr.yml` usa `postgres:16-alpine`.
2. **Herramienta de Backup:** La implementación actual utiliza `pg_dump` con snapshot documental y firma HMAC-SHA256, sin tener instalados binarios de `pg_basebackup`, `pgBackRest` o `WAL-G` en el contenedor base.
3. **Estado de Compuertas en Etapa 0:** Todas las compuertas DR permanecen `NOT MEASURED` en este reporte de evaluación.
- **Clasificación:** `OBSERVED`

## 20. Riesgos con Severidad
- **R-01 (Media):** Discrepancia entre PostgreSQL 15 en `docker-compose.yml` y PostgreSQL 16 en DR Compose. *Mitigación:* Estandarizar imagen a `postgres:16-alpine`.
- **R-02 (Media):** Tamaño de volúmenes de respaldo en entornos con alta tasa de ingesta documental. *Mitigación:* Políticas de retención y compresión implementadas en `docs/policies/backup-retention.md`.
- **R-03 (Baja):** Dependencia de Redis como transporte transitorio en reinicios masivos. *Mitigación:* Reconstrucción limpia desde PostgreSQL SSOT vía `JobRecoveryEngine`.
- **Clasificación:** `INFERRED`

## 21. Plan Incremental Corregido
- **Etapa 0 (Completada):** Evaluación factual del repositorio sin modificaciones funcionales (`PASS`).
- **Etapa 1:** Matriz de selección formal de herramientas de backup (`pg_basebackup` vs `pgBackRest` vs `WAL-G` vs `pg_dump`) y diseño arquitectónico formal de archivado WAL y PITR.
- **Etapa 2:** Estandarización de PostgreSQL 16 y validación de comandos de recuperación.
- **Etapa 3:** Ejecución formal de simulacro DR físico con certificación de compuertas A–G y RPO/RTO.
- **Clasificación:** `INFERRED`

## 22. Primer Cambio Pequeño Propuesto
- **Propuesta:** Evaluar la matriz de selección técnica de herramientas de backup (Etapa 1) para determinar si `pg_dump` tarball con WAL archiving es suficiente o si se requiere integrar `pg_basebackup` en la imagen Docker de PostgreSQL 16.
- **Clasificación:** `INFERRED`
