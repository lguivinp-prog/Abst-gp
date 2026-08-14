# Abast-gp V7 - Estudio de Seguridad de Embeddings y Vectorización

## 1. Contexto de la Vectorización Híbrida
En la arquitectura V7 Cloud Hybrid, el **Secure Gateway Local** (Instalado en el Ministerio) limpiará los textos de PII (RUCs, Nombres). Una vez limpio, el Gateway transformará el texto en **Embeddings Matemáticos** (Matrices vectoriales densas, Ej. tamaño 1536) usando un modelo abierto de NLP local. 
Estos vectores, no el texto crudo, serán transmitidos por la red hacia el Cognitive Cloud de Abast-gp para inferencia RAG.

## 2. Riesgos Teóricos: "Embedding Inversion Attacks"
**Riesgo Fundamental:** Existe una falsa sensación de seguridad en que "los vectores no son reversibles". Investigaciones recientes demuestran que, usando ataques de *Inversión de Embeddings* entrenados en pares conocidos (Vector -> Texto), un atacante en la nube podría reconstruir palabras sueltas o contexto parcial a partir de los vectores, violando el aislamiento si los vectores contienen PII.
**Mitigación en Abast-gp:** El Gateway limpia el PII *ANTES* de generar el Embedding. Incluso si el Cloud es vulnerado y el atacante invierte el vector exitosamente, el texto reconstruido será: `"El contrato de [RUC_MASKED] con [PERSON_NAME]"`. El secreto de Estado permanece matemáticamente imposible de recuperar.

## 3. Cifrado en Tránsito (Secure Transit)
Además de la anonimización, los vectores matemáticos viajarán encapsulados bajo túneles TLS 1.3 (Mutual TLS - mTLS) hacia la nube.
- **Identidad del Gateway:** El Cloud solo aceptará conexiones vectoriales firmadas con certificados emitidos por Abast-gp a nombre exclusivo de la oficina TI del Ministerio remitente. (Arquitectura Zero Trust).

## 4. Retención de Llaves Criptográficas y Aislamiento Cloud
La base de datos vectorial distribuida en la nube (`pgvector` Cloud) almacenará los Embeddings con el identificador del Tenant. 
- **Keys Management:** Si se decidiera cifrar los vectores *en reposo* antes de enviarlos (Client-Side Encryption), se perdería la capacidad de hacer búsqueda de similitud de coseno en la nube (la nube no puede comparar números cifrados ciegamente).
- **Decisión Arquitectónica:** Por ende, los Embeddings residirán en texto plano matemático en el Cloud, pero gracias a la sanitización previa (Fase 2) y al aislamiento de red, el Cloud actúa como un motor de búsqueda rápido que no entiende a quién le pertenece el caso real ni de qué proveedor se trata.

## 5. Actualización al Threat Model (Gateway)
Nuevas amenazas y salvaguardas:
- **Excepciones de Política (Riesgo de Puerta Trasera):** Un usuario malicioso añade una Excepción al Policy Engine diciendo "Ignorar DNI". 
  - *Mitigación:* Se implementó `GatewayPolicyException`, requiriendo creador, aprobador (CISO) y expiración de regla, firmemente auditado en la BD.
- **Inferencia LLM Rogue:** El proveedor LLM externo retiene el prompt semántico anonimizado.
  - *Mitigación:* Acuerdos de "Zero Data Retention" comerciales (API Enterprise, no de usuario final), y la tranquilidad de que el prompt carece de sujetos identificables.
