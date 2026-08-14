# Abast-gp V6.1 - Admin Governance Dashboard (API Integrated)

## 1. Diseño General (UI)
El Dashboard Administrativo se divide en 4 pestañas operadas por React, consumiendo la API `v6_admin.py`.

## 2. Pestaña 1: Configuración OCR (Thresholds)
- **Umbral de DPI (`min_dpi`)**: Deslizador desde 72 hasta 600 DPI.
  - *Límite de API:* No permite bajar de 72 DPI (Bloqueado por Backend).
- **Umbral RAG (`min_rag`)**: Confianza requerida (50% a 99%).
- **Botón `[ Guardar Ajustes ]`**: Llama a `PUT /api/v6/admin/config/thresholds`. Exige justificación.

## 3. Pestaña 2: Telemetría Soberana
- **Estado de Opt-In**: Toggle Activar/Desactivar.
- **Transparencia**: Muestra exactamente qué datos extrae el *Worker* asíncrono. Ningún nombre o monto.
- **Acción**: Llama a `PUT /api/v6/admin/config/telemetry`.

## 4. Pestaña 3: Historial de Configuración (Auditoría)
Muestra una tabla generada desde el modelo `TenantConfigurationHistory`:
- **V2**: `min_dpi` cambió de 150 a 300 por el usuario "AdminIT" (Motivo: "Mejora de OCR").
- **V3**: `telemetry_opt_in` cambió de False a True.

## 5. Pestaña 4: Gestión de Usuarios y Accesos
- Visualización de la plantilla laboral.
- Visibilidad del Token temporal `BREAK_GLASS` en caso de intervención P1 del Nivel 3.
