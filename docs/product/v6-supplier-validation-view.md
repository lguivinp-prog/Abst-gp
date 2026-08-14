# V6 Supplier Validation View - Functional Design

## 1. Overview
The Supplier Validation View allows the contracting authority to inspect a single consolidated profile of a supplier (SupplierProfile) infused with external intelligence (SUNAT, RNP, FUP, CIIU) acquired asynchronously.

## 2. Layout (Dashboard Pattern)
- **Header**: Supplier Name, RUC, Global Consolidated Status Badge (PASSED, WARNING, BLOCKED).
- **Hero Section**: 
  - Left: Identifying information (Address, Legal Rep, DNI, Contact).
  - Right: Validation Triggers & Progress. A "Request Validations" button which triggers `POST /api/v6/suppliers/{id}/validation-requests`.
- **Validation Cards Grid**: 
  - **SUNAT Card**: Shows Taxpayer Status and Condition.
  - **RNP Card**: Shows National Registry Status.
  - **FUP Card**: Single Registry of Providers.
  - **CIIU Card**: Shows semantic correlation between registered economic activities and the case requirements (HIGH, MEDIUM, LOW, UNKNOWN).

## 3. Data Representation
- **Integration States**: Each card reflects the async status of `ValidationRequest` (PENDING, RUNNING, PASSED, WARNING, BLOCKED, ERROR).
- **Evidence Trail**: Each card displays a "View Evidence" link that expands to show `response_payload` data, timestamp, and source to support audits.

## 4. Interaction Flows
- **Trigger Validations**: 
  1. User clicks "Validate".
  2. UI calls the `POST` endpoint and receives a `PENDING` request.
  3. UI polls `GET /api/v6/validation-requests/{id}` until status is terminal.
- **Manual Overrides**: 
  - The system will *never* auto-adjudicate or disqualify. If a supplier is marked `BLOCKED` by SUNAT, the user must still click a final "Disqualify Supplier" or "Approve Exception" button, triggering an AuditLog reason.
