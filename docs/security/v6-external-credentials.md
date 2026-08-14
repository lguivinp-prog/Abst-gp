# External Provider Credentials Management

## 1. Política de Cero Secretos Estáticos
Bajo ninguna circunstancia se pueden quemar llaves maestras, API keys o tokens de acceso en el código fuente.

## 2. Inyección de Entorno
Los adaptadores híbridos (SUNATProvider, RNPProvider, FUPProvider) están diseñados para consumir variables de entorno.
- `SUNAT_API_KEY`
- `RNP_API_KEY`
- `FUP_API_KEY`

Estas variables provendrán del gestor de secretos de la infraestructura (ej. AWS Secrets Manager, Hashicorp Vault, o un `.env` fuertemente encriptado en on-premises).

## 3. Comportamiento Graceful Degradation
Si el sistema detecta que la API key no está inyectada, o si la API gubernamental falla, el adaptador **NUNCA** lanza un error 500 que bloquee la operación.
En su lugar, degrada a:
1. `MANUAL_REQUIRED` (exigiendo al operador subir el PDF de la consulta respectiva).
2. `WARNING` (delegando el riesgo al Supervisor).
