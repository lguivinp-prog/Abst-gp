# Architecture Decision Record (ADR): Abast-gp V7 Cloud Hybrid

## 1. Contexto y Objetivos
**Estado Actual:** Abast-gp V6.1 opera 100% On-Premise. Aunque esto maximiza la seguridad de los secretos de Estado, impone límites técnicos (Falta de escalabilidad vectorial, obsolescencia del modelo LLM local, altísimos costos de hardware para el Estado).
**Objetivo V7:** Diseñar una transición segura hacia un modelo Híbrido, donde los datos sensibles sigan anclados físicamente al ministerio, pero la inferencia semántica y el procesamiento algorítmico pesado se deleguen al Cloud de Abast-gp.

## 2. Modelo de Arquitectura Híbrida (Topología)
- **CAPA LOCAL (On-Premise V5.5/V6):** Custodia de los archivos PDF reales, la Base de Datos PostgreSQL con los expedientes, RUCs de proveedores, y montos de licitación. Custodia absoluta de la llave de descifrado maestro.
- **CAPA GATEWAY (Abast-gp Proxy):** Un nuevo microservicio instalado localmente. Su única función es ofuscar (Anonimizar) fragmentos de texto mediante heurísticas de NLP locales, cifrar los vectores generados, y actuar como el único puente autorizado hacia internet.
- **CAPA CLOUD (Cognitive Engine):** Clústeres Kubernetes alojados en AWS/GCP (SOC 2). Solo reciben *Embeddings* matemáticos y peticiones semánticas anonimizadas. No poseen persistencia de bases de datos relacionales; son cerebros sin memoria.

## 3. Data Privacy Model (Fronteras de Soberanía)
- **Datos que NUNCA salen del Ministerio:** RUC, DNI, Razones Sociales, Correos Electrónicos, Montos Monetarios, y el PDF original del contrato.
- **Datos que PUEDEN salir (al Cloud):** Vectores matemáticos (*Embeddings*), texto semántico fragmentado tras pasar por un algoritmo de enmascaramiento local, y telemetría de rendimiento (aprobada en V6.1).

## 4. Security Foundation
- **Zero-Knowledge Architecture:** El Cloud de Abast-gp será ciego. Si el servidor Cloud es vulnerado, el atacante solo robará tensores numéricos (matrices de 1536 dimensiones) sin la clave de reconstrucción semántica, la cual nunca salió del hardware del Ministerio.
- **Key Management:** Bring Your Own Key (BYOK). El Estado Peruano retendrá la llave KMS que genera los embeddings.
- **Identity & Audit:** Toda petición de inferencia originada por el Ministerio hacia el Cloud irá firmada por un JWT institucional, quedando registrada en el `AuditLog` On-Premise.

## 5. RAG Evolution (Preparación V7)
La memoria In-Memory (Faiss) usada en V6 no escalará si enviamos millones de vectores al Cloud. 
- **PostgreSQL Vector:** `pgvector` será el nuevo motor predeterminado. El Cloud operará motores distribuidos de búsqueda vectorial, pero el ministerio retendrá una réplica transaccional local.
- **Distributed Retrieval:** El Gateway local actuará como orquestador, uniendo respuestas de base de datos rígidas (SQL) con respuestas semánticas del Cloud (RAG).

## 6. Commercial Model (V7)
- **Licencia Local (V5.5/V6 Core):** Perpetua o Costo Fijo por despliegue. Garantiza la funcionalidad básica transaccional.
- **Servicios Cognitivos (V7 Cloud):** Suscripción Anual (Opex) basada en volumen de procesamiento de texto/contratos.
- **Soporte L3:** SLA dictado por telemetría (Soberana, opt-in).
