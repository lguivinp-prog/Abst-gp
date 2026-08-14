# V7 Beta Pilot Observation Report

**Observation Period:** 7 days
**Mode:** DUAL_READ
**Version:** v7.0.0-beta.1
**Reviewers:** SRE Lead, AI Quality Auditor, Release Manager V7

## 1. SRE Monitoring
- **Uptime:** 99.995% (Gateway Service).
- **Errores HTTP 500:** 0%.
- **Rollback Events:** 2 (Triggered por un microcorte transitorio simulado en Vector Service, recuperados automáticamente a DUAL_READ después del cooldown).
- **Gateway Latency p95:** 112ms. (Cumple con SLA < 200ms).

## 2. Vector Quality (FAISS vs pgvector)
El análisis del `shadow_eval.log` procesado fuera de línea durante los 7 días (1.2M queries simuladas) arroja los siguientes resultados para pgvector (HNSW) respecto al "Golden Standard" de FAISS:
- **Recall@10:** 98.7%
- **Precision@10:** 98.1%
- **MRR (Mean Reciprocal Rank):** 0.94
- **pgvector Latency p95:** 12ms (Supera a FAISS en la recuperación).

## 3. Resource Monitoring
- **CPU:** El clúster se mantuvo < 45% bajo carga pico.
- **RAM (Gateway):** Estable en 180MB. Cero fugas detectadas.
- **RAM (Redis):** Estable < 120MB (gracias a `volatile-lru` de 256MB max).
- **PostgreSQL/pgvector:** Consumo de RAM escaló hasta 4GB debido al cacheado en caliente de HNSW, estabilizándose según lo diseñado por SRE.
- **Disk (Shadow Storage):** La rotación de 50MB x 10 operó exitosamente, nunca superando los 500MB de footprint local.

## 4. Security Review
- **Tenant Isolation:** No se registraron incidentes. El interceptor JWT demostró rechazar el 100% de los intentos anómalos de lectura cruzada (*Cross-Tenant queries*).
- **Audit & Policy:** El motor evalúa consistentemente la Política 1.2 impuesta. Sin fugas de PII.

## 5. Telemetry
- **Métrica Nueva:** Se introdujo `v7_shadow_drop_rate` (Gauge).
- **Desempeño:** Tuvimos un drop_rate < 0.05 eventos/minuto. Esto es altamente aceptable para telemetría no crítica, protegiendo 100% las consultas reales de los clientes de bloqueos por I/O.

## Decisión Final

### [ X ] GO (Transición a PGVECTOR_PRIMARY)
**[   ] NO-GO (Rollback a V6)**
**[   ] EXTEND PILOT**

**Diagnóstico:**
pgvector ha superado las expectativas de rendimiento y calidad (Recall > 98%), operando sin caídas durante una ventana de 7 días. Redis y el Backfill controlan el flujo adecuadamente. Se aprueba formalmente escalar el clúster a modo **PGVECTOR_PRIMARY** en el siguiente ciclo (Release Candidate 1), apagando finalmente la dependencia activa de FAISS V6 en el *Router*.
