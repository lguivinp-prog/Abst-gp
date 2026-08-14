# UX/UI Blueprint V1.0 - Abst-gp

## 1. Visual Identity & Brand Architecture
- **Brand Architecture:** "ABAST-GP — una solución de Luis Guivin" (Personal brand is subordinate to the product brand).
- **Style:** Corporate + Modern SaaS. Clear, professional hierarchy optimized for Edge/Chrome on desktop monitors.

### Approved Color Palette
- **Primary Navy:** `#1D2B4E` (Main headers, sidebar background, strong emphasis).
- **Action Blue:** `#2F6BFF` (Primary buttons, active states, links).
- **Light Blue:** `#E9F0FF` (Hover states, subtle active backgrounds, alerts).
- **Background:** `#F5F7FB` (App main background).
- **Surface:** `#FFFFFF` (Cards, modals, paper elements).
- **Main Text:** `#172033` (Body text, headings).
- **Secondary Text:** `#667085` (Helper text, disabled text, placeholders).
- **Success:** `#157A55` (CUMPLE, Approved).
- **Warning:** `#A15C00` (OBSERVADO, Review Required).
- **Danger:** `#B42318` (NO CUMPLE, Blocked, Errors).
- **Information:** `#0E7490` (MEJORA, Helpful tips).

## 2. General UX Rules
- **State Feedback:** Every state (success, warning, error) must combine color, text, and an icon for accessibility.
- **Navigation:** Persistent Navy sidebar for primary navigation (Dashboard, Cases, Suppliers, Rules, Users, Audit, Help).
- **Data Density:** Tables must be readable, allowing row expansion for long text rather than truncating critical procurement data.
- **Configurability:** The entity's logo can replace or sit alongside the ABAST-GP logo in the top-left corner.

## 3. Core Screens Blueprint

### 3.1 Supervisor Dashboard
- **Purpose:** Provide a bird's-eye view of team productivity and pending approvals.
- **Components:** 
  - KPI Cards: Active cases, Pending Review, Pending Approval, Document Errors, Blocked Suppliers.
  - Quick Actions: "Crear Expediente" primary button.
  - Recent Activity Feed (Audit glimpse).
- **Empty State:** "No hay expedientes activos. Crea el primer expediente para comenzar."

### 3.2 Operator Dashboard
- **Purpose:** Task management and focus for the evaluator.
- **Components:**
  - KPI Cards: My Active Cases, Assigned Cases, Pending Tasks.
  - Processing Queue: Shows documents currently being processed by OCR.
  - Actionable list of assigned cases with status pills.

### 3.3 Case Wizard (Creation & Upload)
- **Purpose:** Guide the user step-by-step to prevent skipping mandatory validations.
- **Steps:** 
  1. **Metadata:** Denomination, type (Bien/Servicio), area.
  2. **Base Document Upload:** Drag-and-drop for TDR/EETT.
  3. **Classification Check:** System shows classified pages; user confirms.
- **Loading State:** Skeleton loaders for document parsing, with reassuring text ("Extrayendo requerimientos técnicos...").

### 3.4 Editable Matrix View
- **Purpose:** Human-in-the-loop validation of AI extraction.
- **Components:** Split view. Left side: PDF viewer (TDR/EETT). Right side: Extracted JSON data rendered as an editable form/table.
- **Actions:** Add row, Delete row, Edit field, "Validar Matriz" (Primary Action).
- **Validation:** Matrix cannot proceed if mandatory fields (e.g., Cantidad) are empty.

### 3.5 Supplier Pre-Validation Gate
- **Purpose:** Enforce legal compliance before technical evaluation.
- **Components:** Table listing SUNAT, RNP, CIIU status per supplier.
- **States:** 
  - Passed: Green check. 
  - Failed: Red cross, entire row locked.
  - Reopened (Supervisor only): Yellow lock icon with "Excepción Auditada" tooltip.

### 3.6 Comparison Matrix
- **Purpose:** The core evaluation tool.
- **Components:** 
  - Horizontal scrollable table. Rows = Matrix Requirements. Columns = Suppliers.
  - Badges inside cells: `[CUMPLE]`, `[NO CUMPLE]`, `[OBSERVADO]`, `[MEJORA]`.
  - Clickable cells open a modal showing the exact PDF snippet and page number as evidence.
- **Actions:** "Seleccionar Proveedor" button at the top of each supplier column.

### 3.7 Selection & Justification Modal
- **Purpose:** Capture the decision-making rationale.
- **Components:** 
  - Textarea for justification (Mandatory if selecting a non-optimal supplier).
  - File upload for optional external evidence.
- **Validation:** "Aprobar Selección" remains disabled until the textarea exceeds 20 characters (if justification is required).

### 3.8 Result & Approval
- **Purpose:** Final output generation.
- **Components:** 
  - Preview of "Condiciones Contractuales" and "Informe de Evaluación".
  - "Enviar a Supervisor" (Operator) or "Aprobar y Liberar" (Supervisor).
  - Export options (Copy, DOCX) completely disabled and grayed out until Supervisor approval is logged.
