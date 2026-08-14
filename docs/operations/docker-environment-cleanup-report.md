# Docker Environment Cleanup Report

This report evaluates the current state of the local Docker environment, classifying resources into categories based on their relation to the certified Abst-gp V5.5 baseline and the ongoing V6.0 evolution.

## A) Mantener (Keep)
These resources belong to the active Abst-gp project, current certification layers, or active testing environments for V6.0.
- **Projects**: `verification`
- **Containers**:
  - `verification-backend-dr-run-*` (Active V6 validation runs)
  - `verification-redis-dr-1`
  - `verification-db-dr-1`
  - `verification-minio-1` (Object Storage baseline)
- **Volumes**:
  - `verification_dr-backup-vault`
  - `verification_dr-db-data`
  - `verification_dr-redis-data`
  - `verification_dr-uploads`
  - `verification_dr-wal-archive`
  - `verification_minio_data`
  - `abst-v4_9-remediation-clean_pgdata`
  - `abst-v4_9-remediation-clean_redisdata`
  - `abst-v4_9-remediation-clean_uploads`

## B) Detener (Stop)
Legacy environments currently consuming CPU/Memory but not part of the V5.5/V6.0 Abast-gp pipeline.
- **Projects/Containers**:
  - `lg-contrataciones-*` (api, scheduler, redis, postgres, minio, opensearch)

## C) Eliminar (Remove)
Resources that are strictly safe to remove (no certification data, no rollback dependency, no active use).
- **Rule**: We will *only* remove the `lg-contrataciones` containers that have exited weeks ago.
- **Rule**: We will **NOT** run `docker system prune` or `docker volume prune`. We will explicitly use `docker stop` and `docker rm` on the obsolete non-abast containers.

## Risk Assessment
There is **ZERO** risk to the V5.5 Enterprise DR certification because we are strictly ignoring all volumes and containers prefixed with `verification_`, `abst_gp_dr_certification`, and `abst-v4_9-remediation-clean`.

*Prepared for V6.0-N+ Readiness Phase.*
