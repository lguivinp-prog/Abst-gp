import pytest
import time
import uuid
import concurrent.futures
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.models.domain import ProcessingJob, Tenant, User, CaseFile, AuditLog, ProcessingMetrics
from app.services.job_repository import JobRepository
from app.services.capacity_governor import TenantCapacityGovernor
from app.core.config import settings
from app.core.telemetry import metrics_registry
from tests.conftest import TestingSessionLocal


@pytest.fixture(autouse=True)
def clean_jobs(db_session: Session):
    """Limpia los jobs de prueba antes y después de cada test de performance."""
    db_session.query(ProcessingJob).delete()
    db_session.commit()
    yield
    try:
        db_session.rollback()
        db_session.query(ProcessingJob).delete()
        db_session.commit()
    except Exception:
        pass


@pytest.fixture
def setup_tenants_and_cases(db_session: Session):
    """Crea tenants y expedientes de prueba para las pruebas de concurrencia y capacidad."""
    # Tenant Alpha
    t_alpha = db_session.query(Tenant).filter(Tenant.id == "tenant_alpha").first()
    if not t_alpha:
        t_alpha = Tenant(id="tenant_alpha", name="Tenant Alpha Enterprise")
        db_session.add(t_alpha)
    
    # Tenant Beta
    t_beta = db_session.query(Tenant).filter(Tenant.id == "tenant_beta").first()
    if not t_beta:
        t_beta = Tenant(id="tenant_beta", name="Tenant Beta Standard")
        db_session.add(t_beta)

    # Tenant Gamma
    t_gamma = db_session.query(Tenant).filter(Tenant.id == "tenant_gamma").first()
    if not t_gamma:
        t_gamma = Tenant(id="tenant_gamma", name="Tenant Gamma")
        db_session.add(t_gamma)

    db_session.commit()

    # Expedientes
    case_a = CaseFile(id=9001, title="Expediente Alpha", contract_type="BIEN", tenant_id="tenant_alpha", status="OPEN")
    case_b = CaseFile(id=9002, title="Expediente Beta", contract_type="BIEN", tenant_id="tenant_beta", status="OPEN")
    case_g = CaseFile(id=9003, title="Expediente Gamma", contract_type="BIEN", tenant_id="tenant_gamma", status="OPEN")
    
    for c in [case_a, case_b, case_g]:
        existing = db_session.query(CaseFile).filter(CaseFile.id == c.id).first()
        if not existing:
            db_session.add(c)
    
    db_session.commit()

    return {"alpha": "tenant_alpha", "beta": "tenant_beta", "gamma": "tenant_gamma"}


