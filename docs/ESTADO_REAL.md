# Estado Real del Proyecto (Auditoría con Entorno Vivo)

## 1. Entorno de Ejecución (Docker & Infraestructura)
* **Deminio Docker:** Activo (Docker Desktop 29.7.2).
* **Contenedores de Backend y Servicios:**
  * `abst_api`, `abst_worker`, `abst_worker_ocr`, `abst_db`, `abst_redis` **levantan exitosamente** y se mantienen estables (`Up`, sin CrashLoopBackOff).
  * **PostgreSQL (`abst_db`)** y **Redis (`abst_redis`)** aceptan conexiones correctamente desde el backend.
* **Componentes de Sistema Operativo:**
  * Node.js / NPM no están instalados en el host local (ruta estándar `C:\Program Files\nodejs\node.exe` o PATH general no disponibles).
  * Dentro del contenedor `abst_worker_ocr`, las dependencias de OCR están correctas: **Tesseract 5.5.0** y **Ghostscript 10.05.1**.

## 2. Pruebas Unitarias (Tests)
* **Total de errores de recolección (`pytest --collect-only`):** 5 errores.
* **Causas Raíz:**
  1. `ModuleNotFoundError: No module named 'app.db'`: Presente en `test_admin_api.py` y `test_admin_governance.py`. La causa es que `app/api/deps.py`, `app/models/v6/telemetry.py` y `app/models/v6/tenant_config.py` intentan importar `app.db` que ya no existe (probablemente movido a `app.core.database`).
  2. `ImportError: cannot import name 'Supplier' from 'app.models.domain'`: Presente en `test_experience.py` y `test_supervisor.py`. La clase `Supplier` fue movida a `app/models/v6/supplier.py` pero los tests siguen apuntando al archivo legacy `domain.py`.
  3. Adicional: Falla de `botocore` ausente en el entorno de pruebas, causando error en `test_object_storage.py`.

## 3. Estado de la Base de Datos y Alembic
* **Alembic Heads:** 1 head actual (`4651e83920b0`).
* **Estado de la Cadena:** La cadena **no está rota**. Hubo un `merge heads` explícito (`4651e83920b0_merge_heads.py`) que consolidó las ramas de migraciones de V5.4/V5.5 y los sprints V6 (1 al 26).

## 4. Conflictos de Modelos (V6 vs Domain)
* **Duplicados Críticos:** `GeneratedOutput` existe tanto en `domain.py` como en `app/models/v6/generated_output.py`.
* **Exclusivos de V6 (Ausentes en domain.py):** Entidades clave del nuevo negocio como `Supplier`, `SupplierProfile`, `OfferEvaluation`, `ExperienceRequirement`, `ValidationRequest`.
* **Exclusivos de domain.py (Legacy):** `ValidationDocumentCase`, `OCRProcessingRun`, `ProcessingJob`, `UploadedDocument`.
* **Conflicto Principal:** La suite de pruebas y ciertas dependencias intentan importar entidades de V6 desde `domain.py`, rompiendo la retrocompatibilidad y la recolección de pruebas.

## 5. Corrección de Avance
El informe anterior calculó un 65% asumiendo que nada levantaba y que la separación de backend era más caótica. Con Docker funcionando, la BD inicializando correctamente, y la API sirviendo tráfico (Swagger docs disponibles), la base arquitectónica es sólida. El avance real es del **75%**. 
El 25% restante es trabajo de corrección de *imports*, enlazado de módulos V6 con el `Base` de SQLAlchemy y la restauración/empaquetado del frontend, sin requerir reescritura de lógica de negocio o de extracción documental.
