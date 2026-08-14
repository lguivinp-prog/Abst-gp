# V6 Implementation Architecture Plan - Abst-gp

## 1. SUMMARY
Este documento define la arquitectura técnica consolidada para la evolución de Abst-gp hacia el **V6 Local Enterprise Assistant**. Integrando las directrices del CTO, la arquitectura no solo contempla validaciones externas y la prevención de alucinaciones de IA (Contract Accuracy Gate), sino que formaliza el perfil inteligente del proveedor, la preparación estructurada de órdenes de compra/servicio y un motor de plantillas de salida institucional. La base certificada V5.5 (Disaster Recovery) permanece inalterable.

## 2. ARCHITECTURE CHANGES (CTO REVIEW)
Las siguientes directivas arquitectónicas han sido integradas previo al Sprint 1:
- **Formalización de Entidades:** `SupplierProfile` y `OrderPreparationProfile` existen como modelos formales, no solo como vistas.
- **Motor de Salidas:** Incorporación del `OutputTemplateEngine` para orquestar la generación documental dinámica.
- **Validación Resiliente:** El flujo de validación externa (SUNAT, RNP, FUP, CIIU) adopta una máquina de estados tríadica (`PASSED`, `WARNING`, `BLOCKED`) con jerarquía de excepción auditada.
- **Trazabilidad Externa:** El `External Integration Layer` impone un registro criptográfico (hash) y de caché temporal por cada interacción con el Estado.
- **Safety First:** Inserción de la Fase 0 (Characterization Tests) como pre-requisito a cualquier migración.

## 3. UPDATED DOMAIN MODEL
- **`CaseFile` (Expediente):** Entidad raíz del proceso de contratación.
- **`CaseRequirementMatrix` (Matriz validada):** Requisitos técnicos (TDR/EETT) destilados y ratificados por el Operador.
- **`Supplier` (Proveedor):** Entidad base que rastrea el identificador fiscal.
- **`SupplierProfile` (Ficha Inteligente):** Entidad formal de agregación histórica. Consolida: datos generales (RUC, representante, DNI), historial de evaluaciones previas, validaciones externas vigentes y resultados acumulados.
- **`SupplierOffer` (Oferta):** Instancia transaccional de postulación.
- **`OrderPreparationProfile` (Perfil de Orden):** Entidad transitoria post-adjudicación. Agrupa: proveedor seleccionado, RUC, dirección, contacto, monto adjudicado, plazo, garantía, condiciones y mejoras confirmadas. Lista para volcado a sistemas estatales (ej. SIAF, PLADICOP).

## 4. UPDATED DATABASE PLAN
La persistencia estructural se ejecutará en **3 Migraciones incrementales** para minimizar impacto y permitir rollbacks controlados.

**Migración 1 (Core Operacional):**
- `case_requirement_matrices`
- `suppliers`
- `supplier_offers`

**Migración 2 (Inteligencia & Auditoría):**
- `supplier_profiles` (Vista materializada o tabla de consolidación dependiente).
- `supplier_validations` (Log transaccional: fuente, fecha, usuario, payload_respuesta, hash_respuesta, expiracion_cache).
- `supplier_economic_activities` (Catálogo INEI: codigo_ciiu, descripcion, version_catalogo, relacion_objeto).
- `evaluation_decisions`

**Migración 3 (Generación & Salida):**
- `output_templates` (OutputTemplateEngine: tipo, version, vigencia, configuracion_entidad, body_template).
- `order_preparation_profiles`

## 5. EXTERNAL INTEGRATION LAYER (EIL)
El EIL abstrae las comunicaciones gubernamentales mediante adaptadores dedicados (`SUNATAdapter`, `RNPAdapter`, `FUPAdapter`, `CIIUAdapter`). 

**Trazabilidad Obligatoria:** Todo adaptador debe inyectar a la base de datos:
- `fuente` (ej. API_SUNAT_V1).
- `fecha_consulta` (Timestamp UTC).
- `usuario` (Solicitante).
- `respuesta` (JSON Payload original).
- `hash_respuesta` (SHA256 del Payload para inmutabilidad).
- `expiracion_cache` (TTL).