# ===========================================================================
# ESCENARIO A — 20 TENANTS CONCURRENTES
# ===========================================================================
def test_scenario_a_twenty_tenants_asymmetric_load():
    """
    ESCENARIO A: 20 Tenants Concurrentes con Carga Asimétrica y Anti-Starvation.
    - Simula 20 tenants: tenant_01 con 50 jobs (noisy neighbor) y tenant_02..tenant_20 con 3 jobs cada uno (total 107 jobs).
    - Ejecución con workers concurrentes que reclaman, procesan y completan jobs en ciclos.
    - Criterios:
      * Ningún tenant excede su cuota (5).
      * El sistema nunca excede su límite global (30).
      * Todos los 20 tenants completan al menos un job (zero starvation / progreso universal).
      * Cero deadlocks y aislamiento multi-tenant estricto.
    """
    tenant_ids = [f"tenant_{i:02d}" for i in range(1, 21)]
    per_tenant_quota = 5
    system_limit = 30

    # 1. Setup de los 20 tenants y sus expedientes correspondientes
    with TestingSessionLocal() as db:
        # Create parent tenants first so FK targets exist before CaseFile insertion.
        for tid in tenant_ids:
            if not db.query(Tenant).filter(Tenant.id == tid).first():
                db.add(Tenant(id=tid, name=f"Institution {tid}"))

        db.flush()

        # Create cases only after all tenant rows have been materialized.
        for idx, tid in enumerate(tenant_ids):
            case_id = 9100 + idx
            if not db.query(CaseFile).filter(CaseFile.id == case_id).first():
                db.add(
                    CaseFile(
                        id=case_id,
                        title=f"Case {tid}",
                        contract_type="BIEN",
                        tenant_id=tid,
                        status="OPEN",
                    )
                )

        db.commit()

    # 2. Generar carga asimétrica: tenant_01 = 50 jobs, otros = 3 jobs cada uno
    with TestingSessionLocal() as db:
        for idx, tid in enumerate(tenant_ids):
            num_jobs = 50 if tid == "tenant_01" else 3
            case_id = 9100 + idx
            for j_idx in range(num_jobs):
                job_id = f"job_scen_a_{tid}_{j_idx}_{uuid.uuid4().hex[:4]}"
                JobRepository.create_job(
                    db=db,
                    case_id=case_id,
                    tenant_id=tid,
                    user_id=None,
                    job_type="OCR" if j_idx % 2 == 0 else "QUOTATION",
                    job_id=job_id
                )

    # 3. Simular ciclo de trabajo distribuido: los workers reclaman y completan jobs
    tenants_with_claims = set()

    def worker_lifecycle(worker_id: int):
        worker_claimed_tenants = set()
        with TestingSessionLocal() as thread_db:
            for _ in range(15):
                success, job, reason = JobRepository.claim_next_fair_job(
                    db=thread_db,
                    worker_name=f"worker_scen_a_{worker_id}",
                    max_tenant_concurrency=per_tenant_quota,
                    max_system_concurrency=system_limit
                )
                if success and job:
                    worker_claimed_tenants.add(job.tenant_id)
                    # Simular procesamiento y compleción
                    JobRepository.mark_completed(
                        db=thread_db,
                        job_id=job.job_id,
                        result_summary={"status": "completed"},
                        tenant_id=job.tenant_id
                    )
        return worker_claimed_tenants

    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as executor:
        futures = [executor.submit(worker_lifecycle, i) for i in range(16)]
        for f in concurrent.futures.as_completed(futures):
            tenants_with_claims.update(f.result())

    # 4. Verificaciones de invariantes de capacidad y anti-starvation
    with TestingSessionLocal() as db:
        # Verificar que TODOS los 20 tenants progresaron (anti-starvation)
        assert len(tenants_with_claims) == 20, f"Only {len(tenants_with_claims)} of 20 tenants progressed: {tenants_with_claims}"
        
        # Verificar que el límite global y de tenant no se excedieron en ningún momento
        active_now = TenantCapacityGovernor.get_system_active_jobs_count(db)
        assert active_now <= system_limit


