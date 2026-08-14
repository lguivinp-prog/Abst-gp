# Abast-gp V6 - Sovereign Telemetry Policy

## 1. Principio de Soberanía Digital
Abast-gp reconoce que los procesos de adquisición pública del Estado contienen información sensible y legalmente protegida. La Arquitectura V6.1 introduce un canal de **Telemetría Institucional**, pero se subordina absolutamente a la Ley de Protección de Datos Personales y a las directivas de Ciberseguridad de la PCM.

## 2. Definición de Telemetría Anonimizada
El modelo de datos (`InstitutionalTelemetryEvent`) agrupa métricas matemáticas y conteos. **Queda estrictamente prohibido y bloqueado por arquitectura:**
- Extraer RUCs o Razones Sociales de proveedores.
- Extraer el texto transcrito de los contratos (RAG/OCR).
- Transmitir identificadores físicos de expedientes (Case IDs).

### ¿Qué se transmite?
- `avg_rag_latency_ms`: ¿Qué tan rápido responde la IA en sus servidores locales?
- `rag_human_correction_rate`: ¿El OCR está leyendo basura o el RAG se está equivocando mucho?
- `api_fallback_events`: ¿Cuántas veces se cae la SUNAT/RNP al mes en su región?

## 3. Opt-in y Consentimiento Institucional
- La telemetría viene **APAGADA (Opt-Out)** por defecto de fábrica.
- Para activarla, la Oficina General de Administración (Administrador TI) debe aceptar explícitamente el "Pacto de Mejora Continua" desde la interfaz de *Admin Governance*.
- La activación de este _flag_ dispara un evento inmutable en el `AuditLog` del propio Tenant: `TELEMETRY_OPT_IN_GRANTED`.
