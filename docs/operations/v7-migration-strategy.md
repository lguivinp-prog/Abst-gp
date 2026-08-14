# Abast-gp V7 - Estrategia de Migración Operativa Híbrida

## 1. Arquitectura de Coexistencia (DUAL_RUN)
Para evitar el escenario catastrófico de un "Big Bang" (Apagar la V6.1 y prender la V7 de golpe), se establece una arquitectura de coexistencia donde ambos motores de búsqueda semántica (FAISS in-memory y `pgvector` On-Premise) vivirán temporalmente en paralelo.
- La V5.5 se mantiene intacta, inmutable.
- La V6.1 provee telemetría y gobernanza.
- V7 Alpha/Beta procesa el ruteo de inteligencia en las sombras.

## 2. Vector Router (`VectorEngineRouter`)
Se desarrollará una clase en el *Backend* (PoC probado en `poc/vector_router_alpha.py`) que gobierne hacia dónde viajan los *Embeddings*. Operará en 4 fases secuenciales:

1. **FAISS_ONLY:** Producción actual. V7 apagada.
2. **DUAL_WRITE:** Cada vez que el Gateway V7 genera un Embedding sanitizado, el Router lo guarda en FAISS y también lo inserta en `pgvector`. **Las consultas de usuario (Reads) siguen apuntando 100% a FAISS.** Esto permite llenar la nueva base de datos sin arriesgar la experiencia del usuario.
3. **DUAL_READ (Shadow Mode):** Las consultas de usuario leen de FAISS para mostrarse al cliente, pero asíncronamente leen de `pgvector` para comparar si ambos motores arrojan el mismo resultado. Permite validar latencia y precisión (Recall).
4. **PGVECTOR_PRIMARY:** Si la Fase 3 es exitosa, FAISS se apaga. `pgvector` atiende el 100% del tráfico de lectura y escritura.

## 3. Pipeline de Migración Histórica (Backfill)
Dado que V6.1 tiene gigabytes de datos en FAISS que no pasaron por el Gateway V7, no podemos copiar los vectores directamente.
- **Fuente Autorizada:** Se usará el **Documento Original** (PDF) desde el S3/FileServer V5.5.
- **Flujo Re-Sanitizador:** `Documento Original -> Secure Gateway (Sanitización PII) -> Chunking V7 -> Nuevo Embedding -> Inserción pgvector`.
Este reprocesamiento garantiza que la nueva base `pgvector` nazca criptográficamente limpia de PII.

## 4. Validación de Calidad (Validation)
Durante la etapa `DUAL_READ`:
- **Latencia:** Se comparará el tiempo de respuesta (El benchmark previo exige <5ms para 1M vectores).
- **Recall / Precisión:** Se compararán los Top-K *chunks* recuperados. HNSW (Aproximado) vs FlatL2 (Exacto). La tolerancia aceptable de error de HNSW es menor al 1% de divergencia en el Top-5.

## 5. Rollback Inmediato (Disaster Recovery)
El mayor beneficio del `VectorEngineRouter` es la reversibilidad.
Si `pgvector` sufre corrupción de índices o saturación de memoria durante `PGVECTOR_PRIMARY`:
- Bastará cambiar una variable de entorno (`VECTOR_MODE=FAISS_ONLY`) para regresar instantáneamente al estado legado, sin pérdida de continuidad operativa. El historial de FAISS habrá quedado congelado en la Fase 3.

## 6. Olas de Despliegue (Deployment Waves)
- **Wave 1 (Piloto Alpha):** 1 Institución pequeña (Ej. Un municipio con bajo volumen transaccional V5.5). Fase `DUAL_WRITE`.
- **Wave 2 (Primer Grupo):** 5 Ministerios. Fase `DUAL_READ`. Monitoreo riguroso de falsos positivos en el PII Masking Engine.
- **Wave 3 (Escala Masiva):** Todas las instituciones migran a `PGVECTOR_PRIMARY`.

## 7. Operaciones y Monitoreo (SRE)
- **Backups:** `pg_dump` regular del contenedor `abast-gp-vector-store`.
- **Incidentes:** Las caídas del Gateway o de `pgvector` dispararán alertas al CISO. El estado de telemetría de la V6.1 enviará métricas de la proporción de peticiones que están aplicando el *Fail Closed*.
