# Abast-gp V7 - Engineering Standards & Security Baseline

## 1. Repository Structure
La evolución arquitectónica hacia V7 rompe con el monolito heredado. El código fuente estará segregado lógicamente:
- **V5.5 Legacy:** Intocable, mantenido en el repositorio/rama original.
- **V6.1 Stable:** Operaciones de telemetría y gobernanza actuales.
- **V7 Development:** Nueva rama/estructura de carpetas (`v7_dev/`) exclusiva para la IA Híbrida. No interactuará con el código legacy de forma síncrona.

## 2. Security Baseline (Fundamentos DevSecOps)
- **Secret Management:** Queda prohibido *hardcodear* contraseñas, URLs de bases de datos o llaves de encriptación. Todo secreto debe inyectarse vía Variables de Entorno (o un Vault como HashiCorp Vault).
- **Certificates (mTLS):** En desarrollo, usaremos certificados autofirmados. En producción, la PKI del Estado emitirá los certificados de autenticación mutua para el Gateway.
- **Dependency Scanning:** El pipeline de CI/CD ejecutará escaneos de librerías (`safety`, `pip-audit`) en cada commit para evitar *Supply Chain Attacks*.
- **Image Security:** Toda imagen Docker del Gateway y de la base de datos pasará por *Trivy* para buscar vulnerabilidades en el OS base (Cero CVEs Críticos/Altos permitidos para el release).

## 3. Observability & Metrics (Prometheus)
El clúster de Gateway emitirá telemetría de aplicación en el formato `/metrics` para *Prometheus*:
- `v7_gateway_latency_ms`: Histograma de tiempo de respuesta del ruteo.
- `v7_gateway_policy_decisions_total{decision="BLOCK|ALLOW"}`: Contador de políticas aplicadas por el *Fail Closed*.
- `v7_pgvector_search_latency_ms`: Monitoreo del recall y velocidad de HNSW.
- `v7_gateway_errors_total`: Contador de *timeouts* y excepciones internas.

## 4. Desarrollo de Código
- **Lenguaje:** Python 3.11+.
- **Framework:** FastAPI (Por su rendimiento asíncrono para el Gateway).
- **Clean Architecture:** Separación estricta entre *Entities*, *Use Cases* (PII Masking, Routing) y *Controllers*.
