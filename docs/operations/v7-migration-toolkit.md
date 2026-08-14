# Abast-gp V7 - Herramientas de Migración Operativa (Toolkit)

## 1. VectorEngineRouter (Controlador de Tráfico)
El `VectorEngineRouter` es el enrutador lógico en la capa de persistencia V7, diseñado para garantizar un pase a producción con cero *downtime*.
- **Transición Controlada:** Permite al equipo SRE escalar desde `FAISS_ONLY` -> `DUAL_WRITE` -> `DUAL_READ` -> `PGVECTOR_PRIMARY` usando simples cambios de estado.
- **Auditoría Estricta:** Todo cambio de estado genera un `audit_log` local registrando el usuario (Ej. `CISO_Admin`) y el *timestamp* exacto de la conmutación.

## 2. MigrationBackfillController (Motor de Extracción Histórica)
Dado que los vectores antiguos de V6 no cumplen los estándares criptográficos de la V7, este controlador orquesta la lectura de los PDFs originales (desde V5.5) y los empuja a través del nuevo `Secure Gateway`.
- **Controles Básicos:** `start`, `pause`, `resume`, `cancel`. Si un nodo de Gateway reporta saturación, el SRE puede pausar el *Backfill* instantáneamente.
- **Resource Control:** Posee consciencia temporal (`nocturnal_window`). Si se detecta que se intenta ejecutar fuera de la ventana nocturna (22:00 a 06:00), el controlador impone un acelerador inverso (CPU Throttling al 5%) para proteger los ciclos de procesamiento diurno del Ministerio.

## 3. Metrics & Observability
El *Backfill Controller* reporta en vivo:
- `docs_processed`: Cantidad de PDFs sanitizados.
- `chunks_created`: Vectores HNSW generados.
- `errors`: Errores de OCR o timeout en el Gateway.
- `time_elapsed_ms`: Tiempo de ejecución.
En modo `DUAL_READ`, el *Router* inyecta la métrica booleana `shadow_match`, comparando matemáticamente la exactitud (Recall) de `pgvector` vs `FAISS`.

## 4. Cutover Test & Rollback Mechanism (Disaster Recovery)
El *Cutover* (Pase a Producción) fue simulado exitosamente en el PoC `poc/migration_toolkit.py`:
- **El Rollback es inmediato:** Si durante la fase final (`PGVECTOR_PRIMARY`) el sistema detecta que la base de datos `pgvector` se quedó sin memoria RAM (OOM), el CISO presiona el botón de pánico, invocando el método `.rollback(user)`.
- El tráfico se redirige instantáneamente a `FAISS_ONLY`. El usuario final experimenta una recuperación transparente en la siguiente petición.
