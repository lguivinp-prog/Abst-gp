# Local API Contract Inventory

## Authentication
- **LOGIN**: `POST /api/v1/auth/login` (READY - Retorna JWT real según usuario).

## Core Capabilities
- **EXPEDIENTES**: `GET/POST /api/v1/expedientes` (READY - CRUD básico).
- **DOCUMENTS / UPLOAD**: `POST /api/v1/expedientes/{id}/documents` (READY - Acepta multipart/form-data).
- **REQUIREMENTS**: `GET /api/v1/expedientes/{id}/requirements`, `PUT /api/v1/requirements/{id}` (READY).
- **SUPPLIERS**: `GET/POST /api/v1/expedientes/{id}/suppliers` (READY).
- **QUOTATIONS**: `POST /api/v1/expedientes/{id}/quotations` (READY).
- **DECISION (Supervisor)**: `POST /api/v1/expedientes/{id}/decisions` (READY).
- **CONTRACT ACCURACY**: `POST /api/v1/expedientes/{id}/contract-accuracy` (READY).
- **OUTPUT**: `GET /api/v1/expedientes/{id}/outputs` (READY - Retorna preview HTML).

## Unimplemented / Deferred
- **OCR / EXTRACTION**: PARTIAL (Pipeline backend asíncrono existe, la abstracción local se encarga de inyectar synthetic requirements tras upload).
- **EXPERIENCE / ANNEX3**: MISSING (Diferido a futuras iteraciones).
- **EVALUATION**: MISSING (Matriz de evaluación se computa en UI).
