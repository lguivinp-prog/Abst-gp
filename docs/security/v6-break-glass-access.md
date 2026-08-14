# Abast-gp V6 - Break Glass Access (Temporary Elevated Access)

## 1. Definición y Propósito
El `SYSTEM_ADMIN` no tiene acceso automático multi-tenant a expedientes para prevenir fugas de secretos de Estado. Sin embargo, en situaciones de soporte crítico (Nivel 3), se requiere acceder temporalmente al entorno de un Tenant para depurar errores de algoritmo (ej. RAG Crashing). 

## 2. Flujo de Elevación (Break Glass)
El diseño para la V6.1 requerirá el siguiente flujo:
1. **Solicitud:** El `SYSTEM_ADMIN` genera un token de *Break Glass* indicando:
   - Tenant ID objetivo.
   - Motivo (Bug ticket ID).
   - Duración (Máximo 2 horas).
2. **Autorización Local:** El `ADMIN_IT_INSTITUCIONAL` (Dueño del tenant) debe aprobar la solicitud en su Dashboard. 
3. **Auditoría Inmediata:** La aprobación graba `BREAK_GLASS_GRANTED` en el `AuditLog`.
4. **Revocación Automática:** Al expirar el tiempo, el token JWT del System Admin pierde el _Claim_ de lectura y cualquier intento retorna `403 Forbidden`.

## 3. Restricciones Permanentes (Even on Break Glass)
- Incluso con acceso elevado temporal, el `SYSTEM_ADMIN` **NUNCA** puede presionar botones transaccionales (`VALIDAR`, `SUPERVISOR_EXCEPTION_SELECT`).
- Sus permisos temporales son estrictamente _Read-Only_ sobre los expedientes y logs de error, previniendo alteraciones de adjudicaciones públicas.
