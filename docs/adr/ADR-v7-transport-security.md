# ADR-v7-transport-security

## Contexto
El entorno V7 requiere una política explícita de seguridad de transporte para mitigar riesgos de interceptación en tránsito y definir los alcances de la prueba de Staging. El delta entre `EDGE_MTLS`, `SERVICE_TO_SERVICE_MTLS` o `BOTH` bloqueaba la decisión financiera.

## Decisión
Se determina la política **EDGE_TLS_ONLY** para Staging y Producción, con la siguiente especificación:

- **EDGE (Client ↔ ALB):** `REQUIRED`. Terminado en el ALB de AWS mediante certificado gestionado por ACM.
- **ALB ↔ Application (Gateway):** `NOT_REQUIRED`. El tráfico transita en crudo dentro de la VPC privada/Private Subnets asegurado por Security Groups.
- **Service ↔ Service (Gateway ↔ Redis/Celery):** `NOT_REQUIRED`. Se usarán conexiones de red privadas confiables (VPC local).

## Justificación
La introducción de un sidecar proxy (e.g. Istio) para certificar identidades intra-cluster (`SERVICE_TO_SERVICE_MTLS`) añadiría una sobrecarga computacional de red innecesaria (latencia y CPU para el proxy en cada nodo), y la seguridad de la red VPC privada + RLS PostgreSQL ya cubre los vectores de ataque previstos (Defense in Depth).

## Estado
**CONFIRMED_PRODUCTION_REQUIREMENT** (Para Edge TLS).
**NOT_REQUIRED** (Para intrapod mTLS).

El estado de Staging `UNKNOWN` para mTLS ha sido resuelto y clasificado como mitigado (no bloqueante).
