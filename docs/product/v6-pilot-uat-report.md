# V6 Pilot User Acceptance Test (UAT) Report

## 1. Piloto Evaluado
Se ejecuto el caso piloto completo: "Adquisicion de Laptops Corporativas". Todo el flujo paso a traves de los motores deterministas sin invocar a un LLM productivo, validando puramente el esqueleto algoritmico de RAG y las evaluaciones heurísticas.

## 2. Resultados Operador
- **Facilidad**: Alta. El sistema no permite avanzar si un Anexo carece de validacion.
- **Pasos Confusos**: La separacion entre `OfferEvidence` y `ExperienceEvidence` genero dudas iniciales. Se aclarara en la UI que la Experiencia tiene un carril propio debido al peso normativo.
- **Errores**: Ninguno critico. La extraccion OCR en PDFs sucios genero fragmentos "ruidosos", pero la capa RAG lidio con ellos sin quebrar el motor.

## 3. Resultados Supervisor
- **Aprobacion**: El `CaseWorkflow` (DRAFT -> UNDER_REVIEW -> APPROVED) garantizo que los operadores no pudieran autogenerar contratos finales. 
- **Confianza**: Alta. Al visualizar que la UI del AI Assistant expone los "Retrieved Chunks" originales (gracias a `RAGContextBuilder`), los supervisores confian en que la IA no inyectara reglas fantasmas (zero hallucination).
- **Auditoria**: Cada paso transaccional (evaluar, seleccionar, exportar) fue verificado en la tabla `AuditLog`.

## 4. Security Review
- **RBAC**: Solo perfiles con rol "Supervisor" lograron autorizar el Output.
- **Tenant Isolation**: Validado. Consultas RAG inyectan estrictamente el `tenant_id` y `case_id` a traves de `EvidenceRetrievalService`.
- **Eliminacion**: Restringida. Casos en estado `APPROVED` impiden la eliminacion en cascada gracias a las llaves foraneas `RESTRICT` en los dominios de auditoria y templates.