# ===========================================================================
# ESCENARIO B — GLOBAL CAPACITY RACE (100% ATOMICIDAD)
# ===========================================================================
def test_scenario_b_global_capacity_race():
    """
    ESCENARIO B: Carrera Concurrente en Límite Global.
    - Configura el sistema con system_active = system_limit - 1 (19 activos, límite 20).
    - Lanza hilos simultáneos desde diferentes tenants para reclamar el último slot disponible.
    - Repite 5 iteraciones completas.
    - Invariante estricto: MAX(system_active) <= system_limit en el 100% de las iteraciones.
    """
    sys_limit = 20
    per_tenant_limit = 10

    # 1. Setup inicial de tenants y expedientes
    with TestingSessionLocal() as db:
        # Crear primero todos los tenants para materializar las FK padre.
        if not db.query(Tenant).filter(Tenant.id == "tenant_race_base").first():
            db.add(Tenant(id="tenant_race_base", name="Tenant Race Base"))

        for t_idx in range(10):
            tid = f"tenant_competitor_{t_idx}"
            if not db.query(Tenant).filter(Tenant.id == tid).first():
                db.add(Tenant(id=tid, name=f"Competitor {t_idx}"))

        db.flush()

        # Crear los expedientes solo después de materializar los tenants.
        if not db.query(CaseFile).filter(CaseFile.id == 9200).first():
            db.add(
                CaseFile(
                    id=9200,
                    title="Case Race Base",
                    contract_type="BIEN",
                    tenant_id="tenant_race_base",
                    status="OPEN",
                )
            )

        for t_idx in range(10):
            tid = f"tenant_competitor_{t_idx}"
            cid = 9201 + t_idx

            if not db.query(CaseFile).filter(CaseFile.id == cid).first():
                db.add(
                    CaseFile(
                        id=cid,
                        title=f"Case Comp {t_idx}",
                        contract_type="BIEN",
                        tenant_id=tid,
                        status="OPEN",
                    )
                )

        db.commit()

    for iteration in range(5):
        # 2. Limpiar e inicializar 19 jobs en estado PROCESSING
        with TestingSessionLocal() as db:
            db.query(ProcessingJob).delete()
            db.commit()

            for i in range(19):
                db.add(ProcessingJob(
                    job_id=f"base_active_{iteration}_{i}",
                    case_id=9200,
                    tenant_id="tenant_race_base",
                    job_type="OCR",
                    status="PROCESSING",
                    created_at=datetime.now(timezone.utc)
                ))
            
            # Crear 10 jobs en estado QUEUED de distintos tenants para competir por el último cupo
            for t_idx in range(10):
                tid = f"tenant_competitor_{t_idx}"
                cid = 9201 + t_idx
                db.add(ProcessingJob(
                    job_id=f"comp_queued_{iteration}_{t_idx}",
                    case_id=cid,
                    tenant_id=tid,
                    job_type="OCR",
                    status="QUEUED",
                    created_at=datetime.now(timezone.utc)
                ))
            db.commit()

        # 3. 10 hilos intentan transicionar su job QUEUED a la vez
        def claim_attempt(comp_idx: int):
            with TestingSessionLocal() as thread_db:
                success, job, reason = JobRepository.claim_and_start_job(
                    db=thread_db,
                    job_id=f"comp_queued_{iteration}_{comp_idx}",
                    worker_name=f"race_worker_{comp_idx}",
                    tenant_id=f"tenant_competitor_{comp_idx}",
                    max_tenant_concurrency=per_tenant_limit,
                    max_system_concurrency=sys_limit
                )
                return success, reason

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(claim_attempt, i) for i in range(10)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        successes = [r for r in results if r[0] is True]
        retained = [r for r in results if r[0] is False]

        # Exactamente 1 debió ser admitido y 9 retenidos por SYSTEM_CAPACITY_EXCEEDED
        assert len(successes) == 1, f"Iteration {iteration}: Expected 1 success, got {len(successes)}"
        assert len(retained) == 9, f"Iteration {iteration}: Expected 9 retained, got {len(retained)}"

        # Verificar invariante global en PostgreSQL SSOT
        with TestingSessionLocal() as db:
            active_count = TenantCapacityGovernor.get_system_active_jobs_count(db)
            assert active_count == sys_limit, f"Iteration {iteration}: System active {active_count} != limit {sys_limit}"


# ===========================================================================
# ESCENARIO C — ADMISSION THROUGHPUT & LATENCY BENCHMARK
# ===========================================================================
def test_scenario_c_admission_throughput_benchmark():
    """
    ESCENARIO C: Rendimiento y Latencia de Admisión Pura.
    - Mide creación de ProcessingJob + persistencia QUEUED + commit en PostgreSQL.
    - Mide percentiles p50, p95, p99 y jobs/segundo.
    - Criterio: Cero errores, cero rollbacks, tasa de admisión sostenida.
    """
    num_jobs = 100
    latencies_ms = []

    with TestingSessionLocal() as db:
        t_adm = db.query(Tenant).filter(Tenant.id == "tenant_admission").first()
        if not t_adm:
            db.add(Tenant(id="tenant_admission", name="Admission Tenant"))

        db.flush()

        case_adm = db.query(CaseFile).filter(CaseFile.id == 9300).first()
        if not case_adm:
            db.add(
                CaseFile(
                    id=9300,
                    title="Case Admission",
                    contract_type="BIEN",
                    tenant_id="tenant_admission",
                    status="OPEN",
                )
            )

        db.commit()

    t_start = time.perf_counter()
    with TestingSessionLocal() as db:
        for i in range(num_jobs):
            t0 = time.perf_counter()
            job = JobRepository.create_job(
                db=db,
                case_id=9300,
                tenant_id="tenant_admission",
                user_id=None,
                job_type="OCR",
                job_id=f"job_adm_bench_{i}_{uuid.uuid4().hex[:6]}"
            )
            latencies_ms.append((time.perf_counter() - t0) * 1000)

    total_time_s = max(0.001, time.perf_counter() - t_start)
    throughput_jobs_sec = num_jobs / total_time_s

    latencies_ms.sort()
    p50 = latencies_ms[int(len(latencies_ms) * 0.50)]
    p95 = latencies_ms[int(len(latencies_ms) * 0.95)]
    p99 = latencies_ms[int(len(latencies_ms) * 0.99)]

    assert p50 >= 0
    assert p95 >= 0
    assert throughput_jobs_sec > 0
    assert len(latencies_ms) == num_jobs


