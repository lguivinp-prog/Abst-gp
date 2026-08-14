# Abast-gp V6 - Manual del Administrador (IT)

## 1. Mantenimiento del Nodo Local
- Revise periódicamente la carpeta `logs/` de los contenedores Docker para rastrear errores 500 (`docker-compose logs -f`).
- Las actualizaciones se despliegan reemplazando el archivo `docker-compose.yml` y corriendo `docker-compose up -d`. Esto no afecta la BD Postgres (V5.5 Legacy).

## 2. Gestión de Usuarios
- Para asignar permisos especiales (Rol `SUPERVISOR`), utilice el panel de control institucional.
- Todo cambio de credenciales o accesos queda almacenado en la bitácora `AuditLog`.

## 3. Resolución de Problemas (Troubleshooting)
- Si el módulo RAG falla por "Out of Memory", verifique en el htop que el contenedor tenga al menos 4GB de RAM asignada.
- Si la Validación Externa (SUNAT/RNP) no responde, verifique que los firewalls institucionales de la OGT (Tecnologías) permitan conexiones HTTPS salientes.
