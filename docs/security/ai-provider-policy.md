# AI Provider Security Policy

## 1. Proveedores Autorizados
Para la integración de modelos fundacionales (LLMs), solo se permiten proveedores que ofrezcan:
- Contratos Enterprise con "Zero Data Retention" (Cero retención de datos para entrenamiento).
- Despliegues en nube privada virtual (VPC) o regiones autorizadas.
- Proveedores planificados: OpenAI (Enterprise API), Anthropic (Bedrock/Console Enterprise), o LLM Local Housed (Llama-3 en servidor On-Prem).

## 2. Datos Permitidos (Context Gating)
- **Solo Contexto Validado**: La IA jamás accederá a tablas base de datos en crudo ni hará queries SQL autónomos. Su visión del mundo está restringida al `CaseContextBuilder`, el cual expone únicamente entidades ya procesadas por el motor determinista.
- **Datos Sensibles**: Datos como DNIs puros o tarjetas de crédito (si los hubiera) deben ser enmascarados antes del hashing.

## 3. Trazabilidad y Cifrado
- Toda interacción se almacena en `AIInteractionLog`.
- El contexto enviado y la respuesta recibida se hashean (SHA-256) para garantizar que, si un usuario afirma "La IA me dijo que lo aprobara", se pueda auditar forensemente si el sistema realmente generó esa respuesta.

## 4. Retención de Logs
- Los logs de interacción de IA se mantendrán por el mismo periodo legal que el expediente electrónico del caso, sirviendo como anexo de auditoría no vinculante.

## 5. Límites (Rate Limiting)
- Se impondrán cuotas de tokens por Tenant/User para prevenir ataques de denegación de cartera (Wallet DoS) sobre las APIs de pago.
