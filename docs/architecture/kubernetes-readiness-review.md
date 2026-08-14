# KUBERNETES READINESS ASSESSMENT

**Plataforma**: Abst-gp (Document Intelligence & OCR Pipeline)  
**Versión**: V5.6-F (Enterprise Production Readiness)  
**Fecha**: 2026-08-08  
**Clasificación**: Diseño de Arquitectura Cloud-Native  

---

## 1. ESTADO ACTUAL Y SERVICIOS DESPLEGADOS

Actualmente, el ecosistema Abst-gp opera sobre `docker-compose` con una certificación técnica de Disaster Recovery (V5.5) y un stack consolidado de observabilidad (V5.6). Los componentes identificados para la evaluación son:

### 1.1 Core Business y Procesamiento
- **api**: FastAPI backend transaccional (Stateless).
- **worker**: RQ worker estándar para tareas de procesamiento ligero (Stateless).
- **worker-ocr**: RQ worker intensivo con dependencias de machine learning y volúmenes montados (`/models`, `/uploads`) (Stateful-Heavy).

### 1.2 Persistencia (DR Scope)
- **postgres**: PostgreSQL 16 (SSOT). Posee altos requisitos de persistencia, backups, y redención en caso de failover.
- **redis**: Redis 7. Actúa como broker efímero.

### 1.3 SRE Control Plane (Observability)
- **sre-exporter**: Python sidecar. Recolecta métricas con latencia estricta.
- **prometheus**: Almacenamiento TSDB (Stateful).
- **alertmanager**: Enrutamiento de notificaciones.
- **grafana**: Visualización.

---

## 2. REQUISITOS DE PLATAFORMA KUBERNETES (K8s)

### A. Liveness y Readiness Probes
- **api**: Necesita un endpoint estandarizado (`/health/liveness` y `/health/readiness`) que no sature la DB. **Gap**: Garantizar que el probe actual responda en <2s para evitar *Kill* prematuro por el Kubelet.
- **workers / worker-ocr**: Tradicionalmente difíciles de sondear vía HTTP. **Gap**: Implementar un probe basado en comandos (e.g. `rq info` adaptado) o un sidecar web ligero para medir saturación y evitar el enrutamiento de nuevos jobs si el pod está bloqueado.

### B. Persistent Storage Needs (PVCs)
- **postgres**: `StatefulSet` mandatorio. Requerirá un `StorageClass` de alto IOPS y políticas `Retain`.
- **prometheus**: `StatefulSet` recomendado para la retención del TSDB.
- **worker-ocr**: El volumen compartido `/uploads` requerirá `ReadWriteMany` (RWX) (por ejemplo, NFS/EFS) si se escala horizontalmente a múltiples réplicas (múltiples pods), o bien migrar a S3/ObjectStorage para desacoplar el estado local. **Risk & Gap Crítico**.

### C. ConfigMaps y Secrets
- **Actual**: `.env` estático y variables pasadas en Compose.
- **Objetivo**: Integrar `ExternalSecrets` (AWS Secrets Manager / HashiCorp Vault) para `POSTGRES_PASSWORD`, `SECRET_KEY`, `GF_SECURITY_ADMIN_PASSWORD` y claves HMAC del DR.

### D. Network Policies
- **Aislamiento**: `worker` y `worker-ocr` no deben recibir tráfico Ingress externo.
- **SRE**: `prometheus` debe tener una policy de ingress que solo le permita hacer scrape a los pods etiquetados en el plano de control y `sre-exporter`. `sre-exporter` solo debe alcanzar a la base de datos `postgres` (puerto 5432).

---

## 3. IDENTIFICACIÓN DE GAPS Y RIESGOS

| Componente / Concepto | Riesgo / Gap Identificado | Nivel de Severidad |
| :--- | :--- | :--- |
| **Worker-OCR (State)** | Escalabilidad limitada por requerimiento de File System local compartido (`/data/uploads`). Migración a Kubernetes exigirá `ReadWriteMany` lo cual penaliza el I/O en lectura de imágenes masivas, o migración del código a Object Storage. | CRÍTICO |
| **PostgreSQL (DR)** | La certificación DR actual asume acceso directo al disco local para validación y re-escritura. Trasladar la certificación DR V5.5 a Kubernetes obligará a rediseñar cómo SRE ejecuta el restore (e.g. usando CloudNativePG o Postgres Operator). | ALTO |
| **Probes Asíncronos** | Workers no exponen puertos HTTP. Kubernetes no sabrá de forma nativa si un OCR está trabado procesando una imagen gigante, dificultando el *Horizontal Pod Autoscaler* (HPA) seguro. | MEDIO |

---

## 4. ESTRATEGIA DE MIGRACIÓN (PROPUESTA FUTURA V6.0)

1. **Fase I - Desacoplamiento (Statelessing)**: Migrar el acceso documental en `worker-ocr` y `api` desde I/O a disco local (`/data/uploads`) hacia Object Storage nativo de nube (S3, GCS).
2. **Fase II - Refactor SRE/DR**: Ajustar los flujos de Disaster Recovery (certificados en la V5.5) para que operen utilizando Operators en Kubernetes (ej. CloudNativePG) en lugar de rutinas `docker-compose`.
3. **Fase III - Despliegue de Plano K8s (Helm/Kustomize)**: Modularizar la API y los workers en `Deployments`, las bases de datos en `StatefulSets` y orquestar métricas mediante `ServiceMonitors`.

*NOTA: Actualmente, ninguna de estas fases se ejecutará hasta que el CTO emita la orden para la versión V6.0.*
