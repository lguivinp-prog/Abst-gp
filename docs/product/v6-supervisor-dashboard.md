# V6 Supervisor Dashboard - Functional Design

## 1. Overview
El Supervisor Dashboard es la capa ejecutiva que centraliza la salud operacional de los procesos de abastecimiento. Su propósito es proveer visibilidad inmediata sobre bloqueos (Riesgo HIGH) y cuellos de botella (Riesgo MEDIUM), permitiendo autorizar o auditar acciones.

## 2. Layout Principal (Grid 3-Columnas)

### Columna 1: KPIS y Métricas
- **Expedientes Activos**: 45
- **En Riesgo Alto**: 3
- **Bloqueos Detectados**: 2
- **Tiempo Promedio de Cierre**: 3.5 días

### Columna 2: Approval Queue (Bandeja Priorizada)
Una lista iterativa ordenada automáticamente por `risk_level` DESC.
**Item Template**:
- **[🔴 HIGH] Expediente #104 - Adquisición de Laptops**
  - _Motivo:_ SUPERVISOR_EXCEPTION_SELECT (Auditoría pendiente)
- **[🟡 MEDIUM] Expediente #105 - Servicios Limpieza**
  - _Motivo:_ INCOMPLETE_EVIDENCE (Proveedor PENDING)
- **[🟢 LOW] Expediente #106 - Material Oficina**
  - _Motivo:_ Flujo Limpio (Listo para aprobación)

### Columna 3: Case Detail & Audit (Al hacer click en un Expediente)
Dividido en dos pestañas:

#### Tab A: Supplier Summary (Solo Hechos)
- 🟢 SUNAT: Activo
- 🟢 RNP: Vigente
- 🟢 FUP: Limpio
- 🟡 CIIU: MEDIUM (Warning: "Comercio" vs "Limpieza")
- 🟢 EXPERIENCE: PASSED (S/ 150K calculados)
- **Status:** VERIFIED

_Nota: No existe botón "Recomendar Proveedor". El Supervisor lee los semáforos y toma su propia decisión legal._

#### Tab B: Audit Timeline
Visualización cronológica estricta:
- **10:00 AM**: Operador 1 creó el expediente.
- **10:15 AM**: Motor OCR RAG extrajo 3 fragmentos de Anexo 3.
- **10:45 AM**: Operador 1 validó fragmento 1 (`VALIDATED`).
- **10:45 AM**: Motor de Evaluación calculó `PASSED` (Trace ID #44).
- **11:00 AM**: Operador 1 intentó seleccionar y falló (Permiso denegado).
- **11:05 AM**: Supervisor Forzó la Selección (`SUPERVISOR_EXCEPTION_SELECT`).
