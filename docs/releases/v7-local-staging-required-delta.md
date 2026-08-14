# Local vs Staging Required Delta

## Objetivo
Identificar exactamente qué características operativas NO pudieron ser validadas durante la fase de *Local Integration* y justifican el despliegue de un entorno *Staging*.

## Gaps Identificados

### 1. Ingress Real / Reverse Proxy
- **Requirement:** El tráfico debe atravesar un Ingress/ALB real.
- **Why Local is Insufficient:** Local no expone latencias de red externa ni configuraciones de keep-alive y timeouts de Ingress.
- **Risk:** Timeout prematuro de requests, websockets caídos, headers filtrados.
- **Staging Test Required:** Validación end-to-end de payloads grandes (imágenes/vectores).

### 2. Connection Proxy (PgBouncer/RDS Proxy)
- **Requirement:** Testing de multiplexación transaccional para evitar connection starvation.
- **Why Local is Insufficient:** Local usó una única instancia directa (pool interno de la app).
- **Risk:** Leakage de Tenant Context (SET LOCAL) si el proxy mezcla sesiones; Exhaustion de base de datos.
- **Staging Test Required:** `NO TENANT-CONTEXT LEAKAGE OBSERVED IN EXECUTED STAGING TEST MATRIX`.

### 3. Distributed Architecture (Multi-node Celery/Redis)
- **Requirement:** Validación de concurrencia real y latencia de broker.
- **Why Local is Insufficient:** Local corre todo en la misma red Docker de baja latencia con un solo nodo.
- **Risk:** Race conditions en escritura vectorial (dual-write).
- **Staging Test Required:** Stress test multi-worker para encolamiento de vectores.

### 4. TLS Termination / mTLS
- **Requirement:** Validación de propagación de seguridad de transporte.
- **Why Local is Insufficient:** Local Integration operó en HTTP crudo.
- **Risk:** Fuga de JWTs en tránsito, Handshakes fallidos.
- **Staging Test Required:** Request HTTPs y verificación de claims mTLS.
