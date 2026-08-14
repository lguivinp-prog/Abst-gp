# Product Requirements Document (PRD) V1.0 - Abst-gp V6 Local Enterprise Assistant

## 1. Product Vision
Abst-gp is an intelligent document evaluation assistant designed to accelerate and error-proof public procurement (contrataciones) processes. It acts as an augmenting tool that extracts, validates, and compares technical requirements (EETT) and Terms of Reference (TDR) against supplier quotations and annexes.

**Core Philosophy:** Abst-gp does not replace human judgment, PLADICOP, or official state systems. It cannot automatically award contracts. Its sole purpose is to reduce operational friction and administrative errors in the evaluation matrix.

## 2. Target Environment
- **Initial Scope:** Local network installation (V6 Local Enterprise Assistant).
- **Host System:** Windows 11 Pro.
- **Scale:** 5-6 concurrent users via web browser.
- **Tenancy:** Single automatic local tenant, preventing multi-tenant complexity exposure to the user.
- **Future Vision:** Multi-tenant SaaS platform with independent configuration per entity.

## 3. Mandatory User Flow
1. **Case Creation:** Define title, good/service type, area, entity, and responsible party.
2. **Base Document Upload:** Upload the TDR or EETT.
3. **Extraction & Matrix:** Automatically extract requirements and present them in an editable, user-validated matrix.
4. **Supplier Document Upload:** Upload single/multiple PDFs (Annex 3, Annex 4, brochures, certificates).
5. **Document Classification:** The system classifies pages/sections. The user can manually override.
6. **Pre-Validation Gate:** Check SUNAT, RNP, FUP, CIIU, and RUC state. If failed, the evaluation is blocked unless the Supervisor forcibly reopens it with an audited justification.
7. **Requirement Comparison:** Compare Annex 4 and technical documents against the validated matrix. Detect: CUMPLE, NO CUMPLE, OBSERVADO, MEJORA, CONFLICTO, DATO FALTANTE.
8. **Experience Evaluation:** Compare Annex 3 (contracts, orders, invoices) against minimum experience requirements.
9. **Decision & Justification:** View comparative dashboard. Select a supplier. If the choice contradicts the system's best recommendation, a mandatory justification is required.
10. **Output Generation:** Generate draft evaluation report and contractual conditions (Web preview / Copy to clipboard).
11. **Approval:** Operator submits; Supervisor reviews and approves. Output export is disabled until approved.

## 4. Key Decisions & Restrictions
- **Allowed Improvements (Mejoras):** Shorter delivery times, extended warranties, superior technical specs, and higher experience. *Supplier address cannot be treated as a contractual improvement.*
- **Supplier Selection:** Only ONE supplier can be selected per case.
- **Pricing:** Price is extracted and displayed, but strictly DOES NOT constitute technical added value (no automatic weighting).
- **Document Q&A:** Users can chat/ask questions about the case. Responses must strictly cite the uploaded documents and validated matrix. No hallucinated external knowledge is allowed.
- **Normative Engine:** Procurement rules must be versionable, configurable by entity, and bound by effective dates, not hardcoded.
- **Terminology:** Strictly Peruvian public procurement lexicon (TDR, EETT, RNP, FUP, RUC, CIIU, Orden de Compra/Servicio, PLADICOP).

## 5. User Profiles
- **Supervisor (Admin):** Full control. Can create cases, review all cases, assign cases, approve outputs, manage users/rules, view audit logs, and trigger data deletion/storage cleanup.
- **Operator:** Can create cases, view assigned/own cases, upload documents, validate matrices, evaluate suppliers, generate drafts, and submit for approval.
- **Readonly:** Can only view assigned cases and authorized final results.

## 6. Functional Acceptance Cases
- **CASE A (Goods):** Extract items, quantities, units, specs, experience, delivery, warranty, and payment terms from an EETT. Compare against one or more Annex 4s.
- **CASE B (Services):** Extract service metrics, deliverables, deadlines, and locations from a TDR. Detect fulfillment, omissions, and improvements.
- **CASE C (Consolidated PDF):** Given a single large PDF containing SUNAT, RNP, Annex 3, and Annex 4, the system must segment and classify it correctly.
- **CASE D (Multiple Suppliers):** The system must smoothly handle comparison matrices for up to 10 suppliers simultaneously.
