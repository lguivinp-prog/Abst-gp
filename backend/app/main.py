from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from redis import Redis

from app.core.config import settings
from app.core.database import get_db
from app.api.routers import cases, validation

from app.api.exceptions import setup_exception_handlers

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="API para procesamiento de requerimientos de contratación",
    version="1.0.0"
)

setup_exception_handlers(app)

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

from app.api.routers import auth_router, admin
app.include_router(auth_router.router, prefix="/auth", tags=["auth"])
app.include_router(admin.router, prefix="/admin", tags=["admin"])

@app.get("/")
def read_root():
    return {
        "app": "Abst-gp",
        "status": "running"
    }

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
