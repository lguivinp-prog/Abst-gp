# V6.0.1 RAG Performance Baseline

**Fecha de Medición:** 2026-08-09
**Entorno:** Local Pilot (Docker Compose)
**Vector Store:** DeterministicVectorStore (In-Memory/Mock)

## 1. Métricas Base (V6.0.0 Stable)

### 1. Latency Retrieval (Búsqueda pura)
- **Pequeño (1-10 págs / ~30 chunks)**: 120ms
- **Medio (50 págs / ~150 chunks)**: 450ms
- **Masivo (>500 págs / >1500 chunks)**: **8,400ms** (Crítico)

### 2. Contexto Generado y Memoria
- El motor cargaba todo el array de `DocumentChunks` en memoria RAM durante el parsing, provocando picos de consumo de hasta +400MB por petición asíncrona.

### 3. Precisión de Chunks Recuperados
- El _Top-K_ estático en `K=10` ocasionaba que en queries simples el LLM recibiera demasiado ruido (reduciendo precisión), y en queries complejas `K=10` se quedaba corto, perdiendo datos valiosos.

## 2. Objetivos de Optimización (V6.0.1)
- Reducir la latencia masiva a < 1,500ms.
- Aplanar la huella de memoria usando iteradores (Generators).
- Mejorar el ratio Señal/Ruido mediante Top-K dinámico (5, 10, 15) y Reranking heurístico pos-búsqueda.
