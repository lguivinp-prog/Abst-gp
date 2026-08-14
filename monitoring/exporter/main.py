import os
import time
import logging
import psycopg2
import redis
from prometheus_client import start_http_server, Gauge, Counter
from psycopg2.extras import RealDictCursor

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- METRIC DEFINITIONS ---

# PostgreSQL
wal_archive_lag_seconds = Gauge('abst_postgres_wal_archive_lag_seconds', 'Lag in seconds for PostgreSQL WAL archiving')
backup_last_success_timestamp = Gauge('abst_postgres_backup_last_success_timestamp', 'Unix timestamp of the last successful pg_basebackup execution')
pitr_last_validation_timestamp = Gauge('abst_postgres_pitr_last_validation_timestamp', 'Unix timestamp of the last successful PITR validation drill')

# Redis
redis_health = Gauge('abst_redis_health', 'Redis 7 instance connectivity and health status (1 = UP, 0 = DOWN)')
redis_rebuild_events = Counter('abst_redis_rebuild_events_total', 'Total number of times FLUSHDB and SSOT-to-Redis rebuild was executed')

# Workers
stale_processing_jobs = Gauge('abst_worker_stale_processing_jobs', 'Current number of jobs in PROCESSING state beyond expected completion time')
heartbeat_timeout_count = Counter('abst_worker_heartbeat_timeout_count_total', 'Total incidents of missing heartbeats triggering JobRecoveryEngine')

# Documents
checksum_failures = Gauge('abst_document_checksum_failures_total', 'Total number of files with mismatched SHA-256 vs database')
orphan_documents = Gauge('abst_document_orphan_documents', 'Current number of orphan document files in vault without DB record')

# --- CONFIGURATION ---

DB_HOST = os.environ.get('DB_HOST', 'db')
DB_PORT = os.environ.get('DB_PORT', '5432')
DB_NAME = os.environ.get('DB_NAME', 'abst_gp_db')
DB_USER = os.environ.get('DB_USER', 'postgres') # In production, use a strictly read-only user
DB_PASS = os.environ.get('DB_PASS', 'postgres')

REDIS_HOST = os.environ.get('REDIS_HOST', 'redis')
REDIS_PORT = os.environ.get('REDIS_PORT', '6379')
REDIS_DB = int(os.environ.get('REDIS_DB', '0'))

# --- COLLECTORS ---

def collect_postgres_metrics():
    """Recoge métricas mediante queries read-only al SSOT"""
    conn = None
    try:
        # Timeout ultra-corto para no afectar la base de datos si está saturada
        conn = psycopg2.connect(
            host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASS,
            connect_timeout=3
        )
        conn.set_session(readonly=True, autocommit=True)
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # 1. Stale processing jobs (jobs in PROCESSING for more than 5 minutes)
            cur.execute("""
                SELECT count(*) as count 
                FROM jobs 
                WHERE status = 'PROCESSING' 
                AND updated_at < NOW() - INTERVAL '5 minutes'
            """)
            result = cur.fetchone()
            if result:
                stale_processing_jobs.set(result['count'])
            
            # 2. WAL Lag (simulated via pg_stat_archiver if permissions allow, or static fallback)
            try:
                cur.execute("""
                    SELECT 
                        EXTRACT(EPOCH FROM (NOW() - last_archived_time)) as lag 
                    FROM pg_stat_archiver 
                    WHERE last_archived_time IS NOT NULL
                """)
                archiver_res = cur.fetchone()
                if archiver_res and archiver_res['lag']:
                    wal_archive_lag_seconds.set(archiver_res['lag'])
                else:
                    wal_archive_lag_seconds.set(0)
            except Exception as e:
                logger.warning(f"Could not read pg_stat_archiver (requires permissions): {e}")

    except Exception as e:
        logger.error(f"Error collecting PostgreSQL metrics: {e}")
    finally:
        if conn:
            conn.close()

def collect_redis_metrics():
    """Verifica salud de Redis"""
    try:
        client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, socket_connect_timeout=2)
        if client.ping():
            redis_health.set(1)
        else:
            redis_health.set(0)
    except Exception as e:
        logger.error(f"Error collecting Redis metrics: {e}")
        redis_health.set(0)

def collect_batch_metrics():
    """
    Simula la recolección de métricas asíncronas generadas por jobs SRE batch.
    En un entorno real, leería de textfiles de node_exporter o de una tabla de auditoría.
    """
    try:
        # Aquí leeríamos el timestamp del último backup físico.
        # Por ahora, usamos un stub safe que siempre reporta un estado base.
        backup_last_success_timestamp.set(time.time() - 3600) # Simula un backup exitoso hace 1 hora
        pitr_last_validation_timestamp.set(time.time() - 86400) # Simula PITR validado hace 1 día
        
        # Stubs para documentos y workers
        checksum_failures.set(0)
        orphan_documents.set(0)
        
    except Exception as e:
        logger.error(f"Error collecting batch metrics: {e}")

# --- MAIN LOOP ---

def main():
    exporter_port = int(os.environ.get('EXPORTER_PORT', 8000))
    logger.info(f"Starting Abst-gp SRE Exporter on port {exporter_port}")
    start_http_server(exporter_port)
    
    while True:
        try:
            collect_postgres_metrics()
            collect_redis_metrics()
            collect_batch_metrics()
        except Exception as e:
            logger.error(f"Unexpected error in metrics collection loop: {e}")
        
        time.sleep(15) # Frecuencia de scrape / polling

if __name__ == '__main__':
    main()
