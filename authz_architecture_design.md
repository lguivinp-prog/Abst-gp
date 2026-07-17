# DISEÑO DE ARQUITECTURA DE AUTH/AUTHZ (ESPECIFICACIÓN FINAL CORREGIDA)

Este documento contiene la especificación definitiva y lista para implementarse del sistema de Autenticación y Autorización, incorporando las decisiones arquitectónicas y de producto confirmadas finales.

---

## 1. Diseño de Sesión Definitivo

Se implementarán **Sesiones Opacas respaldadas en Redis**. 

**Diseño del Identificador de Sesión**:
- El token base se generará con al menos 32 bytes aleatorios: `secrets.token_urlsafe(32)`.
- **Regla Crítica**: No almacenar el token completo en logs, AuditLog o base de datos/Redis en texto plano (como metadata).

**Estructura en Redis**:
- `session:{hash_del_token}`: Almacena los datos de la sesión.
- `user_sessions:{user_id}`: Un índice (set/lista) de los hashes de tokens activos para permitir revocación atómica global de todas las sesiones de un usuario.

**Registro de Sesión (Atributos)**:
- `user_id`
- `created_at`
- `last_seen_at` (para control de inactividad)
- `absolute_expires_at` (tiempo máximo absoluto)
- `password_version` o `password_changed_at` (para invalidar sesiones ante cambios de contraseña)
- `csrf_secret`
- Información mínima de seguridad.

**Políticas de Tiempo de Vida (TTL)**:
- **Inactividad**: TTL configurable que se renueva de forma controlada.
- **Absoluto**: Tiempo máximo absoluto configurable tras el cual la sesión expira inevitablemente.
- **Revocación**: Cierre de sesión, desactivación de usuario, restablecimiento/cambio de contraseña o ejecución del mecanismo break-glass eliminarán la(s) clave(s) de Redis inmediatamente.
- **Rotación**: Tras el login y el cambio de contraseña, se emitirá una nueva sesión.

**Definición de Cookie de Sesión**:
- **Producción (HTTPS)**:
  - Nombre: `__Host-abst-session`
  - `HttpOnly`: true
  - `Secure`: true
  - `SameSite`: Lax (como configuración inicial)
  - `Path`: `/`
  - `Domain`: (No configurado, dictado por el prefijo `__Host-`)
  - `Max-Age`: derivado de la duración de la sesión
- **Desarrollo (HTTP)**:
  - Nombre: Configurable y distinto (ej. `abst-dev-session`).
  - `Secure`: false (únicamente permitido cuando `ENVIRONMENT != production`).
- *Nota CORS*: Si frontend y API se despliegan en dominios distintos, podría requerirse `SameSite=None` + `Secure` y una configuración CORS con credenciales explícitas, pero esto no se habilitará por defecto.

**Seguridad XSS**:
La cookie HttpOnly reduce el riesgo de robo del identificador de sesión mediante JavaScript, pero no impide que un XSS ejecute solicitudes autenticadas. La aplicación también requiere CSP, sanitización, escape de salida y pruebas contra XSS.

---

## 2. Diseño CSRF (Synchronizer Token)

Como la sesión se almacena en el servidor (Redis), se implementará un **Synchronizer Token asociado a la Sesión** para evitar la vulnerabilidad de las cookies a ataques CSRF.

**Flujo Operativo**:
1. Al crear la sesión, se genera un `csrf_secret` aleatorio.
2. Se guarda asociado al registro de la sesión en Redis.
3. Se entrega al frontend un token CSRF derivado (o el propio token) mediante una respuesta autenticada o un endpoint específico.
4. El frontend lo conserva en memoria y lo adjunta en la cabecera `X-CSRF-Token` en cada petición mutable.
5. FastAPI compara el valor de la cabecera en tiempo constante (`secrets.compare_digest`) con el asociado a la sesión en Redis.
6. Se validará estrictamente para operaciones `POST`, `PUT`, `PATCH` y `DELETE`.
7. El `csrf_secret` será rotado automáticamente al rotar la sesión.

