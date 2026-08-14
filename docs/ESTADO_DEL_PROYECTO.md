# Estado del Proyecto: Abst-gp (v5.5 / v6 / v7)

## Resumen Ejecutivo
El proyecto "Abst-gp" es una plataforma de contrataciones públicas y extracción documental mediante OCR diseñada para automatizar el análisis de Especificaciones Técnicas (EETT) y perfiles de proveedores. Actualmente, el sistema se encuentra en una transición accidentada entre la versión estable (v5.5/v6) y una refactorización mayor (v7). Se observan múltiples modelos de la versión 6 conviviendo con rutas truncadas, dependencias faltantes y un conjunto de pruebas unitarias severamente roto debido a reorganizaciones de módulos (ej. `app.db` no existe). El avance real se estima en **65%**, justificándose en que el motor de OCR (`engine.py`) y las entidades base existen y fueron probadas, pero la integración (FastAPI), la capa de persistencia y el frontend carecen de estabilidad, aislamiento de entorno y un pipeline de despliegue funcional en el estado actual del repositorio.

---

## Fase 0: Inventario

* **Árbol de directorios y Archivos:**
  * **Top 3 Archivos más grandes:** `backend/data/EETT MATERIALES DE OFICINA - DIRECCIÓN.pdf` (3.1 MB), `frontend/e2e/playwright-report/index.html` (532 KB), `backend/scripts/output.txt` (380 KB).
  * **Modificaciones recientes:** `backend/app/services/ocr/engine.py`, `backend/scripts/parse_output.py`, `backend/app/models/v6/ocr.py`. Existen múltiples scripts de testing iterativos (`check_tables.py`, `test_owner_pdf.py`).
* **Stack Tecnológico:**
  * **Backend:** Python (FastAPI >=0.111), SQLAlchemy >=2.0.30, Alembic, PostgreSQL, Redis, Celery/RQ, OCRMyPDF, PyMuPDF, pdfplumber.
  * **Frontend:** TypeScript, React, Vite, Tailwind/CSS (implícito), Lucide-react, Playwright (E2E).
* **Puntos de Entrada:** 
  * Backend: `backend/app/main.py` (expone rutas de `cases`, `v6_requirements`, etc.).
  * Frontend: `frontend/package.json` -> `vite` dev server.
