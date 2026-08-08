# AUDITORÍA Y HARDENING DE SEGURIDAD POSTGRESQL (FASE FINAL: HARDENING ENTERPRISE)

**Plataforma**: Abst-gp (Document Intelligence & OCR Pipeline)  
**Fecha**: 2026-08-08  
**Área**: Cybersecurity / Database Security / SRE  
**Estado**: AUDITADO Y CORREGIDO  

---

## 1. REVISIÓN DE CONFIGURACIONES DE AUTENTICACIÓN (`pg_hba.conf`)

### 1.1 Diagnóstico de Hallazgos
Durante la inspección de seguridad en las configuraciones de PostgreSQL, se identificaron directivas inseguras del tipo `trust` que permitían el acceso sin contraseña ni validación de identidad:

- **Hallazgo 1 (`verification/docker-compose.dr.yml`)**:  
  Presencia de la variable de entorno `POSTGRES_HOST_AUTH_METHOD: "trust"`. Esta configuración deshabilitaba la verificación de credenciales para todas las conexiones TCP/IP al motor de base de datos.
- **Hallazgo 2 (`verification/dr/init-replication.sh`)**:  
  El script de inicialización inyectaba directivas `trust` abiertas en `$PGDATA/pg_hba.conf`:
  ```text
  host replication all all trust
  host all all all trust
  ```

### 1.2 Riesgos de Seguridad Asociados a `trust`
1. **Suplantación de Identidad y Acceso No Autorizado:** Cualquier entidad en la red de contenedores podía conectarse como superusuario `postgres` o usuario de aplicación sin suministrar contraseña.
2. **Exfiltración y Manipulación de Datos Multi-Tenant:** Un atacante con acceso a la red interna podría evadir el aislamiento multi-tenant y realizar lecturas/escrituras arbitrarias.
3. **Incumplimiento Normativo:** Viola los lineamientos del CIS PostgreSQL Benchmark, SOC 2 Type II, ISO 27001 y estándares de seguridad bancaria/gubernamental.

---

## 2. MEDIDAS DE REMEDIACIÓN Y HARDENING IMPLEMENTADAS

### 2.1 Eliminación Total del Método `trust`
- Se removió `POSTGRES_HOST_AUTH_METHOD: "trust"` de los archivos de orquestación.
- Se configuró la inicialización segura mediante `POSTGRES_INITDB_ARGS: "--auth-host=scram-sha-256 --auth-local=scram-sha-256"`.
- Se actualizó `verification/dr/init-replication.sh` para requerir estrictamente `scram-sha-256` en todas las entradas añadidas a `pg_hba.conf`.

### 2.2 Política Estándar de `pg_hba.conf` para Entornos Enterprise
La configuración endurecida de control de acceso basada en host para PostgreSQL 16 se estructura de acuerdo a la siguiente política:

```text
# TYPE  DATABASE        USER            ADDRESS                 METHOD
# Conexiones locales por socket UNIX
local   all             postgres                                peer
local   all             all                                     scram-sha-256

# Conexiones de la Aplicación (Red Interna / Subred Docker)
host    abst_gp         abst_user       10.0.0.0/8              scram-sha-256
host    dr_db           dr_user         172.16.0.0/12           scram-sha-256
host    all             all             127.0.0.1/32            scram-sha-256

# Conexiones de Replicación y Backup WAL Streaming
host    replication     replicator      172.16.0.0/12           scram-sha-256
host    replication     all             all                     scram-sha-256

# Denegación por defecto implícita para cualquier otra combinación
```

---

## 3. AUDITORÍA DE USUARIOS Y ASIGNACIÓN DE PRIVILEGIOS MÍNIMOS (LEAST PRIVILEGE)

| Rol / Usuario | Propósito | Privilegios Asignados | Restricciones de Seguridad |
| :--- | :--- | :--- | :--- |
| `postgres` | Superusuario administrativo | Control total del cluster | Prohibido para la conexión del backend web/API. Solo para migraciones y mantenimiento. |
| `abst_user` / `dr_user` | Usuario de aplicación | `CONNECT ON DATABASE`, `USAGE ON SCHEMA public`, `SELECT, INSERT, UPDATE, DELETE` en tablas | Sin permisos de `SUPERUSER` ni `CREATEROLE`. Acceso restringido por tenant en la capa ORM. |
| `replicator` / `dr_backup` | Replicación física y WAL streaming | Rol `REPLICATION`, `LOGIN` | Solo permitido para `pg_basebackup` y herramientas de archivado WAL. |

---

## 4. GESTIÓN DE SECRETOS Y ENCRIPTACIÓN EN TRÁNSITO

1. **Hashing de Contraseñas:** Todas las credenciales en PostgreSQL 16 se almacenan mediante el algoritmo criptográfico `SCRAM-SHA-256` con salt aleatorio e iteraciones seguras.
2. **Protección en Tránsito (TLS/SSL):** En entornos de producción sobre Kubernetes / Cloud IaaS, se exige habilitar `ssl = on` con certificados gestionados por Vault/Cert-Manager.
3. **No Filtración en Manifiestos DR:** El manifiesto de backup criptográfico (`backup-manifest.json`) fue auditado formalmente en el test `test_7_4_a_hmac_manifest_contains_key_id_without_secrets`, garantizando que ninguna contraseña, token o secreto se filtre en los metadatos de respaldo.

---

## 5. CONCLUSIÓN

Las vulnerabilidades asociadas a directivas de autenticación `trust` han sido completamente erradicadas del repositorio. Toda la infraestructura de base de datos cumple con las directrices de seguridad y autenticación `SCRAM-SHA-256` requeridas para la certificación Enterprise.