**Defensa en Profundidad Adicional**:
- Validación de las cabeceras `Origin` o `Referer` cuando estén presentes.
- Rechazo de *content types* simples (`application/x-www-form-urlencoded`, `text/plain`, `multipart/form-data`) en endpoints que deben ser puramente `application/json` cuando corresponda.
- Configuración explícita de `SameSite`.
- El token CSRF jamás se aceptará a través del query string de la URL.
- *Nota sobre Double-Submit*: Si en el futuro se requiriese usar un patrón *Double-submit cookie* puramente stateless como alternativa, éste deberá exigir validación HMAC, vinculación criptográfica al identificador de la sesión, comparación en tiempo constante y protección frente a inyección de cookies. No se usará la versión ingenua (comparación simple de cookie vs cabecera).

---

## 3. Modelo `User` y Estrategia de Contraseñas

| Campo | Tipo / Longitud | Nullable | Default | Índices / Constraints |
|---|---|---|---|---|
| `id` | `Integer` | No | Auto | Primary Key, `index=True` |
| `username` | `String(255)` | No | - | `unique=True`, `index=True` |
| `password_hash` | `String(255)` | No | - | - |
| `role` | `String(50)` | No | - | `CheckConstraint("role IN ('ADMIN', 'OPERATOR')")` |
| `is_active` | `Boolean` | No | `True` | - |
| `must_change_password`| `Boolean` | No | `True` | - |
| `created_by_user_id` | `Integer` | Sí | `None` | `ForeignKey("users.id", ondelete="SET NULL")` |
| `created_at` | `DateTime(TZ)`| No | `now()` | - |
| `updated_at` | `DateTime(TZ)`| Sí | `None` | `onupdate=now()` |
| `last_login_at` | `DateTime(TZ)`| Sí | `None` | - |
| `failed_login_count` | `Integer` | No | `0` | - |
| `locked_until` | `DateTime(TZ)`| Sí | `None` | - |
| `password_changed_at` | `DateTime(TZ)`| Sí | `None` | - |

**Tratamiento de Cinco Operadores**:
El despliegue inicial provisionará cinco operadores individualizados. No se creará un Check constraint a nivel de base de datos que limite el número a 5 de manera estricta. Si el modelo de negocio o licencia requiere un límite, éste se diseñará posteriormente como una variable de configuración (`MAX_ACTIVE_OPERATORS`), la cual no se implementará hasta que el usuario confirme si se trata de un límite contractual o solo de las cuentas iniciales del MVP.

**Garantía de ADMIN Único**:
- **Base de datos**: Se garantiza como máximo un administrador mediante un índice único parcial: `CREATE UNIQUE INDEX uq_admin_role ON users (role) WHERE role = 'ADMIN';`.
- **Operacional**: El *bootstrap* y las pruebas automatizadas garantizan que existirá al menos un ADMIN.
- **Aplicación**: Lógica restrictiva para impedir desactivar, eliminar o degradar al ADMIN existente. No existirá ningún endpoint para que un usuario (o incluso el admin) pueda crear un segundo ADMIN.
- **Recuperación**: El script de *break-glass* será la única vía para reactivar a un ADMIN corrompido o revocado.

**Estrategia de Hashing de Contraseñas**:
- Dependencia: `pwdlib[argon2]`.
- Algoritmo Recomendado: **Argon2id**.
- **Retrocompatibilidad**: Se implementará validación compatible con hashes `bcrypt` heredados existentes en el sistema.
- **Rehash Progresivo**: Durante un login exitoso validado contra `bcrypt`, la contraseña en memoria se re-hasheará con Argon2id y se actualizará en base de datos de manera transparente para el usuario.
- **Privacidad**: Jamás se registrarán contraseñas crudas o sus hashes resultantes en logs, AuditLog, ni se devolverán en las respuestas JSON de la API.
- **Abstracción**: Toda la lógica de criptografía se centralizará en una capa de servicio (ej. `PasswordService.hash_password()`, `PasswordService.verify_and_upgrade()`), evitando dispersar código en routers o comandos CLI.

