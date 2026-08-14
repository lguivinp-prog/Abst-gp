# Current UI Gap Analysis V1.0

## 1. Inspection Summary
Based on a direct inspection of the `frontend/src` directory structure within the `abst-v4_9-remediation-clean` branch, the current UI is a foundational React/Vite application. It contains basic routing and some feature folders, but it exhibits massive functional gaps when compared against the comprehensive V1.0 Product Requirements Document (PRD).

## 2. Existing Routes & Screens (Reported & Observed)
- `/login`: Exists (`LoginPage.tsx`). Handles basic JWT auth.
- `/cases`: Exists (`CasesList.tsx`). Displays a list of cases.
- `/cases/:id`: Exists (`CaseDetail.tsx`). Shows details of a specific case.
- `/settings`: Exists (`SettingsPage.tsx`).
- `/monitoring`: Exists (`MonitoringDashboard.tsx`).

## 3. Reusable Components
- **Layout System:** `Layout.tsx` and `ProtectedRoute.tsx` exist and function for basic session governance.
- **Error Boundary:** `ErrorBoundary.tsx` is implemented at the root level.
- **Auth Context:** `AuthContext.tsx` handles state.

## 4. Functional Gaps (Missing against PRD)
- **[GAP] Supervisor vs Operator Dashboards:** `CasesList.tsx` is a generic list. It lacks the KPI cards, task queues, and specialized views required for the different roles.
- **[GAP] Step-by-Step Wizard:** The UX Blueprint demands a guided wizard for Case Creation. Currently, case creation (if it exists) is likely a simple form or missing entirely.
- **[GAP] Split-View Matrix Validator:** `CaseDetail.tsx` (11KB) is too small to contain the complex PDF viewer + Editable JSON Matrix split-screen required for step 5.
- **[GAP] Pre-Validation Gate UI:** There is no distinct interface for the SUNAT/RNP/CIIU validation blocking mechanism.
- **[GAP] Comparison Matrix:** The horizontal, multi-supplier comparison table with `[CUMPLE]/[NO CUMPLE]` badges and evidence modals is entirely absent.
- **[GAP] Justification Modal:** The UI for capturing the user's rationale when selecting a supplier does not exist.
- **[GAP] Contractual Output View:** The final preview screen (Report and Contractual Conditions) with the Supervisor approval gate is missing.
- **[GAP] Document Q&A:** The interface for chatting/asking questions about the case is missing.

## 5. UX Debt & Re-design Requirements
- **Color Palette:** The `index.css`, `App.css`, and localized CSS files need a complete overhaul to inject the approved corporate palette (Primary Navy `#1D2B4E`, Action Blue `#2F6BFF`, etc.).
- **Component Library:** The current UI relies heavily on raw CSS (`CasesList.css`, `CaseDetail.css`). To meet the "Corporate + Modern SaaS" requirement, a robust component library (like Tailwind + shadcn/ui, or MUI) should be introduced to handle complex tables, modals, and status badges consistently.
- **Terminology:** Hardcoded text across all components must be audited to ensure strict adherence to Peruvian procurement lexicon (TDR, EETT, RNP, FUP).

## 6. Regression Risks
- Modifying `CasesList.tsx` or `CaseDetail.tsx` heavily to introduce the Wizard and Matrix views might break existing SRE/Telemetry tracking hooks if they are intertwined.
- The `MonitoringDashboard.tsx` currently exists in the frontend, but the new PRD architecture delegates heavy observability to an Opt-In backend/Docker layer. This screen might need to be deprecated or refactored into a simple iframe/link out to Grafana to save frontend bundle size.
