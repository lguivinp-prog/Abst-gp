# Abast-gp V7 Beta Pilot: SRE Runbook

## 1. Startup
Para iniciar el entorno piloto de forma aislada, asegurándose de no afectar V6.1:
```bash
docker-compose -f docker-compose.v7-staging.yml up -d
```
Asegurar que el estado del **VectorEngineRouter** esté forzado a `DUAL_READ` para recolectar telemetría en *Shadow Mode*.

## 2. Monitoreo (Observability)
Verificar en el dashboard de Prometheus / Grafana las siguientes métricas:
- `v7_vector_engine_switch_total`: Debe ser cero o esporádico. Un incremento constante indica *flapping*.
- `v7_shadow_dropped_total`: Si este valor sube por encima de 10 por minuto, el disco es demasiado lento o hay exceso de carga, evaluar redimensionar el *Shadow Queue*.
- **PostgreSQL RAM**: pgvector requiere *Shared Buffers* adecuados; monitorear el contenedor `pgvector-staging`.

## 3. Manejo de Incidentes (Incident Response)
**Alerta: `Gateway Latency Exceeds 200ms`**
- **Causa probable**: Bloqueos I/O (aunque mitigado por Async Queue) o Redis inestable.
- **Acción**: Si es grave, suspender `DUAL_READ` transicionando manualmente la variable de entorno a `FAISS_ONLY` y reiniciar los pods del Gateway.

**Alerta: `Redis OOM (Out Of Memory)`**
- **Causa probable**: *Backfill Workers* están inyectando tareas más rápido de lo que Celery puede procesar.
- **Acción**: Pausar el *MigrationJob* desde el controlador del Backfill, permitiendo que Redis despache la cola (apoyado en la política `volatile-lru`).

## 4. Rollback
El sistema tiene **Rollback Automático**. Si el *Error Rate* de pgvector excede 5% (sobre un buffer de 100 requests), el Gateway cortocircuita las llamadas a V7 y usa FAISS exclusivamente. 
Para aplicar un *Hard Rollback* manual (apagado total del piloto):
```bash
docker-compose -f docker-compose.v7-staging.yml down
```

## 5. Shutdown
Si el piloto se declara exitoso o finalizado:
- Detener los Workers de Celery para purgar de forma limpia las colas.
- Recuperar y empaquetar `shadow_eval.log` para análisis de `Recall`.
- Apagar el stack.
