# Abast-gp V7 - Secure Gateway High Availability (HA) Design

## 1. Topología del Clúster (Gateway Cluster)
El Secure Gateway, responsable de ofuscar PII y aplicar políticas *Zero Trust* antes de invocar al Cloud, es un componente crítico. Su falla desconectaría la IA del Ministerio.
**Arquitectura:**
- Se desplegará un clúster mínimo de **2 Nodos de Gateway** (Activo-Activo) por cada institución.
- Los nodos serán **100% Stateless** (Sin estado). No retendrán variables globales ni sesiones en memoria RAM. Cualquier nodo podrá enmascarar cualquier PDF de forma independiente.

## 2. Gateway Router (Balanceo y Failover)
El tráfico de salida de Abast-gp V5.5 no apuntará a un nodo individual, sino al **Gateway Router** (Ej. HAProxy o Nginx reverso).
**Lógica de Routing:**
- **Health Checks:** El Router enviará pings HTTP cada 5 segundos al endpoint `/health` de los nodos.
- **Failover Seguro (Retry Seguro):** Si el Nodo A sufre degradación (Timeout por falta de CPU) mientras enmascara un contrato masivo, el Router cortará la conexión, reportará el fallo y redirigirá la petición al Nodo B.
- **Timeout Estricto:** Máximo 15 segundos por petición. Si el enmascaramiento excede este tiempo, se clasifica como *Timeout Attack* y se aborta.

## 3. State Management (Persistencia de Auditoría)
Dado que los nodos son efímeros (Stateless), la trazabilidad debe ser persistente (Stateful).
- El modelo `GatewayAuditEvent` (Detecciones, Decisiones de Política) **no** se guarda en memoria. Cada nodo inyectará su registro de auditoría directamente a la Base de Datos PostgreSQL (V5.5) compartida *antes* de autorizar el ruteo final al Cloud. Si la inyección en DB falla, el envío se cancela (*Fail Closed*).

## 4. Escenarios de Falla (Simulation Results)
- **Degradación Parcial:** Si un nodo entra en bucle infinito (Ej. Regex Catastrófico), el Router detecta el *timeout* y lanza el tráfico al segundo nodo. La seguridad no se debilita.
- **Caída Total:** Si ambos nodos colapsan, el Router no hace *Bypass* hacia el Cloud. Arroja un error `503 Service Unavailable` a la aplicación principal. La Inteligencia Artificial se apaga localmente, preservando el principio **Fail Closed Segura**.

## 5. Operaciones de Despliegue (Operations)
- El futuro `docker-compose.yml` de la V7 declarará `replicas: 2` para el servicio `secure_gateway`.
- El balanceador se ejecutará como un microservicio ligero expuesto en la red Docker interna, encriptando todo tráfico hacia el exterior mediante mTLS.
