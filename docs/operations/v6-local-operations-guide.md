# V6 Local Operations Guide

## 1. Overview
Esta guia detalla los procedimientos operativos para el despliegue del entorno piloto (Local Enterprise) de Abast-gp V6. El sistema esta contenido enteramente en `docker-compose.local.yml`.

## 2. Instalacion y Configuracion Inicial
1. **Requisitos**: Docker Desktop, Python 3.10+ (para clientes locales), 8GB RAM minimo.
2. **Setup**:
   ```bash
   docker-compose -f docker-compose.local.yml up -d --build
   ```
3. **Verificacion**: 
   - Backend API: `http://localhost:8000/docs`
   - Frontend UI: `http://localhost:3000`

## 3. Inicio y Apagado
- **Inicio**: `docker-compose -f docker-compose.local.yml start`
- **Apagado Seguro**: `docker-compose -f docker-compose.local.yml stop`
  > [!IMPORTANT]
  > Usar `stop` y no `down` a menos que se desee destruir los contenedores (los volumenes persistiran).

## 4. Backup y Recuperacion
Los datos residen en dos volumenes: `postgres_data` y `redis_data`.
- **Backup Diario (Cron)**: 
  ```bash
  docker exec -t abst_postgres pg_dumpall -c -U abst_user > dump_$(date +%Y-%m-%d).sql
  ```
- **Recuperacion**: 
  ```bash
  cat dump_file.sql | docker exec -i abst_postgres psql -U abst_user -d abst_db
  ```

## 5. Limpieza (Wipe Out)
Para destruir completamente el entorno incluyendo la base de datos para pruebas limpias:
```bash
docker-compose -f docker-compose.local.yml down -v
```
> [!CAUTION]
> El flag `-v` destruye irremediablemente los volumenes `postgres_data` y `redis_data`.

## 6. Monitoreo (Health)
Se exponen endpoints para validacion activa de balanceadores y monitoreo (Prometheus/Datadog):
- **Healthcheck**: `GET /api/v6/health` (Valida conexion a BD, API y servicios core).

## 7. Estrategia de Actualizacion (Upgrade Strategy)
El versionado del sistema sigue Semantic Versioning (`V6.x.x`).
Proceso de Upgrade:
1. Generar Backup (Ver Seccion 4).
2. Obtener nueva imagen Docker (via Git pull o Container Registry).
3. Detener contenedores: `docker-compose -f docker-compose.local.yml stop`
4. Levantar con auto-migracion: `docker-compose -f docker-compose.local.yml up -d --build`
   *(Nota: FastAPI ejecutara `alembic upgrade head` en el pre-start o el administrador debera ejecutarlo via bash)*.
5. Validar `/api/v6/health`.
6. En caso de fallo critico: Restaurar dump de DB (Rollback) y volver al tag de imagen anterior.

## 8. Troubleshooting
- **Error OCR (Worker Caido)**: Validar logs del celery worker `docker logs abst_worker_ocr`. Asegurar que RabbitMQ/Redis esta en pie.
- **Error AI RAG**: Validar que los `DocumentChunk` existan en BD.
- **Error HTTP 502/504**: El proxy reverso perdio conexion con la API. Validar uso de RAM.
