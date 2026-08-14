# V6 Output Generation View - Functional Design

## 1. Overview
The Output Generation View provides a safe interface to preview, approve, and export the final contractual documents (Conditions, Evaluation Report, OC/OS). It is strictly protected by the `ContractAccuracyGate`, meaning it cannot even be accessed if there are unresolved conflicts in the evaluation phase.

## 2. Layout (Document Viewer Pattern)
- **Left Sidebar**: List of generated outputs for the case (e.g., "Condiciones Contractuales v1.0", "Informe de Evaluacion v1.0").
- **Main Area**: Rich Text / HTML Preview of the selected document.
- **Top Bar**: Action buttons: `Approve Document`, `Export to PDF/DOCX`.

## 3. Data Representation & Traceability
- **Semantic Highlighting**: Variables injected by the `OutputTemplateEngine` (e.g., Supplier Name, Contract Amount) are highlighted in the preview.
- **Hover Traceability**: When the user hovers over a highlighted variable, a popover displays its `TemplateVariableRegistry` origin (e.g., "Source: SupplierProfile.business_name", "Validated by: User A at Timestamp").

## 4. Security & Export Rules
- **Approval Separation**: A generated document is initially in `GENERATED` state. The Supervisor must click `Approve Document` (transitioning to `APPROVED`) before the `Export` button is enabled.
- **Gate Enforcement**: If the `ContractAccuracyGate` yields `ACCURACY_FAILED`, a full-screen blocking overlay is shown: *"El expediente contiene errores de exactitud documental o carece de aprobacion previa. Resuelva los conflictos antes de generar."*
