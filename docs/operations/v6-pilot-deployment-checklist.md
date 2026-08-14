# V6.0-RC1 Pilot Deployment Checklist

## 1. Hardware & Infraestructura Local
- [x] Servidor On-Premise (Mínimo: 8 Cores, 32GB RAM, 500GB SSD).
- [x] Sistema Operativo: Ubuntu 22.04 LTS o superior.
- [x] Conexión a red gubernamental (PIDE) habilitada y puertos whitelisteados.

## 2. Entorno y Contenedores (Docker)
- [x] Docker Engine (v24+) y Docker Compose instalados.
- [x] `docker-compose.local.yml` cargado y configurado.
- [x] Red de contenedores aislada (`abast_net`) creada.

## 3. Seguridad y Variables de Entorno (`.env`)
- [x] `.env` generado a partir de `.env.example`.
- [x] `POSTGRES_PASSWORD` y `REDIS_PASSWORD` generados (Fuertes, >16 char).
- [x] API Keys (SUNAT, RNP, FUP) inyectadas desde el gestor de secretos (Vault/Admin).
- [x] JWT Secret Key rotada para el entorno piloto.

## 4. Base de Datos y Storage
- [x] Volúmenes locales para persistencia de Postgres y Redis creados y con permisos (chown) correctos.
- [x] Migraciones aplicadas exitosamente (`alembic upgrade head` validado al inicio).
- [x] Directorio `storage/ocr_cache` con permisos 755 para los _Workers_ Celery.

## 5. Validación de Servicios (Health)
- [x] API Core (`/api/v6/health`) -> 200 OK
- [x] Postgres DB -> Conexión exitosa.
- [x] RAG Vector Store Local -> Inicializado.
- [x] Celery Workers -> Consumiendo colas de Validación y Extracción sin lag.

## 6. Onboarding de Usuarios
- [x] Creación de `Tenant` Piloto.
- [x] Creación de Cuenta Supervisor (Rol: SUPERVISOR).
- [x] Creación de Cuentas Operador (Rol: OPERATOR).
- [x] Cuentas de Auditoría (Rol: READONLY).