---

## 4. Modelo `CaseFile` (Asignación)
Mantiene `created_by` como autor original. 

| Campo | Tipo | Nullable | Relaciones / Constraints |
|---|---|---|---|
| `assigned_to_user_id`| `Integer` | Sí | `ForeignKey("users.id", ondelete="RESTRICT")`, Indexado |
| `assigned_by_user_id`| `Integer` | Sí | `ForeignKey("users.id", ondelete="SET NULL")` |
| `assigned_at` | `DateTime(TZ)`| Sí | - |

**Reglas**:
- Solo el ADMIN puede asignar, reasignar o desasignar.
- Solo puede asignarse un usuario que exista, que tenga `is_active=True`, y cuyo rol sea `OPERATOR`.
- No se permite asignación a operadores inactivos.
- Al desactivar a un operador, sus expedientes conservan la asignación (`assigned_to_user_id`) pero quedan bloqueados para su operación hasta que el ADMIN los reasigne o reactive al operador.
- `created_by` y `assigned_to_user_id` pueden ser diferentes.
- Expedientes históricos, sin asignar, o migrados, permanecerán sin asignar y serán visibles y operables **únicamente por el ADMIN**.

**Índices**: 
- Índice compuesto/sencillo para listados filtrando por `assigned_to_user_id`.
- Posibilidad de buscar rápidamente registros no asignados (`assigned_to_user_id IS NULL`) para la supervisión global.

---

## 5. AuditLog y Estrategia de Migración

El modelo de `AuditLog` existente (que cuenta con `user_id`, `action`, `entity_type`, `entity_id`, `details`, `created_at`) será migrado cuidadosamente en base a los datos vivos.

**Metodología de Migración para AuditLog**:
1. Conteo preliminar de los registros actuales.
2. Inspección del contenido de `details` (tipo String) para verificar si es JSON válido.
3. **Conversión**: Si el 100% es convertible de forma segura, se migrará `details` a tipo `JSONB` empleando una conversión explícita (`USING details::jsonb`).
4. **Fallback**: Si hay textos libres irrecuperables, se conservará la columna `details` actual (String) y se añadirá un nuevo campo `metadata_safe` (JSONB). **No se descartarán datos históricos**.
5. Para `entity_id` (Integer): Se verificará el tipo real en uso. Su paso a `String` (para alojar UUIDs futuros) requerirá conversión explícita (`USING entity_id::varchar`). Se documentará debidamente que un *downgrade* de esta migración podría ser imposible en caso de insertarse posteriormente un UUID.
6. Inclusión de campo funcional necesario: adición de columna para resultado/estado (`status` o `result`).

**Catálogo Centralizado de Eventos (Enum)**:
- `AUTH_LOGIN_SUCCEEDED`, `AUTH_LOGIN_FAILED`, `AUTH_LOGOUT`, `AUTH_PASSWORD_CHANGED`, `ADMIN_RECOVERY`
- `USER_CREATED`, `USER_ACTIVATED`, `USER_DEACTIVATED`, `USER_PASSWORD_RESET`
- `CASE_CREATED`, `CASE_ASSIGNED`, `CASE_REASSIGNED`, `CASE_UNASSIGNED`
- `REQUIREMENT_UPLOADED`, `QUOTATION_UPLOADED`
- `SECTION_UPDATED`, `SECTIONS_CONFIRMED`
- `COMPARISON_RUN`, `OUTPUT_GENERATED`, `OUTPUT_VIEWED`
- `ACCESS_DENIED`

