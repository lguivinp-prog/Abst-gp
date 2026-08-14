# SRE OBSERVABILITY ARCHITECTURE

**Plataforma**: Abst-gp (V5.6 Enterprise Readiness)  
**Módulo**: Observability & Telemetry Framework  
**Fecha**: 2026-08-08  
**Clasificación**: Arquitectura de Producción SRE  

---

## 1. ARQUITECTURA DE MÉTRICAS OPERACIONALES

La observabilidad de Abst-gp se diseña para proporcionar visibilidad ininterrumpida de los componentes transaccionales, repositorios de documentos y colas de trabajo, asegurando que las capacidades de recuperación (Disaster Recovery) estén continuamente resguardadas sin incurrir en degradación de la lógica de negocio certificada.

### Flujo de Captura y Emisión

1. **Agentes de Extracción (Scraping)**: Las métricas no intrusivas se recolectarán directamente desde los volúmenes, la base de datos (mediante scripts read-only) y exportadores estándar sin sobrecargar el código de dominio de Abst-gp (`JobRepository`, `ProcessingJob`).
2. **Sistema Central de Monitoreo (Prometheus)**: Actúa como recolector central de series de tiempo.
3. **Módulo de Alertamiento (Alertmanager)**: Evalúa las métricas en tiempo real y dispara notificaciones hacia los equipos de guardia.

---

## 2. FUENTES DE TELEMETRÍA

| Subsistema / Fuente | Exportador / Mecanismo de Captura |
| :--- | :--- |
| **PostgreSQL 16 (SSOT)** | `postgres_exporter` (Query a `pg_stat_archiver` y `pg_stat_replication`) y scripts de auditoría periódica de cron para `backup_last_success`. |
| **Redis 7 (Brokers)** | `redis_exporter` nativo (Lectura de health checks e índices de colas). |
| **Workers OCR / Comparación** | Consultas agregadas de lectura (read-only) al SSOT PostgreSQL para contar workers inactivos (`heartbeat_timeout`) y tareas estancadas (`stale`). |
| **Almacenamiento Documental** | Script batch asíncrono (fuera del camino crítico de transacciones) validando checksums en volúmenes `/storage/documents`. |

---

## 3. FRECUENCIA DE RECOLECCIÓN

- **Métricas de Alta Prioridad (Health y Broker Lag)**: $15 \text{ segundos}$ (Ej: `redis_health`).
- **Métricas Transaccionales (Stale Jobs / WAL Lag)**: $60 \text{ segundos}$.
- **Métricas Pesadas (Verificación Documental Completa / PITR Validation)**: Intervalos programados (Diario a las 02:00 UTC) mediante Jobs asíncronos SRE.

---

## 4. MATRIZ DE RESPONSABLES

- **Lead SRE**: Configuración de `Prometheus` y `Alertmanager` en el plano de control (Kubernetes / Docker Swarm).
- **Database Administrator (DBA)**: Mantenimiento y optimización de las sentencias SQL read-only del `postgres_exporter` para no impactar la base de datos certificada.
- **Application Owner**: Aceptación técnica de las métricas. (Sin permisos de modificación directa sobre la infraestructura DR certificada).
