# V6.0.1 Document Quality Assistant - UX Blueprint

## 1. Contexto Operativo
Cuando un Operador arrastra un Contrato o Anexo escaneado a la zona de subida (Upload), el sistema lo procesa en _background_ antes de confirmar la carga.

## 2. Panel de Resultado Inmediato (Scorecard)

### Escenario: QUALITY_GOOD
- **Icono**: Check Verde (✅)
- **Mensaje**: "Documento procesado correctamente (300 DPI, Contraste OK). Iniciando Inteligencia RAG."

### Escenario: QUALITY_WARNING
- **Icono**: Triángulo Amarillo (⚠️)
- **Mensaje**: "El documento fue aceptado, pero presenta advertencias:"
- **Problemas**: 
  - `[Inclinado 6 grados]`. El motor intentará corregirlo, pero la extracción de datos podría ser inexacta.
- **Acción (Opcional)**: "Continuar" o "Reemplazar".

### Escenario: QUALITY_EXCEPTION_REQUIRED
- **Icono**: Semáforo Naranja (🟧)
- **Mensaje**: "El documento tiene una calidad crítica. La lectura OCR automática probablemente falle."
- **Problemas**:
  - `[Baja Resolución: 90 DPI (Mínimo: 150)]`
  - `[Alta difuminación detectada]`
- **Acción Requerida**: Botón _"Solicitar Excepción al Supervisor"_ (Deja traza en AuditLog) o _"Descartar y Resubir"_.

### Escenario: QUALITY_BLOCKED
- **Icono**: Cruz Roja (❌)
- **Mensaje**: "Documento RECHAZADO por inviabilidad de lectura."
- **Problemas**:
  - `[Páginas vacías detectadas]`
- **Acción Obligatoria**: Vuelva a escanear asegurándose de que el archivo contiene texto (Elimine hojas en blanco). El botón de Continuar está desactivado.