**Políticas de Registro**:
- Se debe capturar: `actor`, `recurso`, `estado`, y metadatos permitidos.
- El registro (commit transaccional) del evento en negocio se hará explícitamente en el servicio, de manera unificada y fiable, no dependiente de middlewares HTTP vagos.
- Definir comportamiento de degradación: Si `AuditLog` no puede persistirse por un fallo secundario o pérdida de conectividad transitoria, se deben registrar alertas críticas en APM/Logs estándar en lugar de causar indisponibilidad dura (según análisis de riesgo final).
- Jamás registrar: contraseñas temporales, password_hash, cookies, session_ids crudos completos, tokens CSRF, cabeceras Authorization, API keys ni contenidos íntegros de documentos.

---

## 6. Contrato de Autorización y Endpoints

### Componentes de Seguridad (Dependencias FastAPI)
- `get_current_user`: Base, decodifica sesión. Retorna usuario activo.
- `require_active_user`: Lanza 401 si no está activo o la sesión expiró/fue revocada.
- `require_password_changed`: Valida `must_change_password=False`. Un usuario con requerimiento activo solo podrá acceder a endpoints mínimos (logout, perfil, endpoint para enviar nueva contraseña).
- `require_admin`: Autorización global (403 si no es ADMIN).
- Lógica de Recursos Base (Retornan recurso o lanzan 404 para mitigar enumeración):
  - `get_authorized_case_or_404`
  - `get_authorized_section_or_404` (resuelve el CaseFile padre)
  - `get_authorized_job_or_404` (resuelve el CaseFile padre)
  - `get_authorized_output_or_404` (resuelve el CaseFile padre)

### Reglas
- ADMIN posee acceso global transversal.
- OPERATOR solo tendrá acceso condicionado cuando: `case.assigned_to_user_id == current_user.id`.
- Recursos sin asignación son dominio exclusivo de ADMIN.
- No se confiará en UUIDs o secuencias complejas como medida de control de acceso.
- Códigos HTTP: 404 (Recurso inexistente o ajeno, previniendo enumeración), 403 (Ruta/operación denegada administrativamente), 401 (Ausencia de sesión, expiración, inactividad, necesidad imperante de cambiar clave).

### Endpoints
**Creación y Asignación de Expedientes**:
- `POST /cases/`: Se conserva exclusivo de ADMIN (created_by=ADMIN).
  - *Decisión Pendiente*: Confirmar si en una versión posterior un OPERATOR puede crear un caso autoasignado. No se desarrollará hasta definición de producto.
- `PATCH /cases/{case_id}/assignment`: Exclusivo de ADMIN. Payload `{"assigned_to_user_id": <int|null>}`. La obtención y pérdida de derechos de acceso derivados de la mutación es inmediata. Validará colisiones o inactividad del target operator. Registrará `CASE_ASSIGNED`, `CASE_REASSIGNED` o `CASE_UNASSIGNED` correspondientemente.

**Administración de Usuarios (`/admin/users/*`)**:
- Exclusiva de ADMIN.
- `POST`: Crea únicamente operadores. Genera contraseña temporal segura. Puede devolverla *exactamente una vez* en la respuesta 201 y activará `must_change_password=True`. JAMÁS en log o historial.
- `RESET`: Genera nueva contraseña temporal, activa obligación de cambio, invalida indiscriminadamente TODAS las sesiones activas previas del usuario, y prohíbe explícitamente reusar/ver la clave vieja.
- Ningún endpoint, independientemente de su verbosidad (GET, POST, etc), exfiltrará o mapeará atributos correspondientes al `password_hash`.

---

## 7. Plan de Migración (Alembic)

Secuencia orquestada y ordenada, previa comprobación inicial, sin crear scripts todavía:
1. Inspeccionar datos heredados y tipado de `AuditLog`.
2. Actualización de esquema temporal: Añadir nuevos campos `User` y `CaseFile` de forma tolerante a nulos (NULL allowed).
3. Migración de datos integrados (`UPDATE users SET role='OPERATOR' WHERE role='readonly' OR role IS NULL`).
4. Aplicación de `NOT NULL`, Default bounds, Restricciones CHECK (`role IN ('ADMIN', 'OPERATOR')`), Foreign Keys y constraint Parcial para el ADMIN único.
5. Modificación a tipados y estructura definitiva del `AuditLog`.
6. En un escenario independiente del framework de Alembic (para no inyectar secretismo ni quemar usuarios transaccionalmente), se prevé un _bootstrap manual o vía CLI local_ pos-migración: `python -m app.cli.bootstrap_admin`.
7. Diseñar las directivas reversibles `down_revision`.