* **Variables de Entorno:**
  * Esperadas: `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `SECRET_KEY`, `DATABASE_URL`, `REDIS_URL` (vistas en `backend/app/core/config.py` y `.env.example`).
  * Estado: `DATABASE_URL` no está definida por defecto y es requerida obligatoriamente en `config.py:12` provocando fallos de arranque en crudo.
* **Historial Git:**
  * Rama actual: `feature/phase5-ring1` (2 commits por delante de origin).
  * Commits recientes: Intentos de estabilizar "V4.8.1 Release Candidate Patch", "v5.5 Enterprise DR certification", y múltiples ajustes de OCR y tablas.
  * Gran cantidad de archivos *untracked* (rutas v6, modelos v6, migraciones v6), indicando un salto incompleto de versión.
* **Documentación:** 
  * Existen documentos exhaustivos en `docs/releases`, `docs/operations`, y `docs/architecture` que denotan un enfoque en certificación (DR), despliegues aislados y migración a Kubernetes (ej. `v6-kubernetes-preflight.md`).

---

## Fase 1: Reconstrucción de la Intención

* **Producto y Problema (Confianza: ALTA):** Es una herramienta B2B/B2G para automatizar procesos de compras gubernamentales. Resuelve el problema de la extracción manual de requerimientos y evaluación de proveedores leyendo PDFs complejos (EETT) mediante OCR estructural (identificando párrafos y tablas como la de "PAPEL BOND").
* **Entidades Centrales (Confianza: ALTA):** `Cases` (Expedientes), `Supplier` (Proveedores), `Requirements` (Requisitos), `Validations` (Validaciones), `DocumentChunk` / `StructuredDocument` (Extracción documental). Basado en `backend/app/models/v6/*.py` y `backend/app/api/routers/*.py`.
* **Arquitectura Efectiva (Confianza: MEDIA):** 
  * SPA en React consumiendo una API REST (FastAPI).
  * Base de datos relacional PostgreSQL con migraciones Alembic.
  * Background Workers (Redis + RQ) orquestando la tubería pesada de extracción de PDFs (`app/worker/ocr_worker_tasks.py`).
  ```mermaid
  graph TD
      Client[React Frontend] -->|REST API| API[FastAPI Backend]
      API -->|Read/Write| DB[(PostgreSQL)]
      API -->|Enqueue Task| Redis[(Redis Queue)]
      Redis --> Worker[RQ Worker]
      Worker -->|OCR Pipeline| PDF[OCRMyPDF / pdfplumber]
      Worker -->|Write Results| DB
  ```
* **Integraciones Externas (Confianza: ALTA):** Dependencia estricta en binarios del sistema (Tesseract/Ghostscript vía OCRMyPDF). Restricción estricta de **NO usar AWS/EKS/RDS**.
* **Decisiones de Diseño Irreversibles:**
  1. **Motor OCR Híbrido:** `engine.py` utiliza PyMuPDF para texto nativo y un fallback manual hacia Tesseract + `pdfplumber` con `intersection_y_tolerance = 3` para forzar la separación de tablas. Deshacer esto requeriría reescribir toda la extracción. (Evidencia: `backend/app/services/ocr/engine.py`).
  2. **Modelos Específicos de OCR:** Creación de `StructuredDocument`, `StructuredTable`, etc., centralizados en `backend/app/models/v6/ocr.py`.
  3. **Migración en vuelo a v6:** Gran parte de los modelos apuntan a `v6` pero las dependencias de imports en los tests siguen apuntando a módulos de v5 o renombrados (ej. `app.db` -> `app.core.database`).

---

## Fase 2: Verificación Empírica

1. **Dependencias:** 
   * Frontend: Fallido. Dependencia de entorno de Node ausente en el PATH local.
   * Backend: Pip requirements instalables, pero `docker-compose up` falla debido a que el demonio Docker no está accesible localmente (`failed to connect to the docker API at npipe:////./pipe/dockerDesktopLinuxEngine`).
2. **Build / Compilación:** Imposible validar frontend por falta de npm/node.
3. **Pruebas (Tests):** 
   * `pytest backend/tests/unit` falla catastróficamente durante la recolección (`4 errors during collection`).
   * *Errores textuales:* `ModuleNotFoundError: No module named 'app.db'` (en `test_admin_api.py`) y `ImportError: cannot import name 'Supplier' from 'app.models.domain'` (en `test_experience.py`).
4. **Arranque de la Aplicación:** Bloqueado en backend por la falta de `DATABASE_URL` y variables de entorno no configuradas en tiempo de ejecución. Bloqueado por base de datos inaccesible (Docker caído).
5. **UI / Camino Feliz:** No evaluable.

---

## Fase 3: Análisis de Brechas

* **[COMPLETO] Tubería de Extracción OCR Base:** El pipeline de `engine.py` con `pdfplumber` y tolerancia de 3px para tablas (verificado externamente en `output.txt` y `check_tables.py`).
* **[ROTO] Suite de Pruebas y Enrutamiento Base:** Los tests unitarios no compilan debido a dependencias huérfanas (`app.db`).
* **[PARCIAL] Modelos V6 y Migraciones:** Los modelos existen como archivos untracked, pero no han sido integrados con un `Base` unificado de SQLAlchemy que permita iniciar la aplicación o autogenerar migraciones correctas.
* **[AUSENTE] Frontend Dev Environment:** Configuración funcional o scripts de inicialización agnósticos de host para el cliente React.

### Deuda Técnica y Riesgos
* **Acoplamiento de Imports:** Migración fragmentada. Múltiples módulos asumen que `app.db.session` existe, cuando aparentemente fue movido a `app.core.database`.
* **Riesgo Operacional (Hard dependency):** El backend requiere la instalación manual de dependencias de sistema complejas (tesseract-ocr, ghostscript, ffmpeg, libgl) que no están encapsuladas correctamente si Docker falla.
* **Secretos:** `.env.example` revela que las contraseñas por defecto (`abst_password`) están expuestas. Si se usan en producción por accidente (vía Kubernetes), es un riesgo crítico.
* **Lo que un usuario NO puede hacer hoy:** Desplegar el sistema, correr los tests de regresión, o levantar la interfaz de usuario.
