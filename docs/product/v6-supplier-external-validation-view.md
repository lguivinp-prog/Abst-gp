# V6 Supplier External Validation View - Functional Design

## 1. Overview
Esta vista proporciona una radiografía integral del proveedor frente a los entes rectores del Estado (SUNAT, RNP, FUP) y valida la correspondencia técnica de su actividad (CIIU).

## 2. Layout (Panel de Validación)
- Se presenta como un widget de 4 cuadrantes dentro de `SupplierProfile`.
- Cada cuadrante muestra el nombre del proveedor de validación, el estado, y la fuente de la verdad.

## 3. Semáforos de Estado
- 🟢 **PASSED**: Validación exitosa (Ej. RUC Activo, RNP Vigente).
- 🟡 **WARNING**: Validación dudosa (Ej. CIIU "LOW" Certainty, o API caída y se usó documento manual no concluyente).
- 🔴 **BLOCKED**: Impedimento legal duro (Ej. FUP Sancionado).
- 🟣 **MANUAL_REQUIRED**: API caída y sin evidencia manual. Requiere acción del operador.

## 4. Trazabilidad
Debajo de cada semáforo, debe existir el link al payload crudo (JSON) que entregó la API, o el link al PDF de _fallback_ proveído manualmente por el operador.
