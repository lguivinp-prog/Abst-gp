# PROJECT_CONTEXT

## 1. Visión del producto
* **Nombre del proyecto:** AbastLG - Plataforma de Extracción y Comparación Documental (OCR V2)
* **Problema que resuelve:** El procesamiento y la validación manual de expedientes técnicos, requerimientos y cotizaciones es un proceso lento, repetitivo y altamente propenso a errores humanos, dificultando la agilidad en la gestión de compras y licitaciones.
* **Usuario objetivo:** Analistas de compras, auditores de licitaciones y personal de backoffice encargado de validar requerimientos frente a cotizaciones.
* **Objetivo final:** Automatizar la lectura, extracción, estructuración y comparación algorítmica de documentos complejos (PDFs escaneados o digitales) mediante inteligencia artificial y OCR, entregando reportes de validación listos para revisión.
* **Valor diferencial:** Precisión estructurada. En lugar de extraer texto plano, el sistema identifica secciones semánticas (ej. "Objetivo", "Forma de Pago"), preserva la estructura de los datos y genera cuadros comparativos automáticos en formato HTML/Texto.

## 2. Definición del MVP (Producto Mínimo Viable)
Como Product Manager, la definición del alcance inicial del MVP es la siguiente:
* **Qué debe lograr el MVP:** Permitir a un analista subir un requerimiento base, dejar que el motor extraiga las reglas de negocio, validarlas, subir una cotización candidata, y generar un reporte de comparación automática ("pasa/no pasa" o "cumple/no cumple").
* **Funcionalidades obligatorias:**
  - Creación de Expediente (Case).
  - Subida de documentos (Requerimientos y Cotizaciones).
  - Cola asíncrona de procesamiento OCR V2 con manejo de estados.
  - Generación de secciones normalizadas para validación humana.
  - Ejecución de algoritmo comparativo.
  - Generación de reporte final (HTML/Plano).
* **Flujo principal del usuario:**
  1. Crear expediente.
  2. Subir PDF del requerimiento.
  3. Esperar procesamiento (Progreso 0 a 100%).
  4. Revisar y aceptar (o rechazar) secciones detectadas.
  5. Subir PDF de la cotización.
  6. Disparar comparación automática.
  7. Exportar informe de resultados.
* **Criterios de MVP terminado:** Todos los flujos descritos arriba completan su ciclo end-to-end sin caídas (E2E Tests en 100% Passed), manejando correctamente tanto documentos nacidos digitales como escaneados sin afectar el contrato del Frontend.
* **Fuera del alcance inicial:** Soporte multi-idioma, integración con sistemas ERP de terceros, despliegue serverless de modelos de ML, y entrenamiento fino o customizado del modelo PaddleOCR (se usará el genérico out-of-the-box).

## 3. Arquitectura técnica actual
* **Frontend:** React (Desacoplado, se comunica exclusivamente vía API REST respetando el esquema original de contratos JSON).
* **Backend:** FastAPI (Python 3.12). Arquitectura limpia y síncrona/asíncrona para orquestación rápida de endpoints.
* **Base de datos:** PostgreSQL, manipulado a través de SQLAlchemy 2.0 y migraciones controladas por Alembic.
* **Memoria/Caché:** Redis. Actúa como broker de mensajería y almacenamiento de estado temporal.
* **Servicios / Orquestación:** `ExtractionOrchestrator` decide qué pipeline usar (V1 o V2). Utiliza RQ (Redis Queue) para delegar trabajo pesado fuera del ciclo de vida HTTP.
* **Workers:** Dos contenedores separados:
  - `worker`: Para tareas asíncronas ligeras o procesamiento estándar.
  - `worker-ocr`: Contenedor especializado y pesado que carga los modelos de IA.
* **OCR Engine (V2):** Basado en **PaddleOCR** (v3). Se encarga de la inferencia pesada (detección, clasificación y reconocimiento de texto). Opera bajo un modelo "Cold Start" (descarga inicial de pesos que toma ~1.5 minutos) y "Warm Start" (procesamiento residente de ~8 segundos).
* **Infraestructura:** Todo containerizado nativamente bajo `docker-compose`, permitiendo levantamiento unificado de la base de datos, caché, API y Workers.

## 4. Flujo completo del sistema
1. **Carga:** El usuario realiza un `POST /cases/{case_id}/requirement/upload`. FastAPI guarda el archivo localmente o en volumen de almacenamiento.
2. **Orquestación:** FastAPI encola el ID del caso en Redis Queue (`ocr_tasks`) y devuelve un `job_id` al frontend.
3. **Procesamiento Asíncrono:** El contenedor `worker-ocr` toma el trabajo. El script `ocr_worker_tasks.py` despierta el motor V2.
4. **Inferencia OCR:** PaddleOCR detecta texto, limpia basura, identifica numerales romanos y delimita los bloques.
5. **Estructuración:** El `StructuredDocumentAdapter` empaqueta los resultados crudos del V2 transformándolos exactamente al contrato V1 (`ParsedSection`).
6. **Almacenamiento:** Las secciones se persisten en PostgreSQL. El Job se marca como completado (`progress: 100`).
7. **Consulta:** El Frontend realiza "polling" del job, detecta que terminó, y dispara un `GET /cases/{case_id}/sections` para renderizar el resultado.

