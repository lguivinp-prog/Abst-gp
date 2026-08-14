# V6 Experience Evaluation View - Functional Design

## 1. Overview
Esta pantalla compara visualmente lo que exige el TDR (Requisito de Experiencia) frente a lo que declara el proveedor (Evidencia de Experiencia, Anexo 3) y ofrece la capacidad de auditar cada afirmación hasta el contrato fuente.

## 2. Layout Principal (Split Screen)

### Lado Izquierdo: Requerimiento Mínimo
- **Monto Mínimo Requerido**: S/ 100,000.00
- **Objeto Similar**: "Servicios de Limpieza o Mantenimiento"
- **Periodo**: Últimos 8 años.
- **Resultado Sugerido por IA**: 🟢 **PASSED** (Total Validado: S/ 150,000.00)

### Lado Derecho: Evidencias (Anexo 3 & Contratos)
Una lista de tarjetas (Cards). Cada tarjeta es una `ExperienceEvidence`.

#### Card Estado: 🟡 UNDER_REVIEW / EXTRACTED
- **Entidad**: Ministerio MOCK
- **Objeto Extraído**: Servicio de Limpieza
- **Monto Extraído**: S/ 150,000.00
- **Fecha**: 10/10/2023
- **Snippet RAG**: _"...El contratista brindó el servicio por 150000 soles..."_
- **Acciones (Botones)**: `[ VALIDAR EVIDENCIA ]` / `[ RECHAZAR EVIDENCIA ]` / `[ VER PDF ORIGEN ]`

## 3. Dinámica del Flujo
1. La IA (RAG) extrae candidatos y los coloca como `EXTRACTED` o `UNDER_REVIEW`.
2. El Operador lee el fragmento y valida.
3. Al hacer clic en `[ VALIDAR EVIDENCIA ]`, el monto pasa a ser un monto legalmente computable para el sistema (`VALIDATED`).
4. El Motor Evaluador corre en background y actualiza el Resultado Sugerido a `PASSED`.
5. Si el sistema calcula `FAILED`, el Operador puede buscar manualmente en el PDF y crear una evidencia desde cero.

## 4. Status del Proveedor
En la cabecera superior existirá el **Validation Summary Panel**:
- [SUNAT: 🟢 PASSED]
- [RNP: 🟢 PASSED]
- [FUP: 🟢 PASSED]
- [CIIU: 🟡 WARNING]
- [EXPERIENCE: 🟢 PASSED]
- **OVERALL STATUS**: `VERIFIED`
