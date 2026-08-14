# V6 Production Readiness Checklist

## 1. Infraestructura y Contenedores (Docker)
- [x] Docker Engine & Docker Compose instalados (v2+).
- [x] Mapeo de volumenes persistentes configurado (`postgres_data`, `redis_data`).
- [x] Celery Workers orquestados y conectados a la cola correcta.

## 2. Base de Datos (PostgreSQL)
- [x] Migraciones Alembic aplicadas (`upgrade head`).
- [x] Indices creados para `tenant_id` y `case_id` en tablas maestras.
- [x] Restricciones (Foreign Keys, Constraints) validadas.

## 3. Storage y Backups
- [x] Rutinas de Backup cronificadas (Diarias).
- [x] Restore Drill mensual calendarizado.
- [x] Almacenamiento local para OCR mapeado y con permisos correctos.

## 4. Usuarios y Seguridad (RBAC)
- [x] Politicas de contraseñas fuertes habilitadas.
- [x] Separacion de roles estricta: Operator vs Supervisor.
- [x] Aislamiento Tenant (No cross-tenant data leaks) comprobado.
- [x] `AuditLog` interceptando cambios de estado y `AIInteractionLog` rastreando context chunks.
- [x] `ContractAccuracyGate` activo: Bloquea exportacion de documentos si existen dependencias sin resolver o conflictos heurísticos.
