# V6 Backup Strategy

## 1. Overview
Esta estrategia define los mecanismos para garantizar la persistencia de datos (RPO) y los tiempos de recuperacion (RTO) del entorno V6 Local Enterprise.

## 2. Componentes a Respaldar
1. **PostgreSQL Database (`abst_postgres`)**: Contiene todo el estado transaccional, expedientes, logs de IA, hashes y workflow.
2. **Document Storage**: Almacenamiento local mapeado para PDFs (S3 minio u host mount).
3. **Configuration**: Archivos `.env` y `docker-compose.local.yml`.

## 3. Frecuencia y Retencion
- **Frecuencia**: Un backup completo (pg_dumpall) se dispara cada 24 horas a las 02:00 AM mediante crontab en el servidor host.
- **Retencion**: Se mantienen localmente 7 backups rotativos diarios y 4 semanales, despues de lo cual se archivan en almacenamiento frio o se eliminan.

## 4. Validacion
- Al menos una vez al mes, el equipo SRE debe levantar un contenedor paralelo e importar el ultimo dump para confirmar que los datos no esten corruptos (Restore Drill).
