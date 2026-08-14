# Contract Accuracy Gate V1.0

## 1. Definition
The Contract Accuracy Gate is a strict, non-negotiable set of systemic constraints applied to the final output generation (Contractual Conditions and Evaluation Report). Its purpose is to completely eliminate generative AI hallucinations in legally binding public procurement documents.

## 2. Core Directives
- **Zero Hallucination Tolerance:** The final generated text must ONLY be sourced from the validated matrix, verified data, confirmed improvements (mejoras), and approved decisions.
- **Prohibited Inventions:** The system is explicitly blocked from inventing, interpolating, or assuming:
  - Names (Business or Contact)
  - RUC / DNI numbers
  - Monetary amounts
  - Quantities
  - Dates and deadlines
  - Warranties
  - Technical characteristics
  - Experience metrics
  - Deliverables and obligations

## 3. Traceability Requirement
Every data point injected into the final output MUST retain a metadata payload containing:
1. **Source Document** (e.g., "Anexo 4 - Proveedor A.pdf")
2. **Page Number**
3. **Source Fragment** (The exact text crop from the OCR)
4. **Confidence Score** (Float 0.0 - 1.0)
5. **Validating User** (ID of the Operator/Supervisor who approved the matrix)
6. **Validation Date**

## 4. Contractual Improvement Rules (Mejoras)
The system may only substitute a base requirement (from TDR/EETT) with a supplier's offered improvement if ALL the following conditions are met:
- It is **explicitly** stated in the supplier's documentation.
- It is strictly **favorable** to the State (e.g., shorter delivery time, longer warranty).
- It is **compatible** with the base requirement.
- It is **confirmed** and **approved** by the user.
- *CRITICAL:* The supplier's price MUST NEVER be classified or processed as a technical added value.

## 5. Conflict Resolution & Blocking
- **Low Confidence:** Any extracted data point with a confidence score below the configured threshold must be flagged as `REQUIERE REVISIÓN` in the UI. The user must manually confirm or edit it before proceeding.
- **Irreconcilable Conflict:** If a supplier's documents contradict each other (e.g., Annex 4 says 10 days, brochure says 15 days), the system must raise a `CONFLICTO` alert.
- **Blocking Rule:** The final output generation (Copy/Export) is HARD-BLOCKED if there are any unresolved `REQUIERE REVISIÓN` or `CONFLICTO` tags in the selected supplier's column.

## 6. Output Export Control
Exporting (Copy to Clipboard, DOCX generation) is physically disabled in the UI and blocked at the API level until the `Supervisor` role explicitly sets the case status to `APPROVED`. No draft documents can leave the system.