## 5. Estado actual del desarrollo
* **Qué está terminado:** Toda la tubería core de extracción OCR V2 está integrada con la API original y orquestada asíncronamente.
* **Qué funciona:** Creación de expedientes, carga de archivos, despacho correcto al worker OCR sin colisiones, procesamiento real (extrayendo secciones correctamente) y validación de esquemas JSON de respuesta.
* **Qué pruebas pasan:** El Baseline crítico de Integración (`test_full_integration_flow`, `test_full_integration_flow_v2`, `test_empty_extraction_v2`) pasa al **100%**.
* **Commit actual:** `648bb237c014dc396c294ba37110f44e3c3b4d35`
* **Rama actual:** `fix/e2e-baseline-regression`
* **Archivos vitales de infraestructura/código:**
  - `backend/app/services/extraction_engine/orchestrator.py` (Cerebro del despacho).
  - `backend/app/worker/ocr_worker_tasks.py` (Punto de entrada al IA).
  - `backend/app/services/extraction_engine/adapters/structured_document_adapter.py` (Traductor de datos).
  - `docker-compose.yml` y `docker-compose.test.yml`.

## 6. Problemas resueltos (Historial Clínico)
1. **Crash Interno del Worker:** Solucionado inyectando imports faltantes (`time`, `threading`) en `ocr_worker_tasks.py` que provocaban un `NameError` durante la inicialización del heartbeat.
2. **Dependencia faltante:** Inclusión de `pydantic-settings` en `requirements-ocr.txt` para evitar caídas silenciosas al importar configuraciones en el entorno aislado del worker.
3. **Orquestación V2:** Inyección robusta del objeto `ProcessingJob` y generación de una llave SHA256 para `run_dedup_key` de la tabla `OCRProcessingRun`, permitiendo que V2 no violara llaves foráneas.
4. **Tiempos de Cold Start vs Pruebas E2E:** Los tests de integración estaban fracasando a los 10-15 segundos. Se documentó que el motor toma ~100s en descargar pesos de red. Se modificaron los tests a una tolerancia de `180` iteraciones.
5. **Normalización Pydantic:** Una vez resuelto el timeout, descubrimos que FastAPI emitía un Error 500 (`ResponseValidationError`) porque `structure_json`, `corrections_json` y `warnings_json` llegaban como diccionarios `{}` desde el Adapter, mientras el esquema esperaba estrictamente listas `[]`. Fue solucionado.

## 7. Decisiones técnicas importantes
* **Adaptador Estricto (Adapter Pattern):** Se decidió crear el `StructuredDocumentAdapter` en vez de modificar la capa de rutas. *Razón:* Evitar un refactor masivo en el Frontend en React. *Regla:* Las salidas del V2 **jamás** deben cambiar las llaves esperadas en `SectionResponse`.
* **Tiempo de Espera en Pruebas (Cold Start):** Se incrementó artificialmente la espera E2E a 3 minutos. *Razón:* Permite aislar pruebas locales puras sin requerir volúmenes con pesos del modelo pre-descargados.
* **Compatibilidad de Estado del Job:** El Orquestador ahora "falsea" o inyecta el `progress = 100` sobre el Job original de RQ apenas termina el modelo. *Razón:* El frontend V1 y las pruebas esperan que el job_id retorne estado 100%.

## 8. Pendientes actuales
* **Alta prioridad:**
  - Realizar "merge" definitivo de esta rama de estabilización hacia `main` o `develop`.
* **Media prioridad:**
  - Agregar tests formales aislados de rendimiento (Warm Start vs Cold Start).
  - Centralizar y optimizar las trazas de logs del worker OCR.
* **Futuro:**
  - Hacer un "Bake" o pre-carga de los modelos de PaddleOCR directamente en la imagen de Docker (Dockerfile) para que los tiempos en producción siempre sean equivalentes al "Warm Start" (8s en vez de 99s).

## 9. Roadmap hacia MVP
- **Fase 1 (Actual):** Estabilización Pipeline V2. [COMPLETADO]
- **Fase 2:** Integración Final del Módulo de Comparación (Asegurar que las secciones V2 interactúan sin roces con la heurística de matching).
- **Fase 3:** Refinamiento visual y de experiencia en el Frontend (Barras de progreso, visores de PDF lado a lado).
- **Fase 4:** Beta Testing cerrado, métricas de retención y paso a entorno Productivo (Cutover primario).

---

## 10. PROMPT DE CONTINUIDAD

**PROMPT PARA NUEVAS SESIONES DE GPT:**
```markdown
Eres mi arquitecto de software senior y líder técnico. Estamos trabajando en el proyecto "AbastLG - Plataforma de Extracción Documental OCR V2".

Acabamos de estabilizar el pipeline asíncrono, resolver los cuellos de botella de Cold Start, corregir incompatibilidades de Pydantic y lograr un baseline E2E limpio con un 100% de éxito (Commit actual: 648bb237). 

Por favor, lee detalladamente el archivo `PROJECT_CONTEXT.md` para asimilar toda la arquitectura, el flujo del sistema, las decisiones previas y los problemas ya resueltos.

Nuestra prioridad ahora es continuar con el desarrollo respetando el flujo de MVP. No modifiques el Adapter V2 ni la configuración de orquestación a menos que sea estrictamente necesario. Pregúntame qué tarea del Roadmap o "Pendiente de alta/media prioridad" atacaremos en esta sesión y guía mis próximos pasos de manera estructurada.
```
