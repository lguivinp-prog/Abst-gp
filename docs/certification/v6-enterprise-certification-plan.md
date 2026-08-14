# Abast-gp V6 Enterprise Certification Plan

## 1. Propósito de Certificación
Antes de empaquetar Abast-gp V6 como solución definitiva (V6.1) apta para escalar a todos los pliegos presupuestales del Estado, la arquitectura completa (Core V5.5 + AI Assistant V6) debe superar un panel de certificación enterprise y de ciberseguridad gubernamental.

## 2. Seguridad & Aislamiento (Security Layer)
- **Tenant Isolation Certification**: Pruebas de pentesting demostrando que un RAG Prompt Injection no puede exponer contratos de la `Oficina A` a la `Oficina B` (Vector Store Compartmentalization).
- **RBAC Audit**: Certificar que la directiva `SUPERVISOR_EXCEPTION_SELECT` está aislada a nivel de Token JWT y que toda ejecución impacta criptográficamente el `AuditLog`.
- **Zero-Knowledge Providers**: Certificar que las firmas `.env` de las APIs gubernamentales (SUNAT/RNP) no se fugan en los logs de la aplicación.

## 3. Estabilidad Arquitectónica (Architecture & DR)
- **V5.5 Legacy Preservation**: Los auditores externos deberán ejecutar `pytest tests/dr/test_disaster_recovery.py` para constatar matemáticamente que los motores asíncronos V6 jamás mutan el core original de persistencia transaccional.
- **RAG Latency SLA**: Certificar que el 95% de las búsquedas en contratos > 500 páginas responden en < 2.0 segundos, avalando la estrategia de `Generators` y `Top-K Dinámico`.

## 4. Operación & Contingencia (Operational Resilience)
- **Fallback Certification**: Simular caídas de las APIs de SUNAT/RNP (apagando red externa). Certificar que el sistema degrada a `MANUAL_REQUIRED` y permite completar el expediente sin colgar la UI.
- **OCR Resilience**: Cortar RAM del contenedor Celery. Certificar que el `Document Quality Assistant` purga correctamente el caché de memoria (`/tmp/abast_uploads`) para evitar saturación de volúmenes Docker.

## 5. Matriz de Pruebas Obligatorias (Test Evidence)
El paquete de certificación exigirá la adjunción de los siguientes reportes CI/CD:
- `v6.0.1-regression-matrix.md` (Aprobado al 100%).
- `v6-rc1-validation-report.md`.
- Resultados en crudo de `pytest backend/tests/unit/v6/` con cobertura mínima del 90%.
