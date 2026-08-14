# V6 Requirement Matrix View - Functional Design

## 1. Overview
The Requirement Matrix View is the core interface for the "Assisted Extraction" feature in V6. It acts as the Human-in-the-Loop (HITL) gatekeeper to ensure no AI decisions are applied without explicit human approval.

## 2. Layout (Split-View)
The UI will adopt a split-pane layout to maximize context switching efficiency:
- **Left Pane (50%) - Document Viewer**: Renders the original PDF or text document.
- **Right Pane (50%) - Matrix Editor**: A reactive data table displaying the extracted requirement candidates.

## 3. Data Representation
Each row in the Matrix Editor represents a `RequirementCandidate` or `CaseRequirementMatrix` entry.
Columns:
- **Status Indicator**: Color-coded tag (`PENDING_REVIEW` [Yellow], `VALIDATED` [Green], `MODIFIED_BY_USER` [Blue], `OBSERVED` [Orange], `REJECTED` [Red]).
- **Requirement Type**: Dropdown (Technical, Legal, Financial).
- **Description**: Text area (Editable).
- **Value**: Text input (Editable).
- **Confidence**: Progress bar or percentage text (e.g., 60%). 
- **Actions**: Approve (Checkmark), Modify (Pencil), Reject (X).

## 4. Interaction Flows
- **Context Syncing**: Clicking on a requirement row will automatically scroll the Left Pane Document Viewer to the `source_page` and highlight the `source_fragment` retrieved from the `RequirementEvidence`.
- **Validation**: Clicking "Approve" triggers a `PUT /api/v6/cases/{id}/requirements/{req_id}` with status `VALIDATED` and updates the row instantly.
- **Modification**: Editing the text directly marks the row as `MODIFIED_BY_USER` and forces a reason prompt to satisfy AuditLog evidence trails.

## 5. Security & Constraints
- The UI MUST disable batch approval (e.g., "Approve All" button) to enforce strict review.
- The UI MUST NOT allow the user to bypass the reason prompt when transitioning to `OBSERVED` or `REJECTED`.
