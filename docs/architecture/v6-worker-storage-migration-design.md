# V6.0 Worker Storage Migration Design

## 1. Estado Actual (Filesystem Dependencies)
Actualmente, los workers de extracción y OCR asumen acceso posix irrestricto al sistema de archivos local (`settings.UPLOADS_DIR`). Las dependencias acopladas identificadas son:
- **Argumentos de los Tasks**: Las funciones como `process_run_v2`, `process_requirement_task`, y `execute_v1_pipeline` reciben directamente el parámetro `file_path`.
- **Rutas estáticas para artefactos**: `ocr_worker_tasks.py` (Modo SHADOW) realiza un `os.makedirs` y `with open(..., "w")` hacia `/uploads/validation_artifacts/...`.
- **Motores OCR Subyacentes**: `pipeline.process_document(file_path)` y `process_pdf(file_path)` esperan un path en disco, ya que librerías subyacentes como PyMuPDF (fitz), Tesseract, o AWS Textract CLI requieren interactuar con un I/O de sistema de archivos físico o cargarlo directo en memoria.
- **Capa de Persistencia**: `AtomicPersistence.save_structured_document` escribe el JSON estructurado directamente usando `settings.UPLOADS_DIR`.

## 2. Diseño Objetivo
El ecosistema Cloud Native V6 separa conceptualmente la API, el Worker y el Storage, donde el Worker no comparte almacenamiento en bloque (PVC) con la API.

```mermaid
graph TD
    API[FastAPI] --> |Encola Tarea (URI)| Redis[RQ / Redis]
    Redis --> Worker[OCR Worker]
    Worker --> |1. storage.get(URI)| ObjectStorage[(DocumentStorage)]
    Worker --> |2. Spool Local| LocalTemp[Local Temp Workspace]
    LocalTemp --> |3. Procesa| OCREngine[Motor OCR (V1/V2)]
    OCREngine --> |4. JSON Result| Worker
    Worker --> |5. storage.put(JSON)| ObjectStorage
```

## 3. Estrategia para Archivos Grandes (Temp Workspace)
Dado que los motores de visión computacional y OCR requieren usualmente de un path físico local o cargan iterativamente los bytes del documento (lo que hace ineficiente y frágil pasarlos directamente vía una red de sockets de S3):
- **Streaming & Spooling**: El worker debe crear un archivo temporal en su propio filesystem de ejecución usando `tempfile.NamedTemporaryFile`. El contenido se descarga de `DocumentStorage.get(uri)` usando *chunking* (8192 bytes) para evitar picos de consumo de memoria RAM.
- **Temp Workspace**: El motor OCR (`process_document`) será invocado apuntando a este Temp Workspace local del pod/contenedor del worker.
- **Cleanup (Limpieza)**: El ciclo de vida de este archivo temporal está encapsulado en un bloque `try...finally` asegurando que, sin importar errores fatales de OCR, el `os.remove()` se invoque, evitando *disk leaks* que apaguen el nodo de Kubernetes.

## 4. Compatibilidad
- **Retries**: Al utilizar URIs inmutables en Redis, el encolamiento es independiente del nodo que ejecute. Si un pod de worker falla por `OOMKilled`, el retry descargará nuevamente el URI en un nodo sano, haciendo la tarea intrínsecamente segura para retries.
- **Idempotencia**: Al generar artefactos de salida, si la URI a persistir ya existe (`storage.exists`), puede sobreescribirse o ser saltada si los checksums coinciden.
- **Checksum**: El worker validará la integridad en dos partes:
  - Download: Calcular SHA-256 al bajar el URI temporalmente para asegurar que no se corrompió la red.
  - Upload (Artefactos JSON): Calcular y adjuntar el hash del artefacto que produce el `AtomicPersistence` migrado.

## 5. Impacto DR V6 (Disaster Recovery)
Al desacoplar los *validation_artifacts* y los JSON generados del sistema de archivos, el DR plan se simplifica drásticamente. El proceso de restauración solo requerirá recuperar la base de datos PostgreSQL (SSOT) y hacer un sync/restore del Bucket de S3.
La reconstrucción de índices de *Worker Reconciliation* de V5 (Gate E) será nativa ya que un "Dead Worker" dejará de dejar "orphan files" locales.

## 6. Riesgos
- **Latencia de Red (Network I/O)**: Bajar documentos pesados (ej. 300MB) para OCR introduciá latencia. Esto podría disparar timeouts de latido (Heartbeat Timeouts) configurados estrictamente en V5 si la descarga demora más de 15 segundos.
- **Mitigación**: Extender el `heartbeat_worker` thread para que también envíe latidos continuos ("DOWNLOADING") mientras ocurre el *stream* de descarga inicial.
- **Sobrecarga de Object Storage**: Un incremento de requests `GET`/`PUT` que deba rate-limitarse.
