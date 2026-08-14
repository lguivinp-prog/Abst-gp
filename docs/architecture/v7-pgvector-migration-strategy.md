# Abast-gp V7 - pgvector Migration & Vector Architecture Strategy

## 1. Vector Architecture (V5.5 Core vs V7 Vector Store)
**Objetivo:** Evolucionar el almacenamiento vectorial de Abast-gp sin contaminar la base transaccional Legada (V5.5).
- **Separación de Responsabilidades:** No instalaremos la extensión `pgvector` en la base de datos principal de V5.5 (donde viven los expedientes y usuarios). En su lugar, levantaremos un **contenedor PostgreSQL independiente exclusivo para V7 Vector Store**. 
- Esto asegura aislamiento de recursos; si las consultas matemáticas de K-Nearest Neighbors (KNN) saturan la CPU, el sistema de expedientes del Ministerio seguirá funcionando sin latencia.

## 2. pgvector PoC & Benchmark Analysis
Se ejecutó un PoC comparando Faiss FlatL2 (V6) vs pgvector HNSW (V7) aislando cargas de hasta 1 millón de vectores.
- **Faiss (V6):** Consumo de 349ms y 2.5 GB RAM para 1M vectores.
- **pgvector HNSW (V7):** Consumo de 4.77ms y 1.5 GB RAM para 1M vectores.
*Conclusión:* El uso de índices jerárquicos de navegación de mundo pequeño (HNSW) en pgvector pulveriza la latencia de búsqueda de Faiss exhaustivo, haciéndolo ideal para la infraestructura On-Premise a gran escala.

## 3. Data Security (Políticas Vectoriales)
- **Embeddings Permitidos:** Vectores generados a partir de texto sanitizado por el Secure Gateway (Ej. "Contrato suscrito con [RUC_MASKED]").
- **Embeddings Prohibidos:** Vectores generados a partir del PDF binario o texto crudo sin ofuscar.
- **Acceso Criptográfico:** La conexión entre la API del Gateway y el Vector Store usa SSL (`sslmode=verify-full`). Además, se habilita Row-Level Security (RLS) en pgvector forzando la cláusula `tenant_id` a nivel de motor de base de datos para garantizar aislamiento multi-entidad infranqueable.

## 4. Hybrid Retrieval Orchestration
La inferencia de inteligencia artificial operará en un pipeline dual:
1. **Local Retrieval:** El Gateway recibe una pregunta del usuario. La convierte en vector. Ejecuta un query semántico rápido (HNSW) en el PostgreSQL local (`pgvector`) para recuperar los *chunks* relevantes en milisegundos.
2. **Cloud Cognitive Inference:** El Gateway empaqueta la pregunta original y los *chunks* recuperados (limpiados de PII) y los envía al Cognitive Cloud para que el LLM redacte la respuesta final.

## 5. Migration Strategy (Faiss -> pgvector)
**Transición Suave y Segura:**
1. **Coexistencia:** Durante el despliegue V7, Faiss seguirá siendo la fuente de la verdad para documentos antiguos. El nuevo servicio V7 Vector Store se inicializa vacío.
2. **Migración en Background (Gradual):** Un `Celery Worker` (Scheduler V6.1) leerá los índices de Faiss, los pasará por el Masking Engine (para asegurar que cumplan el nuevo estándar de seguridad) y los insertará en `pgvector`.
3. **Rollback:** Si pgvector experimenta corrupción de índices o falta de memoria, un flag en el `TenantConfiguration` (`vector_engine: "faiss"`) permite regresar al motor de memoria en tiempo real, garantizando 0 downtime.
