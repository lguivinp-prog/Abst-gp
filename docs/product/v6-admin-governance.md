# Abast-gp V6.1 - Admin Governance UI Blueprint

## 1. Propósito
Descentralizar la parametrización de la IA y el control de accesos, entregando el poder a las Oficinas de Tecnologías Institucionales sin depender del fabricante de Abast-gp.

## 2. Estructura del Panel de Control (Admin Dashboard)

### Tab 1: Gestión de Usuarios (RBAC)
- **Grid de Usuarios:** Listado de Operadores y Supervisores.
- **Acciones:** Revocar acceso, Asignar Rol `SUPERVISOR`, Resetear Contraseña.
- *Nota: Todo cambio impacta el `AuditLog` obligatoriamente.*

### Tab 2: Umbrales Algorítmicos (Thresholds)
- **Document Quality Threshold:** Deslizador (Slider) para definir el `min_dpi` aceptable. (Sugerido: 150. Restricto: 300).
- **RAG Confidence Gate:** Deslizador para ajustar cuándo el sistema marca un documento como `WARNING` por ambigüedad.

### Tab 3: Privacidad y Telemetría Soberana
- **Estado Actual:** 🔴 Desconectado (Datos confinados).
- **Toggle Switch:** `[ Habilitar Telemetría Anonimizada ]`
- **Modal de Consentimiento:** Muestra la versión actual de la política (`docs/security/v6-sovereign-telemetry-policy.md`) detallando exactamente las columnas del `InstitutionalTelemetryEvent` que se enviarán al Cloud de Abast-gp. Requiere firma electrónica o re-ingreso de contraseña del Administrador TI para confirmar el Opt-In.
