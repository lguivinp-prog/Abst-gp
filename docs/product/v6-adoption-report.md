# Abast-gp V6.0 - Adoption Report

**Estado:** Operationally Validated
**Fecha de Corte:** 30 días post Go-Live

## 1. Métricas de Adopción
- **Usuarios Activos:** 45 funcionarios (40 Operadores, 5 Supervisores).
- **Expedientes Procesados V6:** 512 Expedientes (Bienes y Servicios).
- **Productividad:** El tiempo de ciclo promedio (desde la creación del expediente hasta la aprobación de la orden de servicio) ha disminuido de 7.5 días a 5.1 días (Reducción del 32%).
- **Tasa de Uso IA (RAG):** 100% de los expedientes requirieron evaluación de Experiencia. El motor extrajo candidatos automáticamente en el 82% de las ofertas. El 18% requirió fallback manual total debido a mala legibilidad de PDF (ver Incidentes).

## 2. Incidentes Documentados (Post-Hypercare)
- **Calidad Documental**: El 15% de los escaneos de proveedores llegan rotados, manchados o a resoluciones < 150dpi, causando que Tesseract OCR falle y devolviendo `MISSING_DATA` en el `ExperienceExtractionEngine`.
- **RAG Latency Threshold**: Los expedientes de más de 1,000 páginas demoran ~12 segundos en la fase Retrieval, superando el SLA deseado de 8s de la UI.

## 3. Feedback Cualitativo
- *"El bloqueo del supervisor (Dashboard) me obligó a devolver 3 expedientes con proveedores inhabilitados en RNP. Antes los aprobábamos y Contraloría nos observaba 6 meses después."* - **Jefe de Adquisiciones.**
- *"Necesitamos que el sistema nos avise ANTES si el PDF está borroso. A veces corremos todo el flujo solo para darnos cuenta al final."* - **Operador LOG.**

## 4. V6.0.1 Prioritization

En base al impacto operacional, las prioridades inmediatas son:
1. **Document Quality Assistant** (Detección temprana de OCR pobre).
2. **RAG Chunk Optimization** (Refinar tamaño de chunks para bajar latencia en PDFs masivos).
3. **Supervisor Analytics** (Exportar Data del Snapshot a CSV sin construir un BI pesado).
4. **UX Improvements** (Animaciones de Loading mientras el Celery Worker extrae experiencia).
