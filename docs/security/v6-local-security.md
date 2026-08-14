# V6 Local Security Hardening

## 1. Secret Management
- Nunca alojar passwords o API Keys en codigo fuente ni en Dockerfiles.
- El sistema inyecta dependencias sensibles via `.env` (no trackeado en GIT).
- Keys de LLMs futuros residen puramente en la capa del SO o Vault externo.

## 2. Politicas de Acceso (RBAC & Tenant)
- Todo endpoint de `/api/v6/` hereda el Auth Dependency requiriendo un Bearer Token JWT valido.
- **Tenant Isolation:** V6 impone filtrado severo (Where clauses) por `tenant_id` garantizando que un Tenant jamas vea o evalue data de otro.
- **Roles:**
  - `OPERATOR`: Puede crear casos, cargar evidencia y solicitar AI RAG.
  - `SUPERVISOR`: Unico rol que puede ejecutar `POST /api/v6/cases/{id}/approve` y emitir firmas contractuales.

## 3. Storage Lifecycle & AI Policy
- **Eliminacion (Soft Delete vs Hard Delete):** No se permite el Hard Delete de expedientes con estado `APPROVED`. Solo retenciones normativas caducas desencadenan purgas historicas (Archivado offline).
- **AI Data Policy**: 
  - Prohibido enviar datos marcados como PII puro si no aportan a la evaluacion (Anonimizacion futura).
  - Modelos externos operan bajo "Zero Data Retention" agreements.
  
## 4. AuditLog Transaccional
Cada modificacion de estado en `CaseWorkflow`, `SupplierSelection` y `GeneratedOutput` es interceptada por el ORM e insertada en `audit_logs` con `user_id` y timestamp inmodificable, sirviendo como cadena de custodia.
