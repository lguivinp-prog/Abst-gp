# V6 AI Assistant View - Functional Design

## 1. Overview
The AI Assistant view provides a conversational interface overlay on the Case File dashboard. It allows operators and supervisors to query the validated case context (Requirements, Offers, Evaluations) to accelerate analysis.

## 2. Layout (Side Panel Pattern)
- **Trigger**: Floating action button (FAB) or Side Panel toggle "Asistente IA".
- **Chat History**: Scrollable area displaying `question` (User) and `response` (AI).
- **Warning Banner (Persistent)**: 
  > ⚠️ "La IA es un asistente analítico y requiere validación humana. No puede tomar decisiones de adjudicación ni reemplazar el flujo legal."

## 3. Response Structure
Every AI response bubble MUST contain:
1. **Answer Text**: The formatted markdown response.
2. **Sources Tag**: A visual chip listing the sources used (e.g., "Sources: Case Evaluations").
3. **Evidence References**: If applicable, links to specific fragments or documents.

## 4. Interaction Constraints
- The user can ask free-text questions.
- Under the hood, the system injects the `CaseContextBuilder` snapshot into the prompt.
- If the user asks something outside the scope of the current CaseFile, the AI will refuse to answer or state it lacks context, as it cannot query arbitrary DB records.
