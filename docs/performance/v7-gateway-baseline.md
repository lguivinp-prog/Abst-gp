# V7 Secure Gateway: Performance Baseline & Streaming Architecture

## 1. Arquitectura de Streaming (Chunking)
En la iteración previa (V1), el Gateway cargaba el documento íntegro en memoria, aplicando heurísticas sobre un único *String* gigante. Esto generaba un costo algorítmico cuadrático ($O(N^2)$), escalando a casi 9 segundos para 1000 páginas.
**Solución V2:** El Gateway ahora opera como un flujo (*Stream*). Corta el texto en *chunks* (Ej. 2000 caracteres) y procesa cada fragmento de forma aislada a través del pipeline `Detection -> Conflict -> Masking -> Policy`.

## 2. Ventaja del "Fail Closed" Temprano
El rediseño permite una ganancia de rendimiento monumental vinculada a la seguridad: **Cortocircuito Lógico**. 
Si el Policy Engine detecta un riesgo severo (Ej. `HIGH_RISK_BLOCK`) en la primera página de un contrato de 1000 páginas, el Gateway **aborta el procesamiento del resto del documento instantáneamente**.

### Benchmark de Latencia (Con Inyección PII en Página 1)
- **100 Páginas:** 0.91 ms (vs 24 ms en V1)
- **500 Páginas:** 0.37 ms (vs 1.9 Segundos en V1)
- **1000 Páginas:** 0.37 ms (vs 8.7 Segundos en V1)
*Nota:* El tiempo en 1000 páginas es idéntico a 500 porque el motor detiene la ejecución en el primer *chunk* comprometido.

## 3. Policy Intelligence & Falsos Positivos
El Policy Engine se actualizó de un binario (`ALLOW`/`BLOCK`) a un semáforo de riesgo:
- `HIGH_RISK_BLOCK`: Riesgo severo (DNI/RUC expuesto o números residuales > 8 dígitos no clasificados). Cierre de conexión inmediato.
- `MEDIUM_RISK_QUARANTINE`: Detección anómala.
- `LOW_RISK_ALLOW`: Tráfico limpio.

**Control de Falsos Positivos:**
Las heurísticas fueron afinadas. Expresiones comunes peruanas como teléfonos celulares (`9XXXXXXXX`) o correlativos de expedientes del Estado (`EXP-2026-XXXXXXXX`) ya no detonan el *Fail Closed*, previniendo la parálisis operativa del Gateway.

## 4. Auditoría Versionada
El modelo de auditoría (`GatewayAuditEvent`) ahora retiene de forma forense las versiones de los motores exactos que tomaron la decisión:
- `detector_version` (Ej. v1.1)
- `masking_version` (Ej. v1.1)
- `policy_version` (Ej. v2.0)
Esto permite trazar retrospectivamente si un documento se fugó debido a una versión anticuada de las Expresiones Regulares.
