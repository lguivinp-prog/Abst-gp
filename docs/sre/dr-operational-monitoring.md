# PROPUESTA DE MONITOREO OPERACIONAL CONTINUO SRE (DISASTER RECOVERY)

**Plataforma**: Abst-gp (Document Intelligence & OCR Pipeline V5.5 / V5.6)  
**Módulo**: SRE Observability & DR Telemetry Framework  
**Fecha**: 2026-08-08  
**Clasificación**: Propuesta Operacional / Transición a Producción Enterprise  

---

## 1. OBJETIVO DEL MONITOREO OPERACIONAL SRE

Garantizar la visibilidad en tiempo real del estado de salud de todos los componentes de persistencia, brokers asíncronos, almacenamiento documental y colas de trabajo, permitiendo detectar desviaciones antes de que se conviertan en incidentes y asegurando que las capacidades de Disaster Recovery cumplan continuamente los SLAs (RPO $\le 300\text{ s}$, RTO $\le 900\text{ s}$).

---

## 2. MATRIZ DE MÉTRICAS OPERACIONALES POR SUBSISTEMA

### A. PostgreSQL 16 (SSOT & Replicación Física)

| Métrica Prometheus / OpenTelemetry | Tipo | Umbral de Alerta (Warning / Critical) | Acción Operativa Recomendada |
| :--- | :--- | :--- | :--- |
| `abst_postgres_wal_archive_lag_seconds` | Gauge | **Warn**: $> 60\text{ s}$<br>**Crit**: $> 180\text{ s}$ | Verificar ancho de banda y permisos en el storage de archivado de WAL. |
| `abst_postgres_last_successful_backup_timestamp` | Timestamp | **Warn**: $> 24\text{ h}$<br>**Crit**: $> 36\text{ h}$ | Disparar backup físico de emergencia (`pg_basebackup`) y auditar cron SRE. |
| `abst_postgres_last_pitr_validation_status` | Binary / Gauge | **Crit**: $0$ (Fallo en último simulacro PITR) | Revisar integridad de la cadena de WALs y scripts de replay. |
| `abst_postgres_replication_lag_bytes` | Gauge | **Warn**: $> 64\text{ MB}$<br>**Crit**: $> 256\text{ MB}$ | Inspeccionar saturación de red o contención I/O en réplicas. |

### B. Redis 7 (Capa de Transporte Efímero)

| Métrica Prometheus / OpenTelemetry | Tipo | Umbral de Alerta (Warning / Critical) | Acción Operativa Recomendada |
| :--- | :--- | :--- | :--- |
| `abst_redis_availability_ratio` | Gauge (0..1) | **Crit**: $< 0.999$ | Reiniciar contenedor / pod Redis y verificar conectividad de socket. |
| `abst_redis_rebuild_duration_seconds` | Histogram | **Warn**: $> 5.0\text{ s}$<br>**Crit**: $> 15.0\text{ s}$ | Evaluar volumen de jobs activos en PostgreSQL e índices de reconciliación. |
| `abst_redis_orphan_keys_detected` | Counter | **Warn**: $> 0$ | Ejecutar script de reconciliación `rebuild_redis.py --sync-from-db`. |

### C. Workers Asíncronos & `JobRecoveryEngine`

| Métrica Prometheus / OpenTelemetry | Tipo | Umbral de Alerta (Warning / Critical) | Acción Operativa Recomendada |
| :--- | :--- | :--- | :--- |
| `abst_worker_stale_jobs_count` | Gauge | **Warn**: $> 5$<br>**Crit**: $> 20$ | Forzar ejecución del `JobRecoveryEngine` para reencolar a `QUEUED`. |
| `abst_worker_heartbeat_timeout_seconds` | Gauge | **Warn**: $> 60\text{ s}$<br>**Crit**: $> 120\text{ s}$ | Reiniciar workers sin respuesta e inspeccionar saturación de CPU/RAM. |
| `abst_job_processing_duration_seconds` | Histogram | **Warn**: $p95 > 180\text{ s}$<br>**Crit**: $p99 > 300\text{ s}$ | Escalar horizontalmente el pool de workers OCR. |

### D. Almacenamiento Documental (Vault / Blob Storage)

| Métrica Prometheus / OpenTelemetry | Tipo | Umbral de Alerta (Warning / Critical) | Acción Operativa Recomendada |
| :--- | :--- | :--- | :--- |
| `abst_document_checksum_mismatch_count` | Counter | **Crit**: $> 0$ | Aislar documento afectado y restaurar copia inmutable desde backup vault. |
| `abst_document_orphan_files_count` | Gauge | **Warn**: $> 10$<br>**Crit**: $> 50$ | Ejecutar script de auditoría `validate_documents.py --clean-orphans`. |
| `abst_storage_available_capacity_ratio` | Gauge (0..1) | **Warn**: $< 0.20$ (20%)<br>**Crit**: $< 0.10$ (10%) | Aprovisionar espacio en volumen o activar auto-escalado de storage. |

---

## 3. ARQUITECTURA DE ALERTAMIENTO Y DASHBOARDS (GRAFANA)

### Dashboard Recomendado: *Abst-gp Enterprise DR & Persistence Health*
1. **Panel Superior (SLA Status)**:
   - Indicador en tiempo real de RPO Actual Estimado (Lag WAL actual).
   - Indicador de RTO Estimado (Tiempo promedio del último simulacro de recuperación).
2. **Panel de Base de Datos**:
   - Tasa de generación de WALs (MB/min).
   - Estado de salud del cluster PostgreSQL 16 y conexiones activas.
3. **Panel de Almacenamiento e Integridad**:
   - Gráfico de verificación diaria de sumas SHA-256 de documentos.
   - Total de documentos respaldados vs. total registrados en base de datos.
4. **Panel de Workers & Colas**:
   - Tasa de trabajos procesados por minuto por tipo (`OCR`, `COMPARISON`, `QUOTATION`).
   - Conteo de transiciones de rescate automáticas (`JobRecoveryEngine`).

---

## 4. PLAN DE SIMULACROS CONTINUOS (SRE CHAOS & DR DRILLS)

Para mantener la certificación DR activa durante la fase de producción, se establece el siguiente cronograma de simulacros periódicos:

- **Semanal**: Verificación automatizada de integridad de backups (`pg_verifybackup` sobre snapshot más reciente).
- **Mensual**: Simulación no destructiva de Point-In-Time Recovery (PITR) en ambiente de staging.
- **Trimestral**: Drill de caída forzada de worker con validación de rescate de jobs en curso.
- **Semestral**: Rotación formal de claves HMAC de firmado y simulación de desastre mayor con failover completo.
