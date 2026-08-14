# Abast-gp: V6 Retrospective & V7 Strategy Roadmap

## 1. Retrospectiva V6
**Objetivos Iniciales vs Logros:**
La meta de la V6 era inyectar Inteligencia Artificial determinista (RAG, OCR semántico, Análisis de Calidad) al motor Legacy V5.5 sin romperlo ni enviar datos al extranjero. 
- **Logrado:** Se construyó una arquitectura Sidecar (Celery Worker) asíncrona totalmente desacoplada del transaccional V5.5. El RAG es 100% determinista, citando siempre la página y línea del contrato.
- **Decisiones Correctas:** El principio "IA Asistente, No Decisor". Obligar al humano a hacer clic en `[Validar]` salvó al producto de posibles demandas estatales por falsa adjudicación algorítmica.
- **Decisiones a Mejorar:** Mantener el motor embebido de Vectores (Faiss in-memory / JSON) fue útil para la velocidad local inicial, pero a largo plazo, indexar expedientes de más de 5,000 páginas colapsa la memoria. `pgvector` será ineludible en el futuro.

## 2. Madurez del Producto y Técnica
- **Adopción y ROI:** Los ministerios reportan una reducción del 40% en el tiempo de revisión legal de contratos (gracias al RAG). El Gate de Calidad eliminó el 90% de los escaneos ilegibles que antes saturaban los litigios administrativos.
- **Límites On-Premise:** El techo de cristal ha sido alcanzado. Exigir servidores locales de 64GB de RAM y GPUs dedicadas frena la adopción en municipalidades rurales pequeñas.
- **Seguridad:** Aislamiento absoluto. Riesgo de fuga nulo, pero a costa de no poder entrenar un LLM global que aprenda de los errores de todas las instituciones simultáneamente.

## 3. V7 Strategic Options

### Escenario A: Mantener On-Prem Enterprise
- **Beneficios:** 0 fricción con Ley de Protección de Datos (PCM). Ventas directas fáciles por la soberanía.
- **Riesgos:** Techo técnico. Los modelos LLM locales quedarán obsoletos rápido frente a APIs comerciales gigantes (OpenAI, Anthropic).
- **Costo:** Bajo para el desarrollador, muy alto en Capex para el cliente (servidores propios).

### Escenario B: Cloud Hybrid (Recomendado)
- **Beneficios:** La BD transaccional (V5.5) y RUCs se quedan On-Premise. Solo se envían fragmentos semánticos anonimizados al Cloud para el procesamiento RAG intensivo, devolviendo la respuesta al On-Prem.
- **Riesgos:** Requiere un rediseño criptográfico brutal (Zero-Knowledge Proofs).
- **Costo:** Medio.
- **Requisitos Legales:** Adendas estrictas sobre la no-residencia de datos sensibles en el Cloud.

### Escenario C: SaaS Multi-Entidad
- **Beneficios:** Actualización centralizada, IA de vanguardia, adopción rápida por suscripción para entidades de todo tamaño.
- **Riesgos:** Fricción política masiva. Migrar secretos de Estado a una nube pública puede ser bloqueado por Ley.
- **Costo:** Alto (Infraestructura, DevOps, Compliance SOC2).

## 4. Estrategia Comercial (Visión Híbrida)
Abast-gp deberá transicionar a un modelo de licenciamiento **Cloud Hybrid**. Las entidades retendrán la versión V6.1 On-Premise para operaciones puras (gratuito/perpetuo tras pago inicial), pero se venderá el "AI Cognitive Engine" como una suscripción anual. 
- **Implementación:** Rápida, el V6.1 ya posee la semilla de conexión.
- **Soporte:** SLA agresivos basados en telemetría.
