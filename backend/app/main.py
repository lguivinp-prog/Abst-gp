from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from redis import Redis

from app.core.config import settings
from app.core.database import get_db
from app.api.routers import cases, validation, v2_upload
from app.api.routers import v6_documents, v6_requirements, v6_suppliers, v6_offers, v6_validations, v6_evaluations, v6_selection, v6_outputs, v6_ai, v6_health, v6_history
from app.api.exceptions import setup_exception_handlers
from app.core.telemetry import OpenTelemetryMiddleware, metrics_registry
from fastapi.responses import Response

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="API para procesamiento de requerimientos de contratación",
    version="1.0.0"
)

setup_exception_handlers(app)

@app.on_event("startup")
def startup_orphan_reconciliation():
    """
    R3-09: Reconciliación automática integrada en el ciclo de vida de la aplicación.
    Limpia archivos temporales huérfanos y artefactos no referenciados de manera durable.
    """
    try:
        import os
        from app.core.database import SessionLocal
        from app.services.v6.reporting.pdf_report_generator import PdfReportGenerator
        db = SessionLocal()
        try:
            reports_root = os.path.join(settings.UPLOADS_DIR, "reports")
            if os.path.exists(reports_root):
                PdfReportGenerator.reconcile_all_orphans(db, reports_root, max_age_seconds=3600)
        finally:
            db.close()
    except Exception:
        import logging
        logging.getLogger("app.p13.reconciliation").exception(
            "P13: falló la reconciliación de archivos; intervención operativa requerida"
        )


@app.on_event("startup")
def startup_security_alert_dispatcher():
    """
    R4-05, R5-06: Valida preflight del canal de alertas e inicia el despachador autónomo supervisado.
    En entorno LAN o producción, el canal debe ser un transporte remoto verificado (webhook o telegram).
    """
    import logging
    startup_logger = logging.getLogger("app.security.startup")
    try:
        from app.services.security.intrusion_service import validate_alert_channel_readiness, start_alert_dispatcher_service
        readiness = validate_alert_channel_readiness()
        if not readiness.get("ready"):
            app_env = getattr(settings, "APP_ENV", "development").lower()
            msg = f"Canal de alertas no preparado para produccion/LAN (R5-06): {readiness.get('reason')}"
            startup_logger.error(msg)
            if app_env in ("lan", "production", "prod"):
                raise RuntimeError(f"Preflight de seguridad LAN fallido (R5-06): {readiness.get('reason')}")
        start_alert_dispatcher_service(interval_seconds=3.0)
    except Exception as e:
        startup_logger.error(f"Fallo en preflight o inicio del despachador de alertas: {e}")
        if getattr(settings, "APP_ENV", "development").lower() in ("lan", "production", "prod"):
            raise


@app.on_event("startup")
def startup_verify_database_quarantine():
    """
    B1-03: Bloqueo operativo transversal si la base de datos se encuentra en cuarentena
    por una restauracion DR previa inconsistente o fallida (_dr_restoration_quarantine detectada).
    Impide que la instalacion opere o sea presentada como operativa.
    """
    import logging
    startup_logger = logging.getLogger("app.quarantine.startup")
    try:
        from sqlalchemy import text
        from app.core.database import SessionLocal
        db = SessionLocal()
        try:
            if db.bind and getattr(db.bind.dialect, "name", "") == "postgresql":
                has_table = db.execute(text("SELECT to_regclass('public._dr_restoration_quarantine')")).scalar()
                if has_table:
                    quarantine = db.execute(text(
                        "SELECT reason FROM _dr_restoration_quarantine ORDER BY id DESC LIMIT 1"
                    )).first()
                    if quarantine:
                        reason = quarantine[0]
                        msg = (
                            f"BLOQUEO OPERATIVO TRANSVERSAL POR CUARENTENA DR (B1-03): "
                            f"La base de datos se encuentra en cuarentena estricta (_dr_restoration_quarantine activa). "
                            f"Causa: {reason}. Los servicios operativos quedan inhabilitados."
                        )
                        startup_logger.critical(msg)
                        raise RuntimeError(msg)
        finally:
            db.close()
    except RuntimeError:
        raise
    except Exception as e:
        msg = f"BLOQUEO OPERATIVO TRANSVERSAL POR CUARENTENA DR (B1-FAIL-CLOSED): Fallo en preflight de cuarentena: {e}"
        startup_logger.critical(msg)
        raise RuntimeError(msg) from e


@app.on_event("shutdown")
def shutdown_security_alert_dispatcher():
    """
    R4-05: Detiene el despachador de alertas de seguridad limpiamente.
    """
    try:
        from app.services.security.intrusion_service import stop_alert_dispatcher_service
        stop_alert_dispatcher_service()
    except Exception:
        pass

# Telemetría OpenTelemetry y Prometheus
app.add_middleware(OpenTelemetryMiddleware)

# CORS config
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Cambiar a orígenes específicos en producción
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(cases.router, prefix="/cases", tags=["cases"])
app.include_router(validation.router, prefix="/validation", tags=["validation"])
app.include_router(v2_upload.router)

# Mount API V6
app.include_router(v6_documents.router, prefix="/api/v6", tags=["v6_documents"])
app.include_router(v6_requirements.router, prefix="/api/v6", tags=["v6_requirements"])
app.include_router(v6_suppliers.router, prefix="/api/v6", tags=["v6_suppliers"])
app.include_router(v6_offers.router, prefix="/api/v6", tags=["v6_offers"])
app.include_router(v6_validations.router, prefix="/api/v6", tags=["v6_validations"])
app.include_router(v6_evaluations.router, prefix="/api/v6", tags=["v6_evaluations"])
app.include_router(v6_selection.router, prefix="/api/v6", tags=["v6_selection"])
app.include_router(v6_history.router, prefix="/api/v6", tags=["v6_history"])
app.include_router(v6_outputs.router, prefix="/api/v6", tags=["v6_outputs"])
app.include_router(v6_ai.router, prefix="/api/v6", tags=["v6_ai"])
app.include_router(v6_health.router, prefix="/api/v6", tags=["v6_health"])

from app.api.routers import auth_router, admin, pilot
app.include_router(auth_router.router, prefix="/auth", tags=["auth"])
app.include_router(admin.router, prefix="/admin", tags=["admin"])
app.include_router(pilot.router, prefix="/api/pilot", tags=["pilot"])

from sqlalchemy import text

@app.get("/health")
def read_health(db: Session = Depends(get_db)):
    health_status = {"api": "ok", "db": "error", "redis": "error"}
    
    # Check DB
    try:
        db.execute(text("SELECT 1"))
        health_status["db"] = "ok"
    except Exception:
        pass
        
    # Check Redis
    try:
        redis_client = Redis.from_url(settings.REDIS_URL)
        if redis_client.ping():
            health_status["redis"] = "ok"
    except Exception:
        pass
        
    return health_status


@app.get("/metrics", tags=["sre"])
def get_prometheus_metrics():
    """
    Endpoint de scraping para Prometheus / Grafana.
    Retorna métricas técnicas y de negocio en formato estándar OpenMetrics (text/plain).
    """
    metrics_text = metrics_registry.generate_latest()
    return Response(
        content=metrics_text,
        media_type="text/plain; version=0.0.4; charset=utf-8"
    )

from fastapi.staticfiles import StaticFiles
import os

static_dir = os.path.join(os.path.dirname(__file__), "static")
app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