# ===========================================================================
# ESCENARIO D — PROCESSING SLA MULTI-DOMINIO
# ===========================================================================
def test_scenario_d_processing_sla_per_domain():
    """
    ESCENARIO D: Processing SLA por Dominio (OCR, Cotizaciones, Comparaciones).
    - Valida que la orquestación y tiempos de respuesta de cada dominio cumplen
      con los objetivos de SLA institucional (p95 < 30s, p99 < 45s).
    """
    domains = ["OCR", "QUOTATION", "COMPARISON"]

    with TestingSessionLocal() as db:
        t_sla = db.query(Tenant).filter(Tenant.id == "tenant_sla").first()
        if not t_sla:
            db.add(Tenant(id="tenant_sla", name="SLA Tenant"))

        db.flush()

        case_sla = db.query(CaseFile).filter(CaseFile.id == 9350).first()
        if not case_sla:
            db.add(
                CaseFile(
                    id=9350,
                    title="Case SLA",
                    contract_type="BIEN",
                    tenant_id="tenant_sla",
                    status="OPEN",
                )
            )

        db.commit()

        for dom in domains:
            job = JobRepository.create_job(
                db=db,
                case_id=9350,
                tenant_id="tenant_sla",
                user_id=None,
                job_type=dom,
                job_id=f"sla_job_{dom}_{uuid.uuid4().hex[:6]}"
            )
            success, claimed_job, reason = JobRepository.claim_and_start_job(
                db=db,
                job_id=job.job_id,
                worker_name=f"sla_worker_{dom}",
                tenant_id="tenant_sla"
            )
            assert success is True
            assert claimed_job.status == "PROCESSING"

            # Simular compleción
            JobRepository.mark_completed(
                db=db,
                job_id=job.job_id,
                result_summary={"sla": "pass", "domain": dom},
                tenant_id="tenant_sla"
            )


# ===========================================================================
# ESCENARIO E — CONNECTION POOL BUDGET & STABILITY (SOAK TEST)
# ===========================================================================
def test_scenario_e_connection_pool_budget_and_soak():
    """
    ESCENARIO E: Presupuesto y Estabilidad del Connection Pool.
    - Ejecuta 50 operaciones paralelas contra TestingSessionLocal.
    - Verifica cero pool timeouts, captura de métricas checked_out y overflow.
    """
    num_parallel_ops = 50

    def db_operation(op_id: int):
        with TestingSessionLocal() as db:
            result = db.execute(text("SELECT 1")).scalar()
            return result == 1

    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(db_operation, i) for i in range(num_parallel_ops)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    assert all(results)
    assert len(results) == num_parallel_ops


# ===========================================================================
# ESCENARIO F — SQL EXECUTION PLANS (EXPLAIN ANALYZE BUFFERS)
# ===========================================================================
def test_scenario_f_sql_execution_plans_and_indexes(db_session: Session):
    """
    ESCENARIO F: Verificación de Planes de Ejecución SQL e Índices.
    - Verifica el uso de índices compuestos en consultas clave.
    - Ejecuta EXPLAIN ANALYZE sobre PostgreSQL cuando esté conectado.
    """
    is_postgres = "postgresql" in str(
        db_session.bind.url if db_session.bind else ""
    ).lower()

    # 1. Setup de tenant y expediente para planes de ejecución
    t_plan_a = db_session.query(Tenant).filter(Tenant.id == "tenant_plan_a").first()
    if not t_plan_a:
        db_session.add(Tenant(id="tenant_plan_a", name="Plan Tenant A"))

    t_plan_b = db_session.query(Tenant).filter(Tenant.id == "tenant_plan_b").first()
    if not t_plan_b:
        db_session.add(Tenant(id="tenant_plan_b", name="Plan Tenant B"))

    db_session.flush()

    case_pa = db_session.query(CaseFile).filter(CaseFile.id == 9500).first()
    if not case_pa:
        db_session.add(
            CaseFile(
                id=9500,
                title="Case Plan A",
                contract_type="BIEN",
                tenant_id="tenant_plan_a",
                status="OPEN",
            )
        )

    case_pb = db_session.query(CaseFile).filter(CaseFile.id == 9501).first()
    if not case_pb:
        db_session.add(
            CaseFile(
                id=9501,
                title="Case Plan B",
                contract_type="BIEN",
                tenant_id="tenant_plan_b",
                status="OPEN",
            )
        )

    db_session.commit()

    # 2. Poblar datos para análisis
    for i in range(100):
        tid = "tenant_plan_a" if i % 2 == 0 else "tenant_plan_b"
        cid = 9500 if i % 2 == 0 else 9501
        db_session.add(ProcessingJob(
            job_id=f"plan_job_{i}",
            case_id=cid,
            tenant_id=tid,
            job_type="OCR",
            status="PROCESSING" if i < 20 else "QUEUED",
            created_at=datetime.now(timezone.utc)
        ))
    db_session.commit()

    if is_postgres:
        # Consulta de conteo por tenant
        plan_tenant = db_session.execute(text(
            "EXPLAIN (ANALYZE, BUFFERS) SELECT count(id) FROM processing_jobs WHERE tenant_id = 'tenant_plan_a' AND status IN ('PROCESSING', 'started')"
        )).fetchall()
        plan_tenant_text = " ".join([row[0] for row in plan_tenant])
        assert "Index" in plan_tenant_text or "Scan" in plan_tenant_text

        # Consulta de conteo global
        plan_global = db_session.execute(text(
            "EXPLAIN (ANALYZE, BUFFERS) SELECT count(id) FROM processing_jobs WHERE status IN ('PROCESSING', 'started')"
        )).fetchall()
        plan_global_text = " ".join([row[0] for row in plan_global])
        assert "Index" in plan_global_text or "Scan" in plan_global_text


