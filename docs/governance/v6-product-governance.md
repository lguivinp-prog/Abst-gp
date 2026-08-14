# Abast-gp V6 Product Governance

## 1. Definición de Políticas de Release
Abast-gp es un producto _Enterprise B2G_ (Business to Government), por ende la estabilidad prima sobre la innovación rápida.
- **Versiones Menores (Patches / V6.0.x)**: Reservadas estrictamente para bugfixes, optimizaciones de latencia (RAG Chunking), y detectores operacionales que no alteren la arquitectura de la base de datos ni los roles RBAC. Pueden desplegarse sin interrumpir el Legacy V5.5.
- **Versiones Mayores (Minor/Major / V6.1, V7.0)**: Reservadas para nuevas integraciones institucionales (SaaS, Cloud Native, Kubernetes) o para migrar el modelo determinista core a nuevas infraestructuras lógicas. Requieren certificación DR cruzada obligatoria.

## 2. Architecture Decision Records (ADRs)
Toda alteración al diseño del motor RAG, la base de datos de Auditoría (`AuditLog`) o las pasarelas externas de Validación (`ExternalValidationLayer`) debe quedar sustentada mediante un ADR formal validado por el CTO.

## 3. Política de Seguridad (Cero Regresión)
1. Queda estrictamente prohibido desactivar el `ContractAccuracyGate` en cualquier versión.
2. Queda estrictamente prohibido sustituir los Evaluadores Heurísticos deterministas (`ExperienceEvaluationEngine`) por Modelos de Lenguaje probabilísticos (LLMs). La IA asiste (RAG Retrieval), el Humano (o Algoritmo) decide.
3. El `AuditLog` debe mantenerse inmutable.

## 4. Roadmap V6.0.1+
El gobierno técnico priorizará optimizaciones locales antes de considerar infraestructuras distribuidas (Kubernetes) o pasarelas SaaS (OpenAI/Anthropic Cloud), debido a regulaciones de retención de datos soberanos. 

**Hoja de Ruta Inmediata:**
1. _Document Quality Assistant_: Worker de pre-procesamiento para Deskewing y detección de DPI insuficiente antes de ingerir a la BD Vectorial.
2. _RAG Optimization_: Ajustar `chunk_size` y `overlap` empíricamente.
