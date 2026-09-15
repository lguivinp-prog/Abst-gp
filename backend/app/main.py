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