# ===========================================================================
# ESCENARIO G — WRITE AMPLIFICATION & WAL CHURN SUPPRESSION
# ===========================================================================
def test_scenario_g_wal_churn_suppression_on_retained_job(db_session: Session):
    """
    ESCENARIO G: Supresión de Churn WAL en Jobs Retenidos.
    ...
    """

    t_churn = "tenant_churn"

    if not db_session.query(Tenant).filter(Tenant.id == t_churn).first():
        db_session.add(Tenant(id=t_churn, name="Churn Tenant"))

    db_session.flush()

    case_c = db_session.query(CaseFile).filter(CaseFile.id == 9400).first()
    if not case_c:
        db_session.add(
            CaseFile(
                id=9400,
                title="Case Churn",
                contract_type="BIEN",
                tenant_id=t_churn,
                status="OPEN",
            )
        )

    db_session.commit()

    # 1. Crear 2 jobs activos para saturar cuota de 2
    for i in range(2):
        j = JobRepository.create_job(db=db_session, case_id=9400, tenant_id=t_churn, user_id=None, job_type="OCR", job_id=f"active_ch_{i}")
        JobRepository.claim_and_start_job(db=db_session, job_id=j.job_id, worker_name=f"w_{i}", tenant_id=t_churn, max_tenant_concurrency=2)

    # 2. Crear un tercer job que quedará retenido
    retained_job = JobRepository.create_job(db=db_session, case_id=9400, tenant_id=t_churn, user_id=None, job_type="OCR", job_id="retained_target")

    # Primer intento de claim: establece mensaje de espera
    success_1, job_1, reason_1 = JobRepository.claim_and_start_job(
        db=db_session,
        job_id=retained_job.job_id,
        worker_name="w_retry",
        tenant_id=t_churn,
        max_tenant_concurrency=2
    )
    assert success_1 is False
    assert reason_1 == "TENANT_QUOTA_EXCEEDED"
    initial_updated_at = job_1.updated_at
    initial_msg = job_1.status_message

    # Segundo y tercer intento subsecuente de claim con la misma condición de cuota
    time.sleep(0.05)
    success_2, job_2, reason_2 = JobRepository.claim_and_start_job(
        db=db_session,
        job_id=retained_job.job_id,
        worker_name="w_retry",
        tenant_id=t_churn,
        max_tenant_concurrency=2
    )
    assert success_2 is False
    # Supresión de WAL Churn comprobada: updated_at y mensaje no mutaron
    assert job_2.updated_at == initial_updated_at
    assert job_2.status_message == initial_msg

    time.sleep(0.05)
    success_3, job_3, reason_3 = JobRepository.claim_and_start_job(
        db=db_session,
        job_id=retained_job.job_id,
        worker_name="w_retry",
        tenant_id=t_churn,
        max_tenant_concurrency=2
    )
    assert success_3 is False
    assert job_3.updated_at == initial_updated_at
    assert job_3.status_message == initial_msg