**Estados de Validación:**
- **`PASSED`:** (Ej. RUC Activo/Habido). Flujo normal.
- **`WARNING`:** (Ej. Timeout del RNP). Permite evaluación, pero levanta alerta.
- **`BLOCKED`:** (Ej. Baja Definitiva). Bloquea la oferta. Excepción exclusiva para `Supervisor`, requiriendo texto de sustento insertado en `AuditLog`.

## 6. CIIU INEI ENGINE
- **Estructura:** Almacena código, descripción oficial, fuente (INEI), y versión del catálogo.
- **Funcionalidad:** Cruza la actividad del proveedor contra el objeto del expediente.
- **Semántica de Resultados:** `Alta relación`, `Media relación`, `Baja relación`, `No identificada`.
- **Regla Estricta:** El sistema *nunca* aprueba automáticamente. El usuario dictamina `Cumple`, `No cumple` u `Observado`, guardando la fecha, usuario y fuente de la decisión.

## 7. UPDATED API PLAN
Nuevos contratos bajo `/api/v1`:
- `GET /suppliers/{ruc}/profile` -> Retorna el `SupplierProfile` consolidado.
- `GET /cases/{id}/order-profile` -> Obtiene el `OrderPreparationProfile`.
- `POST /cases/{id}/exceptions/validation` -> (Supervisor only) Desbloquea un estado `BLOCKED` con sustento.
- `POST /templates/render` -> Invoca el `OutputTemplateEngine` con la plantilla vigente.

## 8. AI GOVERNANCE & CONTRACT ACCURACY GATE
- **Límites IA:** Prohibido declarar cumplimiento normativo/legal, inventar RUC/DNI/Montos/Plazos o auto-seleccionar proveedores. Sugerencias limitadas a "CUMPLE_SUGERIDO".
- **Contract Accuracy Gate:** El `OutputTemplateEngine` compila la OC/OS/Contrato inyectando *solamente* datos del `OrderPreparationProfile` y `CaseRequirementMatrix`. Todo bloque de texto exige traza de auditoría (`source_document`, `page`, `confidence`, `validated_by_user`). 

## 9. UPDATED IMPLEMENTATION PHASES
- **FASE 0 - Implementation Safety:** Characterization Tests sobre OCR, Storage, Jobs, Processing y DR. Garantiza que la cobertura actual documente fielmente la entropía antes de codificar.
- **FASE 1 - Foundation:** Migración 1. Modelos, contratos API.
- **FASE 2 - Expedientes:** Wizard, carga, extracción, matriz.
- **FASE 3 - Proveedor Inteligente:** Migración 2. Integración EIL (SUNAT, RNP, FUP, CIIU) y Ficha Consolidada (`SupplierProfile`).
- **FASE 4 - Comparación:** Matrices, mejoras, evaluación de experiencia.
- **FASE 5 - Resultados & Templates:** Migración 3. `OutputTemplateEngine`, `OrderPreparationProfile`, aprobación.
- **FASE 6 - IA Asistente:** Habilitación RAG normativo confinado al caso.
- **FASE 7 - SaaS Multi-entidad:** Multi-tenant Cloud final.

## 10. TEST STRATEGY
- Mantenimiento **estricto y sin modificaciones** de `pytest tests/dr/test_disaster_recovery.py -v`.
- **Fase 0 Tests:** Characterization testing para cimentar comportamientos legacy.
- **EIL Mocks:** Mocks inyectables para respuestas de SUNAT/INEI en unit testing.
- **Output Validation:** Comprobación rigurosa contra el *Contract Accuracy Gate*.

## 11. UPDATED RISKS
- **Complejidad del Template Engine:** Mantener un versionado de plantillas que varían por entidad (SaaS futuro) puede encarecer el mantenimiento si no se aplican gramáticas restrictivas (ej. Jinja2 sandboxed).
- **Sobrecarga de Auditoría:** El hashing criptográfico de cada payload de integración SUNAT/RNP inflará la base de datos si no se imponen políticas de purga anual.

## 12. OPEN DECISIONS
- **Motor de Renderizado Documental:** Queda por definir la biblioteca exacta para el `OutputTemplateEngine` (ej. DocxTemplate vs generación PDF pura desde HTML).
