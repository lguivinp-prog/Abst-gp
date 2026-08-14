# ABST-GP V6.0: CLOUD-NATIVE TARGET ARCHITECTURE DESIGN

**Plataforma**: Abst-gp (Document Intelligence & OCR Pipeline)  
**Fase**: V6.0-A (Diseño Cloud-Native)  
**Fecha**: 2026-08-08  
**Autor**: Equipo de Arquitectura SRE  

---

## 1. ESTRATEGIA DE STORAGE (OBJECT STORAGE)

La migración a una arquitectura nativa de la nube exige abandonar el almacenamiento en volumen de disco local (`/data/uploads`) a favor de un servicio de Object Storage (ej. AWS S3, GCS, Azure Blob).

### A. Migración y Custodia de Metadatos
- **Decisión Arquitectónica**: El motor de PostgreSQL (SSOT) retendrá la custodia absoluta de la metadata (Tenant ID, Checksum, Timestamp). El Object Storage operará estrictamente como un almacenamiento "ciego", enrutado mediante claves UUID.
- **Flujo de Carga (Upload)**: La API no guardará el archivo en disco, sino que generará una firma de URL temporal (Presigned URL) o transmitirá el flujo de bits directamente a S3 en chunks asíncronos.

### B. Estrategia de Checksum (Integridad)
- **Generación en Origen**: El checksum `SHA-256` se calcula en RAM por la API antes de emitir la escritura hacia el Object Storage. Este hash se registra en PostgreSQL de forma transaccional.
- **Validación Asíncrona**: El SRE Pipeline (monitoreado en Grafana) comparará periódicamente el checksum alojado en la DB con el `ETag` / metadata hash nativo del proveedor de Object Storage.

### C. Estrategia de Restore Documental (Disaster Recovery)
- El Disaster Recovery del Object Storage se apoya en replicación nativa Multi-Region o Versionado activo.
- Si la base de datos se corrompe y realiza un Point-In-Time Recovery (PITR), se ejecutará un Job de reconciliación que leerá la DB y enviará una señal de "Soft Delete" o enrutamiento al bucket S3 para asegurar que los documentos "huérfanos" (subidos después de la corrupción de la DB) se manejen adecuadamente.

---

## 2. ORQUESTACIÓN DE WORKERS

La escalabilidad asíncrona es el principal motivador de la versión V6.0.

### A. Deployment y Health Endpoints
- **Sidecar Web**: Dado que los workers RQ son procesos de terminal, se les inyectará un Sidecar HTTP (o un wrapper ASGI ligero) que responda `200 OK` en rutas `/healthz/live` y `/healthz/ready`. 
- Esto permitirá a Kubernetes utilizar sondas de Kubelet y aislar pods de worker que estén muertos o atrapados en un bucle OCR (liveness failure).

### B. OCR Workers y Autoscaling (HPA / KEDA)
- **Decisión Arquitectónica**: Implementar **KEDA** (Kubernetes Event-driven Autoscaling).
- El número de réplicas del `worker-ocr` (Stateful-Heavy) crecerá no basado en el uso de CPU (que siempre será del 100% al procesar), sino basado en la **profundidad de la cola Redis** (`abst_queue_depth`).

---

## 3. EVOLUCIÓN DE POSTGRESQL

PostgreSQL 16 es el núcleo duro (SSOT) certificado bajo normativas de Disaster Recovery estrictas en V5.5. Al migrar a K8s, existen dos enfoques:

### A. Managed PostgreSQL (RDS / Cloud SQL) vs. CloudNativePG (Operator)
- **Evaluación**: Un PostgreSQL administrado por la nube provee PITR nativo "Out-of-the-box" (via snapshots subyacentes), pero reduce el control explícito del equipo SRE sobre el cifrado local de los WALs.
- **Decisión CloudNativePG**: Desplegar la base de datos con un Operator K8s (`CloudNativePG`). Esto permite retener el control completo, donde cada Pod de base de datos orquesta su propio respaldo (pgBackRest) hacia un bucket S3.

### B. Backup y PITR Strategy
- La política de Physical Backup se mantiene (generando un archivo base semanal validado con `pg_verifybackup`).
- El Continuous Archiving de los WALs se enviará directamente a Object Storage. La latencia (medida en V5.6 con la métrica `abst_postgres_wal_archive_lag_seconds`) alertará a SRE si el upload falla, protegiendo el RPO (< 300s).

---

## 4. KUBERNETES DISASTER RECOVERY (NUEVA GENERACIÓN)

Al reemplazar los contenedores de Compose, la certificación de Disaster Recovery (Gates A-I) debe replantearse (V6.0 Certification).

### A. Nuevos Riesgos
- **Desincronización de Estado (Split-Brain)**: Un Network Partition en K8s podría resultar en pods huérfanos intentando procesar colas.
- **PersistentVolume Claim Failure**: Fallos al atachar el almacenamiento del Operator PostgreSQL al nodo físico, dejando a la base de datos sin inicializar.

### B. Nuevos Gates de Certificación
- **Gate J (K8s Namespace Restore)**: Medir el RTO desde que se ejecuta la creación del Namespace DR desde cero hasta que el Operator de Postgres levanta la conexión y extrae los WALs de S3.
- **Gate K (KEDA Autoscaling Rebound)**: Validar que, post-desastre, el HPA encienda a los OCR Workers agresivamente (Scale-out) tras detectar la pila acumulada de trabajos no procesados.

### C. Estrategia de Recuperación (Runbook Target)
1. Iniciar clúster secundario de K8s.
2. Inyectar `ExternalSecrets` (AWS/Vault) usando credenciales maestro.
3. Desplegar manifiestos base (Redis, Deployments, Operator).
4. El Operator lee S3, realiza Restore y declara PITR exitoso.
5. Los Workers leen Redis y el HPA se dispara según la cola.