---

## 8. Break-glass (Recuperación Administrativa)

Herramienta perimetral que asume vulneración total de los accesos API del sistema.
**Comando**: `python -m app.cli.admin_reset`

**Reglas Operativas**:
- El comando se ejecuta obligatoriamente en contexto de acceso privilegiado al servidor de producción/contenedor de base de datos.
- Prohibición estricta de leer contraseñas a través de la terminal pública o por parámetros CLI de inicio visibles en procesos OS. 
- La ingesta de la nueva clave de emergencia se debe adquirir a través de prompts de texto protegidos (e.g. `getpass`), entrada estándar entubada asegurada, o un archivo de secreto montado temporalmente de naturaleza *read-once* que cumpla con políticas rigurosas de File System.
- Su ejecución creará al ADMIN si es un `bootstrap` primigenio (y se verifica su inasistencia absoluta). Si ya existe, reseteará la clave a Argon2id, reactivará el estado `is_active=True`, ordenará obligación de rotar password `must_change_password=True`, liquidará íntegramente las sesiones Redis vigentes, y grabará la anomalía como evento `ADMIN_RECOVERY` desvinculado (actor `NULL`, metadata referenciando el `break-glass`).
- Empleará un flujo de salida (Stdout/Stderr) aséptico sin imprimir *hashes* o *strings*.

---

## 9. Plan de Pruebas Definitivo

### Sesión
- El identificador almacenado en Redis **no** se registra en texto plano en la metadata.
- El prefijo seguro `__Host-` se emite apropiadamente bajo entorno de `production`.
- La configuración de producción declina forzosamente inicializar cookies con atributo `Secure=false`.
- Expiración proactiva y determinista basada en inactividad. Expiración absoluta.
- Petición de baja revoca exitosamente TODAS las sesiones concurrentes para la entidad.
- Rotación del `sid` es forzada y validada luego del éxito en autenticación y mudanza de contraseña.
- Conexión caída o Redis vaciado desautoriza las sesiones en ráfaga (falla de forma segura).

### CSRF
- Intento de mutación (POST/PUT/DELETE) desprovisto de Token detona un 403 Forbidden.
- Intento con Token adulterado 403.
- Token derivado de otra sesión simultánea se valida negativamente, causando 403.
- Flujo legítimo con token correcto devuelve HTTP Success correspondiente.
- Métodos estériles `GET/HEAD/OPTIONS` operan desvinculados de comprobación del Synchronizer Token.
- La sustitución/rotación del ticket de sesión invalida al token CSRF antiguo.
- Operación criptográfica interna de la verificación CSRF ejecuta en tiempo constante para mitigar análisis lateral/temporizado.

### Contraseñas
- Generación de nueva identidad se consolida con Argon2id.
- Usuarios vigentes con BCrypt operan sin interrupción en primera autenticación.
- Verificación correcta de clave pre-existente detona el mecanismo de Upgrade BCrypt -> Argon2id transparente y definitivo.
- Intento ilegítimo declina operación, logea el suceso en auditoría de Auth sin tocar o mutar los algoritmos del hash en base.
- Ni trazas HTTP ni registros de logs de contenedor evidencian trazas crudas del hash resultante o clave en memoria en ningún tramo de ejecución.

