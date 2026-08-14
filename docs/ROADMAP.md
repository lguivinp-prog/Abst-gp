# Roadmap de Rescate: Abst-gp

Este backlog priorizado traza la ruta desde el estado actual (fragmentado y con tests rotos) hacia un producto funcional, estable y desplegable para los entornos locales y en Kubernetes, tal como está previsto en la arquitectura V6.

---

## Ola 1: Desbloqueo y Estabilización (Lo Roto)
Objetivo: Lograr que el backend compile, pase tests básicos y el contenedor Docker levante sin errores críticos de dependencia.

| ID | Título | Categoría | Archivos Afectados | Esfuerzo | Criterio de Aceptación |
|----|--------|-----------|---------------------|----------|-------------------------|
| O1-01 | **Reparación de Imports de Persistencia** | Bug / Deuda | `backend/tests/**/*.py`, `backend/app/api/deps.py` | S | Reemplazar todas las referencias huérfanas a `app.db` por `app.core.database`. Los tests no deben fallar en la fase de recolección (`pytest` collection exitosa). |
| O1-02 | **Consolidación de Modelos de Dominio V6** | Bug | `backend/app/models/domain.py`, `backend/tests/unit/v6/*.py` | M | Resolver `ImportError: cannot import name 'Supplier'`. Asegurar que los modelos en `v6/` estén debidamente exportados y enlazados al Base declarativo de SQLAlchemy. |
| O1-03 | **Restaurar Entorno de Contenedores Local** | Infra | `docker-compose.yml`, `backend/Dockerfile` | S | `docker-compose up -d` levanta Postgres, Redis y el Backend sin reinicios (CrashLoopBackOff). La base de datos es accesible localmente. |
| O1-04 | **Protección de Variables de Entorno** | Seguridad | `backend/app/core/config.py`, `.env.example` | S | El backend no debe crashear instanciando si falta `DATABASE_URL` durante un test, utilizando entornos segregados o variables default para tests de CI. |

---

## Ola 2: Completar el Núcleo Funcional (V6 Parcial)
Objetivo: Conectar el pipeline de OCR reparado con el flujo real de endpoints REST para que los trabajadores procesen expedientes.

| ID | Título | Categoría | Archivos Afectados | Esfuerzo | Criterio de Aceptación |
|----|--------|-----------|---------------------|----------|-------------------------|
| O2-01 | **Integración del Modelo StructuredDocument** | Feature | `backend/app/services/ocr/engine.py`, `backend/app/models/v6/ocr.py` | S | El OCR de un documento escaneado retorna un objeto `StructuredDocument` válido según el schema de Pydantic sin errores de validación. Depende de O1-02. |
| O2-02 | **Encolamiento Asíncrono de OCR** | Feature | `backend/app/worker/ocr_worker_tasks.py`, `backend/app/api/routers/v2_upload.py` | M | Subir un PDF por la API encola exitosamente la tarea en Redis. El worker la procesa y actualiza el estado en BD a `COMPLETED`. |
| O2-03 | **Commit de Migraciones V6** | Deuda | `backend/alembic/versions/*` | M | Ejecutar `alembic upgrade head` sin errores en una BD limpia. Integrar todas las migraciones untracked de los "sprints 1-26". |
| O2-04 | **Restauración del Frontend (NPM/Vite)** | Bug | `frontend/package.json`, `frontend/vite.config.ts` | S | `npm run build` y `npm run dev` inician exitosamente el servidor. La UI puede comunicarse con el backend en el puerto local correspondiente. |

---

## Ola 3: Pulido y Producto Mínimo Vendible (MVP)
Objetivo: Asegurar que el sistema de cara al usuario final ("Owner" / "Supervisor") funcione de punta a punta, libre de fallos silenciosos y auditable.

| ID | Título | Categoría | Archivos Afectados | Esfuerzo | Criterio de Aceptación |
|----|--------|-----------|---------------------|----------|-------------------------|
| O3-01 | **Visualizador de Tablas y Requisitos Extraídos** | Feature | `frontend/src/features/cases/components/*` | L | El Frontend muestra correctamente las tablas separadas por `engine.py` (ej. "PAPEL BOND") y permite revisión manual (human-in-the-loop). |
| O3-02 | **Pruebas E2E de Extracción y Aprobación** | Calidad | `frontend/e2e/acceptance.spec.ts` | M | Playwright navega por el flujo de carga, espera al worker de OCR y verifica que la UI renderiza el `StructuredDocument`. |
| O3-03 | **Validación de Restricciones (Kubernetes)** | Infra / Seg | `docs/operations/v6-kubernetes-preflight.md` | S | Asegurar que no hay dependencias duras al host filesystem y que el sistema soporta volúmenes efímeros o persistentes en un entorno "No-AWS/RDS". |

**Definición de MVP (Mínimo Producto Vendible):**
Un sistema desplegable *on-premise* mediante Docker Compose / Kubernetes local donde un analista puede subir un PDF de Especificaciones Técnicas (EETT), el sistema extrae automáticamente mediante OCR las tablas de requisitos y párrafos estructurados sin truncamiento, y la UI permite validar esta información, guardando el "Expediente" en PostgreSQL.
