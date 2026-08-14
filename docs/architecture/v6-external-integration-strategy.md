# V6 External Integration Strategy

## 1. Overview
This document outlines the architectural strategy for transitioning the `ValidationProviderInterface` from deterministic mocks (used during Sprints 1-5) into real-world production data sources (SUNAT, RNP, FUP, CIIU, etc.).

## 2. Priority Hierarchy
As defined by the architectural guardrails, Abast-gp V6 enforces the following priority list for sourcing external intelligence:

1. **API Oficial Autorizada (Highest Priority)** 
   - Web services directly published by the governing entity (e.g., SUNAT REST API for RUC queries, OSCE APIs for RNP).
2. **Convenio PIDE / Interoperabilidad** 
   - Utilizing the National Interoperability Platform (PIDE) in Peru if a direct API is unavailable.
3. **Carga Manual Validada (Fallback)** 
   - When no automated mechanism exists, the system gracefully falls back to requesting the user to upload the PDF certificate (e.g., "Constancia RNP") which will then be parsed via our OCR Engine.
   
> [!CAUTION]
> **Scraping NO autorizado**. Web scraping is strictly prohibited as a primary dependency due to legal fragility and UI volatility of government portals.

## 3. Architecture Transition
- **Providers Pattern**: The existing `ValidationProviderInterface` remains unchanged.
- **Queueing (RQ Worker)**: Calls to external APIs will be enqueued in Redis via RQ. The worker will handle retries, rate limiting, and exponential backoff to prevent bans from government IPs.
- **Normalization Engine**: Raw strings fetched from APIs will pass through the `NormalizationEngine` to convert textual quantities/currencies into numeric constants before reaching the `SupplierProfile` or `ExperienceEvaluationEngine`.
