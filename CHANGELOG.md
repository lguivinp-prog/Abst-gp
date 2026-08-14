# Changelog - Abast-gp

## [6.0.0] - 2026-08-09
### Added
- **Inteligencia de Requerimientos**: Extracción OCR/Heurística del TDR para generación de matrices deterministas.
- **Inteligencia de Proveedores**: Adaptadores Híbridos de validación externa (SUNAT, RNP, FUP, CIIU) con tolerancia a fallos API.
- **Inteligencia de Ofertas & Experiencia**: Evaluación matemática y validación Humano-en-el-Bucle (Human-in-the-loop) para extraer contratos del Anexo 3 vía RAG.
- **Asistente IA (RAG Seguro)**: Motor contextual aislado estrictamente por Tenant/Expediente. No toma decisiones legales.
- **Dashboard de Supervisión**: Panel de Control para orquestar la bandeja de aprobación y monitorizar los Riesgos (LOW/MEDIUM/HIGH).
- **Flujo de Decisión / Output Engine**: Generación automática de contratos estructurados protegidos por el `ContractAccuracyGate`.

### Security
- Inmutabilidad estricta introducida a través de `AuditLog`.
- `SUPERVISOR_EXCEPTION_SELECT` para puentear bloqueos documentarios en situaciones de emergencia (e.g. Desabastecimiento inminente), dejando traza criptográfica/forense.
- Cero Secretos Estáticos: Migración a arquitecturas `.env` inyectadas para providers externos.

### Architecture
- V6 despliega como un conjunto de Sidecars asíncronos (Celery Workers) y orquestadores (Engines) construidos ALREDEDOR de la V5.5 Core.
- El Core Transaccional V5.5 y sus procesos de Recuperación Ante Desastres se mantienen congelados y 100% operativos.
