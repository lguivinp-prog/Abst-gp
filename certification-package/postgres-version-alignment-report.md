# INFORME DE ALINEACIÓN DE VERSIONES POSTGRESQL (FASE FINAL: HARDENING ENTERPRISE)

**Plataforma**: Abst-gp (Document Intelligence & OCR Pipeline)  
**Fecha**: 2026-08-08  
**Área**: SRE / Database Administration / Enterprise Architecture  
**Estado**: REVISADO Y ALINEADO  

---

## 1. ESTADO Y VERSIONES DETECTADAS (DIAGNÓSTICO)

Durante la auditoría de hardening previa al cierre formal de Disaster Recovery (Fase 7.4-C), se detectó una divergencia crítica en la declaración de versiones de PostgreSQL a lo largo de los entornos del repositorio:

| Componente / Archivo | Versión Declarada Anteriormente | Versión Actual Alineada | Rol en la Plataforma |
| :--- | :--- | :--- | :--- |
| `docker-compose.yml` | `postgres:15-alpine` | `postgres:16-alpine` | Despliegue productivo local / base |
| `docker-compose.test.yml` | Implícita / sin tag explícito | `postgres:16-alpine` | Entorno de pruebas Ring 1 |
| `verification/docker-compose.dr.yml` | `postgres:16-alpine` | `postgres:16-alpine` | Infraestructura Disaster Recovery Fase 7.4 |
| `Dockerfile.backend.test` | `postgresql-client-16` / `postgresql-16` | `postgresql-client-16` | Contenedor de ejecución DR y validación |
| `verification/dr/create_backup.py` | `server_version_num >= 160000` | `server_version_num >= 160000` | Motor de Physical Base Backup y PITR |
| `docs/runbooks/disaster-recovery.md` | `PostgreSQL 16 como SSOT` | `PostgreSQL 16 como SSOT` | Runbook formal SRE |

---

## 2. ANÁLISIS DE RIESGOS TÉCNICOS Y OPERACIONALES

La coexistencia de PostgreSQL 15 en producción con herramientas y estándares DR diseñados exclusivamente para PostgreSQL 16 introducía los siguientes riesgos críticos:

1. **Incompatibilidad Binaria en Backups Físicos (`pg_basebackup` / `pg_verifybackup`):**
   - El formato interno de archivos de datos (`PG_VERSION`) y el formato del archivo `backup_manifest` difieren entre las versiones mayores 15 y 16.
   - Un backup físico generado desde un cluster PostgreSQL 15 no puede ser verificado ni restaurado utilizando binarios de PostgreSQL 16 sin provocar un fallo inmediato (`FATAL: database files are incompatible with server`).
2. **Incompatibilidad de Registros WAL (Write-Ahead Logging):**
   - El formato de los registros WAL en PostgreSQL 16 incluye mejoras estructurales y cambios en el encabezado respecto a PostgreSQL 15. Un standby o réplica basada en stream de WAL fallaría si los motores no comparten la misma versión mayor.
3. **Rechazo Categórico en Compuertas de Certificación DR:**
   - La función canónica `verify_postgresql_16_server()` en `verification/dr/create_backup.py` rechaza explícitamente cualquier servidor con versión mayor diferente a 16 (`POSTGRESQL_VERSION_MISMATCH`). Si producción operase en PG 15, los backups automatizados fallarían de forma sistemática.

---

## 3. OPCIÓN RECOMENDADA

**Estandarización Total en PostgreSQL 16 (`postgres:16-alpine`)**

- **Justificación**:
  - PostgreSQL 16 ofrece soporte nativo avanzado para streaming de WAL comprimido, verificación criptográfica con `pg_verifybackup`, autenticación robusta `SCRAM-SHA-256` por defecto y optimizaciones sustanciales en concurrencia y consultas particionadas.
  - La suite de certificación DR Fase 7.4-C (Gates A a I) ha sido validada y probada al 100% sobre PostgreSQL 16.14.

---

## 4. PLAN DE ALINEACIÓN Y MIGRACIÓN

### Fase 1: Alineación de Infraestructura y Contenedores (EJECUTADO)
- Actualización de `docker-compose.yml` para fijar `image: postgres:16-alpine`.
- Actualización de `docker-compose.test.yml` fijando explícitamente `image: postgres:16-alpine`.
- Verificación de consistencia con `verification/docker-compose.dr.yml` y `Dockerfile.backend.test`.

### Fase 2: Procedimiento de Migración de Datos para Instancias Existentes (Producción)
Para clusters productivos actualmente corriendo en PostgreSQL 15 que requieran actualización a 16:
1. **Generación de Dump Lógico Completo Previo**:
   ```bash
   pg_dumpall -h localhost -p 5432 -U abst_user --clean --if-exists > /backup/pre_upgrade_dump_pg15.sql
   ```
2. **Actualización mediante `pg_upgrade` o Migración Asistida por Dump**:
   - Detener el contenedor de PostgreSQL 15.
   - Reemplazar volumen o migrar directorio de datos mediante `pg_upgrade` con binarios 15 y 16.
   - En despliegues containerizados estándar, iniciar `postgres:16-alpine` con volumen limpio e importar:
     ```bash
     psql -h localhost -p 5432 -U abst_user -d abst_gp -f /backup/pre_upgrade_dump_pg15.sql
     ```
3. **Re-indexación y Análisis Post-Migración**:
   ```sql
   VACUUM FREEZE ANALYZE;
   REINDEX DATABASE abst_gp;
   ```
4. **Validación de Integridad**:
   - Ejecutar `python -m verification.dr.validate_database`.
   - Ejecutar `python -m verification.dr.validate_documents`.

---

## 5. CONCLUSIÓN

La divergencia de versiones ha sido mitigada en el código fuente y las plantillas de orquestación Docker. Toda la plataforma Abst-gp opera de forma homogénea sobre **PostgreSQL 16**.
