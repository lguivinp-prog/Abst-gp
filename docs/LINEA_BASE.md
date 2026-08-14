# Línea Base (Auditoría Forense)

## 1. Veredicto AWS: Independencia On-Premise
El proyecto **SÍ** puede funcionar totalmente aislado de AWS. 
- **Módulo `botocore` / `boto3`:** Las importaciones en `backend/app/storage/object.py` (línea 6) son, en tiempo de ejecución, **código muerto** bajo la configuración por defecto. El adaptador S3 solo se activa si la variable de entorno `STORAGE_BACKEND` se establece en `object_storage`. Por defecto es `local`.
- **Archivos Terraform (`.tf`):** Toda la carpeta `terraform/` (con recursos como `aws_eks_cluster`, `aws_s3_bucket`, `aws_kms_key`) es un residuo de Infraestructura como Código (IaC) de un despliegue anterior. Se puede eliminar sin afectar el código de la aplicación local.

## 2. Almacenamiento de Archivos (PDFs)
Los archivos **se almacenan en el disco local**.
- **Evidencia:** `backend/app/core/config.py` define `STORAGE_BACKEND: str = os.getenv("STORAGE_BACKEND", "local")`. Además, en `docker-compose.yml`, el directorio local se monta sobre el contenedor mediante el volumen `uploads:/data/uploads`. El código hace uso del `LocalStorageAdapter`.

## 3. Smoke Test del Camino Feliz
El proceso se rompe en el **primer paso**.
- **Paso Exacto de Ruptura:** Subida del PDF por la API (`POST /cases/{case_id}/requirement/upload`).
- **Error Textual:** `401 Unauthorized` (`{"detail": "Not authenticated"}`).
- **Análisis Forense:** El endpoint exige un JWT válido. Para emitirlo, necesitamos un usuario en BD (ej: script `seed_dev_users.py`). Sin embargo, **la base de datos está completamente vacía (0 tablas)** porque `alembic upgrade head` aborta y hace *rollback* debido a: `psycopg2.errors.DuplicateTable: relation "generated_outputs" already exists`. Esto confirma que el conflicto `v6 vs domain` impide inicializar el sistema local.
- **Tabla PAPEL BOND:** No producida (no llegó a procesar).

## 4. Suite de Monitoreo
En `docker-compose.yml` levantan:
- **Prometheus** (raspado de métricas).
- **Grafana** (dashboards visuales).
- **Alertmanager** (alertas).
- **SRE-Exporter** (exportador de métricas custom).
**Ninguno es requisito funcional.** La aplicación no depende de ellos de forma síncrona; el monitoreo es pasivo (pull-based). Se pueden apagar para ahorrar recursos sin romper el backend.

## 5. Propuesta de Arquitectura Frontend (Sin Node local)
Para que el cliente on-premise no requiera Node en su servidor host, se propone empaquetar el frontend con un `Dockerfile` multi-etapa que construya con Node internamente y sirva con Nginx:

**Propuesta `frontend/Dockerfile` (NO aplicada):**
```dockerfile
# Etapa 1: Build
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

# Etapa 2: Serve
FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
```

**Propuesta para `docker-compose.yml`:**
```yaml
  frontend:
    build:
      context: ./frontend
    ports:
      - "3000:80"
    depends_on:
      - abst_api
```
*(Se usaría un comando diferente, p.ej. `npm run dev`, en caso de querer modo desarrollo con hot-reload mapeando el volumen `.:/app`)*.
