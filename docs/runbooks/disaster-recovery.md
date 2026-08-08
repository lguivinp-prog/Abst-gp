# RUNBOOK DE RECUPERACIÓN DE DESASTRES & CONTINUIDAD OPERACIONAL (DR)

**Plataforma**: Abst-gp / Document Intelligence Pipeline  
**Versión**: V5.5 Enterprise Operations  
**Responsables**: SRE Lead, Principal Software Architect, Database Administrator  
**Objetivos Certificados**: RPO $\le$ 5 minutos | RTO $\le$ 15 minutos  

---

## 1. PRINCIPIOS ARQUITECTÓNICOS DE DISASTER RECOVERY

1. **PostgreSQL 16 como SSOT**: Toda la verdad transaccional reside en PostgreSQL. La base de datos es la única fuente autorizada para restaurar el estado del sistema.
2. **Redis 7 como Transporte Efímero**: Redis es volátil y transitorio. Nunca se asume persistencia en Redis; se limpia y reconstruye en cada ciclo de DR.
3. **Validación Criptográfica y Manifiesto Inmutable**: Todo backup físico está respaldado por un archivo `backup-manifest.json` firmado mediante HMAC-SHA256 y un catálogo `backup-checksums.json` de documentos.
4. **Idempotencia en Reconciliación**: El motor `JobRecoveryEngine` reconcilia jobs huérfanos sin producir ejecuciones duplicadas ni alterar estados terminales (`READY`, `FAILED_FINAL`).

---

## 2. MATRIZ DE ESCENARIOS Y TIEMPOS OBJETIVO

| Escenario | Causa Raíz | Procedimiento de Recuperación | RPO Objetivo | RTO Objetivo |
| :--- | :--- | :--- | :--- | :--- |
| **Escenario A: Pérdida Total BD** | Falla de hardware / destrucción de volumen | Restauración de Base Backup Físico + Replay WAL + Snapshot Documental | $\le$ 5 min | $\le$ 15 min |
| **Escenario B: Corrupción Lógica (PITR)** | `DROP/DELETE` accidental o migración errónea | Point-In-Time Recovery al timestamp $T_{\text{target}}$ inmediatamente anterior | $\le$ 1 min | $\le$ 10 min |
| **Escenario C: Backup Corrupto / Inválido** | Falla de checksum o firma HMAC inválida | Detección estricta, alerta `DR_RESTORE_FAILED` y fallback a snapshot previo | $\le$ 5 min | $\le$ 12 min |
| **Escenario D: Pérdida Total de Redis** | Caída de cluster Redis / flush accidental | Reconstrucción limpia de Redis (`FLUSHDB`) y escaneo con `JobRecoveryEngine` | 0 min (SSOT) | $\le$ 2 min |
| **Escenario E: Worker Muerto en `PROCESSING`** | Crash de nodo worker / OOM | `JobRecoveryEngine` detecta heartbeat estancado y transiciona a `QUEUED` con backoff | 0 min | $\le$ 1 min |
| **Escenario F: Documento Faltante / Dañado** | Inconsistencia de filesystem / pérdida de archivo | Validador bidireccional detecta mismatch y restaura desde snapshot documental | 0 min | $\le$ 5 min |
| **Escenario G: Falla de Aislamiento Tenant** | Intento de cruce de datos post-restore | Bloqueo preventivo y validación de `tenant_id` en `validate_database` | 0 min | $\le$ 3 min |

---

## 3. PROCEDIMIENTO OPERATIVO PASO A PASO

### Fase 1: Declaración de Desastre y Contención
1. Declarar incidente en el canal de comando SRE (`#sre-dr-incidents`).
2. Aislar tráfico entrante mediante API Gateway / Load Balancer (activar página de mantenimiento o modo solo lectura).
3. Detener temporalmente los workers de procesamiento (`rq worker` / `celery`).

### Fase 2: Identificación del Punto Objetivo de Recuperación (PITR)
1. Identificar el timestamp exacto del incidente $T_{\text{incident}}$ en UTC.
2. Determinar el timestamp seguro $T_{\text{target}} = T_{\text{incident}} - \Delta t$.
3. Localizar el paquete de backup físico más reciente en el vault seguro (`/data/backup_vault/`).

### Fase 3: Ejecución de la Restauración
1. **Verificar Manifiesto y Checksums**:
   ```bash
   python -m verification.dr.restore_backup latest
   ```
2. **Reconstruir Redis Efímero**:
   ```bash
   python -m verification.dr.rebuild_redis
   ```
3. **Reconciliar Jobs mediante JobRecoveryEngine**:
   ```bash
   python -m verification.dr.reconcile_jobs
   ```

### Fase 4: Compuertas de Validación y Certificación de Integridad
1. **Validación de Base de Datos**:
   ```bash
   python -m verification.dr.validate_database
   ```
2. **Validación Documental Bidireccional**:
   ```bash
   python -m verification.dr.validate_documents
   ```
3. **Medición de RPO / RTO**:
   ```bash
   python -m verification.dr.measure_rpo_rto
   ```

### Fase 5: Reinicio de Servicios y Monitoreo Post-DR
1. Iniciar workers de procesamiento (`abst_worker`).
2. Abrir tráfico en API Gateway.
3. Monitorear dashboards SRE (`/sre/dashboard`) y métricas Prometheus:
   - `abst_dr_restore_total`
   - `abst_dr_reconciliation_total`
   - `abst_active_workers`
   - `abst_active_jobs`
4. Confirmar que no hay alertas activas en `AlertEngine`.