### Usuarios
- Perfil `ADMIN` instaura exitosamente la cuota de los primeros 5 `OPERATOR`.
- Imposibilidad de instanciar la dualidad de perfil `ADMIN` a nivel de negocio y restricción a nivel BD.
- Perfil `OPERATOR` inhibido de ejecutar o enumerar recursos dentro de URIs de `/admin/users/`.
- Perfil inhabilitado recibe rebote prematuro de login en primer ciclo de validación del servicio JWT/Cookie.
- El comando de baja/deactivate elimina en cascada lógica y en memoria a través de Redis las sesiones previas.
- Secuencia de Reset invalida ráfaga de credenciales residuales y activa obligación en flag pertinente.
- Token temporal del `POST /admin/users` transfiere al body _una única vez_ y perece en el contexto. Sin trazas residuales en la auditoría.

### Expedientes
- Consigna de Creación (POST) reservada al `ADMIN`.
- ADMIN confiere el control de Expediente(A) a OPERATOR Activo(1).
- Intento de ADMIN de trasladar control a OPERATOR Inactivo aborta por regla de negocio.
- OPERATOR (1) visualiza solo su ecosistema (A).
- Intervención de Reasignación detona revocación de acceso in situ, denegando permisos residuales que el OPERATOR original pretendiese ostentar en solicitudes contemporáneas.
- Todo ecosistema de artefactos, cotizaciones y resultados dependientes del Expediente (A) se acogen estrictamente a la matriz de autoridad del padre.
- Expedientes ausentes de asignación listan exentos al flujo del OPERATOR (quien recibiría un 404). Accesibles y operables puramente por ADMIN.

### Auditoría
- Secuencias consumadas de lógica de dominio (Éxito).
- Alteraciones negadas, violaciones o insuficiencia de escalado vertical, abortos.
- Rechazos proactivos en la capa del router o middleware se trazan apropiadamente bajo catalogación de política.
- Insistencia en la omisión y no persistencia de material protegido (secretos API, Hashes o CSRF params).
- Eficiencia funcional en el endpoint GET de auditoría, demostrando filtros (timestamp, severidad, case_id) y paginación.

---

## 10. Plan de Implementación (Commits Secuenciales)

Se planifica el diseño de un abordaje atómico garantizando control sobre cada regresión:

1. `test: add authz model and migration contract tests`
   - *Este commit de Contrato/Prueba definirá roles, restricción del ADMIN, migración sobre roles heredados (legacy) y la persistencia ampliada/correcta sobre expedientes y AuditLog actual. No alterará todavía el modelo SQL real.*
2. `feat(authz): extend user, case assignment and audit models`
3. `feat(auth): add admin bootstrap and recovery commands`
4. `feat(auth): add Redis-backed opaque sessions`
5. `feat(auth): add login, logout and password change`
6. `feat(admin): add user administration`
7. `feat(authz): add case assignment`
8. `feat(authz): protect cases and child resources`
9. `feat(audit): record security and business events`
10. `feat(ui): add login and admin interfaces`
11. `test(security): add full authz regression`
12. `chore(security): harden cookies, CSRF, CORS and API docs`

---

## 11. Decisiones Todavía Pendientes

1. **Exposición de la Plataforma**: Definir si la aplicación operará exclusivamente en red interna/VPN, expuesta a Internet o un sistema híbrido (lo cual agrava el modelo de amenazas de endpoints).
2. **Proveedor OIDC**: Determinar si en un plazo a futuro un proveedor corporativo externo (e.g. Identity Providers centralizados empresariales) delegará el login y las políticas del portal, reemplazando la persistencia de autenticación provista por esta solución puramente local.
3. **Auditoría de Lecturas**: Reevaluar el requisito de trazabilidad sobre operaciones exentas de mutación (los GET masivos). Trazar y auditar consultas de Expedientes individuales acarrea altos compromisos en retención transaccional (Volumen logarítmico vs valor de control).
4. **Retención de AuditLog**: La política de retención transaccional o purga temporal de la tabla de Auditoria (siempre que las políticas de retención legal para Compliance de la plataforma así lo exijan).
5. **Creación de Expedientes por Operadores**: Decisión pendiente: “¿Los OPERATOR únicamente procesan expedientes asignados o también pueden crear un expediente que quede automáticamente asignado a ellos?”. No iniciar la implementación de esta ruta hasta su clarificación.
