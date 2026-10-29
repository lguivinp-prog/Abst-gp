# ABST-GP V6 — PAQUETE DE INSTALACIÓN Y MIGRACIÓN A SERVIDOR LINUX (P19)

Este paquete contiene la configuración de despliegue, scripts de respaldo/restauración y directivas de seguridad para el traslado de ABAST-GP V6 desde el anfitrión piloto a un servidor Linux dedicado institucional.

---

## 1. Inventario de Archivos del Paquete Portable

* `docker-compose.linux.yml`: Perfil de producción con Caddy HTTPS 443, PostgreSQL 15, Redis 7, API, Workers, Web SPA y volúmenes persistentes.
* `Caddyfile.linux`: Configuración TLS Reverse Proxy de Caddy con bloqueo perimetral de `/docs`, `/metrics` y cabeceras HSTS/CSP.
* `.env.linux.template`: Plantilla de variables de entorno con diferenciación estricta de Fase 1 (Restauración) y Fase 2 (Rotación).
* `restore_linux.sh`: Script ejecutable para restaurar el respaldo firmado y cifrado P19 sobre la base destino.
* `backup_linux.sh`: Script ejecutable para programar respaldos consistentes periódicos en producción.
* `rollback_linux.sh`: Script de detención limpia ante contingencias (sin `-v`, preservando volúmenes y respaldos).

---

## 2. Procedimiento de Migración en Dos Fases

### FASE 1: Restauración Inicial con Claves de Origen (Obligatorio)
1. Clonar el repositorio en el servidor Linux en el commit certificado `d8663e48b05f9d671fd1244f5c36211be648f91d`.
2. Copiar `.env.linux.template` a `.env.production` y asignar permisos `chmod 600 .env.production`.
3. Extraer desde la custodia segura las claves criptográficas vigentes del piloto:
   * `BACKUP_ENCRYPTION_KEY`
   * `BACKUP_SIGNING_KEY`
   * `MFA_ENCRYPTION_KEY`
   * Pegarlas en `.env.production`.
4. Copiar el archivo de respaldo exportado `pilot_backup_p19.tar.enc` y su manifiesto `.manifest.json` a `/data/backups/`.
5. Ejecutar la restauración:
   ```bash
   bash deployment/linux_package/restore_linux.sh /data/backups/pilot_backup_p19.tar.enc .env.production
   ```
6. Iniciar el stack completo:
   ```bash
   docker compose --project-directory . --env-file .env.production -f deployment/linux_package/docker-compose.linux.yml up -d
   ```
7. Verificar login con `pilot_superadmin` utilizando TOTP y acceso a los expedientes existentes.

### FASE 2: Rotación Controlada Post-Verificación
Una vez acreditada la operatividad y recuperación integral en el servidor Linux:
1. **Rotar `SECRET_KEY`:** Generar un nuevo token de 64 caracteres hex (`openssl rand -hex 32`) para invalidar sesiones previas.
2. **Rotar contraseñas de infraestructura:** Cambiar `POSTGRES_PASSWORD` y `REDIS_PASSWORD` actualizando las credenciales de conexión interna.
3. **Rotar claves de respaldo:** Generar un nuevo respaldo de producción con la nueva clave de cifrado y firma.

---

## 3. Resolución P16 de Secretos
El archivo `verification/dr/backup_lan_pg15.py` está montado en modo sólo lectura (`:ro`) en `/app/verification` dentro del contenedor `api`, garantizando:
* Ninguna contraseña se pasa por línea de comandos.
* La URL de base de datos se sanea en logs y journals (`target_db_ref` y fingerprints SHA-256).
* Cuarentena preventiva fail-closed (`_dr_restoration_quarantine`) que se levanta únicamente tras verificar la completitud conjunta de base de datos y archivos documentales.
