# V6 Supplier Offer Evaluation View - Functional Design

## 1. Overview
The Offer Evaluation View allows the contracting authority to compare the requirements defined in the `CaseRequirementMatrix` against the evidences presented in one or more `SupplierOffer`. It enforces a strict Human-in-the-Loop policy for validation, flagging improvements and conflicts but refusing automatic decisions.

## 2. Layout (Matrix Grid Pattern)
- **Header**: Case Name, Contract Type, Global status.
- **Data Grid (Table)**: 
  - **Rows**: The requirements (`CaseRequirementMatrix`). Grouped by Legal, Technical, Financial.
  - **Columns**: 
    - Col 1: Requirement details (Description, Value).
    - Col 2..N: Supplier Offers (e.g. "Tech Corp SAC", "Data Systems EIRL").
  - **Cells (`OfferEvaluation`)**: Show semantic labels:
    - `PASSED` (Green check)
    - `FAILED` (Red X)
    - `OBSERVED` (Orange warning)
    - `IMPROVEMENT` (Blue star, tooltip: e.g. "Mejora plazo: 5 dias vs 10 dias")
    - `CONFLICT` (Red block, tooltip: "Evidencias discordantes detectadas")
    - `MISSING_DATA` (Grey dash)

## 3. Data Representation & Validation
- **Click-to-Evidence**: Clicking a cell opens a side-panel displaying the `OfferEvidence` linked to that evaluation, showing the fragment extracted from the attached document (Anexo 4, Ficha técnica, etc.).
- **Human Resolution**: The user MUST click an action button (`Validar`, `Rechazar`, `Observar`) inside the side-panel for each row.
- **Conflict Resolution**: If a cell is in `CONFLICT`, the user cannot globally approve the offer until they manually select which evidence holds true, changing the cell's state and logging an audit `reason`.

## 4. Security & Constraints
- **Price is not Improvement**: Price columns are treated strictly as `ECONOMIC_DATA` and cannot trigger the `IMPROVEMENT` tag.
- **Block Contract Generation**: If any `OfferEvaluation` row is marked as `CONFLICT`, the entire parent `SupplierOffer` gets marked as `HAS_CONFLICTS`, blocking the UI from showing the "Proceed to Adjudication/Contracting" button.
