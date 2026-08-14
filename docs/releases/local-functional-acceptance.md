# Local Functional Acceptance Checklist

Este checklist evalúa si el producto es utilizable end-to-end por un usuario humano a través de una interfaz de usuario local.

- [x] **Startup:** PASS (Los servicios backend, worker y db inician vía Docker Compose).
- [ ] **Login:** FAIL / NOT_IMPLEMENTED (No hay UI de Login, solo JWT issuance vía API cruda).
- [ ] **Create expediente:** FAIL / NOT_IMPLEMENTED (No hay UI para crear expedientes).
- [ ] **Upload PDF:** FAIL / NOT_IMPLEMENTED (Solo endpoint multipart/form-data en API).
- [ ] **OCR/extract:** PARTIAL (Pipeline backend existe y funciona aislando endpoints, pero inaccesible para usuario final).
- [ ] **Requirement matrix:** FAIL / NOT_IMPLEMENTED (No existe UI para renderizar ni corregir la matriz).
- [ ] **Human validation:** FAIL / NOT_IMPLEMENTED.
- [ ] **Supplier A/B:** FAIL / NOT_IMPLEMENTED.
- [ ] **Quotes:** FAIL / NOT_IMPLEMENTED.
- [ ] **Annex 4:** FAIL / NOT_IMPLEMENTED.
- [ ] **Evaluation:** FAIL / NOT_IMPLEMENTED (Lógica de negocio existe en Python, pero no es operable).
- [ ] **Annex 3:** FAIL / NOT_IMPLEMENTED.
- [ ] **Experience:** FAIL / NOT_IMPLEMENTED.
- [ ] **Supervisor decision:** FAIL / NOT_IMPLEMENTED (No hay interfaz de aprobación).
- [ ] **Contract Accuracy Gate:** PARTIAL (Aserciones backend existen, sin front).
- [ ] **Output:** FAIL / NOT_IMPLEMENTED (No hay visor de reportes).
- [ ] **Restart/persistence:** PASS (Datos vectoriales y relacionales persisten en volúmenes Docker).
- [ ] **Role enforcement:** PASS (Roles en JWT existen y bloquean endpoints).

## Resultado Final
**LOCAL_PRODUCT_VALIDATION_FAILED**. El sistema carece de Frontend. Es un ecosistema puramente Headless/API. Un usuario de negocio no puede operarlo.
