# Architecture Decision Record (ADR): V7 Secure Gateway

## 1. Contexto y Objetivos (Gateway ADR)
**Estado:** V7 Cloud Hybrid en etapa de diseño.
**Problema:** Enviar contexto documental hacia el Cloud (para inferencia LLM) expone inherentemente secretos de Estado si no se filtran rigurosamente en el origen.
**Objetivo:** Diseñar un Microservicio de Borde (Edge Proxy) denominado **Secure Gateway**, que se instalará físicamente en los servidores On-Premise del Ministerio. Será el *único* canal autorizado para contactar al Cloud de Abast-gp, actuando como un firewall semántico con tolerancia cero a fugas.

## 2. Clasificación de Datos (Data Classification)
- **Datos Prohibidos (Drop Inmediato):** 
  - Nombres propios y Razones Sociales.
  - RUC (Registro Único de Contribuyentes), DNI, Pasaportes.
  - Cuentas bancarias, Códigos CCI, Montos monetarios exactos.
  - El archivo PDF físico en formato binario.
- **Datos Permitidos (Forward):** 
  - Métricas de telemetría (Con opt-in V6.1).
  - Embeddings matemáticos (Vectores ciegos).
  - Texto anonimizado (Ej. "El proveedor [EMPRESA_1] suscribió el contrato el [FECHA]").

## 3. PII Masking Engine
El motor de ofuscación correrá localmente antes de cifrar el Payload.
- **Identificación:** Uso de heurísticas (Regex de RUCs Peruanos, DNI) combinadas con un modelo NLP local ligero de *Named Entity Recognition* (NER).
- **Masking:** Reemplazo determinista (`[RUC_ANON]`, `[PERSON_NAME]`).
- **Bloqueo (FAIL CLOSED):** Si el motor de masking falla (por timeout de CPU, error de librería, o ambigüedad extrema), el diseño dicta que el Gateway corte la conexión (`HTTP 500`) en lugar de enviar el texto crudo. Preferimos degradación del servicio Cloud a riesgo de fuga.

## 4. Policy Engine (GatewayPolicyEngine)
Motor de decisión en el proxy:
- **ALLOW:** Texto limpiado exitosamente. Se firma y se envía al Cloud.
- **BLOCK:** Patrones de alta peligrosidad detectados que el masker no pudo resolver limpiamente, o certificados SSL inválidos hacia el Cloud.
- **REVIEW:** Texto ambiguo. Se bloquea el envío al Cloud y se emite una alerta a Contraloría Interna / Administrador TI para calibrar el Masking Engine.

## 5. Auditoría Local (Gateway Audit)
Diseño conceptual del modelo `GatewayAuditEvent` (Guardado en PostgreSQL Local, NUNCA en la nube):
- `request_id`: UUID de la traza.
- `policy_version`: Versión del motor de reglas usada.
- `decision`: ALLOW / BLOCK / REVIEW.
- `destination_endpoint`: URL del servicio cognitivo destino.
- `timestamp`: UTC DateTime.

## 6. Threat Model (Modelado de Amenazas)
- **Fuga PII por Falso Negativo:** El motor NER no reconoce una Razón Social y la envía al Cloud. *Mitigación:* Heurísticas estrictas complementarias (Diccionario de empresas proveedoras del Estado) y modelo Fail Closed.
- **Prompt Injection:** Un atacante sube un contrato con un prompt malicioso para extraer datos del Cloud. *Mitigación:* El Cloud Cognitive Engine opera sin memoria de otros clientes (Stateless Inferences).
- **Proveedor Cloud:** Abast-gp AWS/GCP podría ser hackeado. *Mitigación:* Arquitectura Zero-Knowledge. El Cloud solo ve `[EMPRESA_1] vendió [PRODUCTO]`.
- **Logs Externos:** Riesgo de que la telemetría del Cloud guarde los prompts. *Mitigación:* Inferencia efímera garantizada por contrato (No data retention).

## 7. Security Test Plan
El pipeline de integración continuo para este componente (cuando se construya) debe incluir:
1. **DNI/RUC Detectado:** Inyectar un RUC peruano válido en el texto. Esperar que el Gateway devuelva `[RUC_ANON]` o bloquee.
2. **Texto Sensible Extremo:** Subir un PDF lleno de números de cuentas CCI. El sistema debe colapsar (Fail Closed) antes que rutear al Cloud.
3. **Bypass Attempt:** Intentos de conexión directa de la API V6.1 al Cloud evadiendo el Gateway. El Cloud debe rechazar tráfico que no posea la firma criptográfica (mTLS) exclusiva del Gateway.
