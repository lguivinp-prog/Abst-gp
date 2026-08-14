# V6 RAG Assistant View - Functional Design

## 1. Overview
The RAG Assistant View evolves the base AI conversational panel to provide extreme transparency into *why* the AI answered a certain way, exposing the exact document chunks retrieved by the system.

## 2. Layout Enhancements
- **Answer Block**: The main text response from the AI.
- **Retrieval Metrics (Meta)**: A small badge indicating "Chunks recuperados: X" and "Estrategia: deterministic-mock-v1".
- **Evidence Drawer (Accordion)**: 
  - A clickable element under the answer labeled "Ver Evidencia Original".
  - When expanded, it lists the exact text fragments (`retrieved_chunks`) the AI consumed.
  - Each fragment shows its origin (e.g., "Anexo 3 - Pagina 2").

## 3. Strict Traceability
By enforcing this view, we ensure the operator never trusts the AI blindly. The operator can compare the AI's summary directly against the RAW text chunks displayed in the Evidence Drawer without needing to open the original heavy PDF.
