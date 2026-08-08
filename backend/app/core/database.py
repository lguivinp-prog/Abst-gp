from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from app.core.config import settings
from app.core.telemetry import record_db_pool_metrics

engine_kwargs = {
    "pool_pre_ping": True,
}
if "sqlite" not in settings.DATABASE_URL.lower():
    engine_kwargs.update({
        "pool_size": settings.DB_POOL_SIZE,
        "max_overflow": settings.DB_MAX_OVERFLOW,
        "pool_timeout": settings.DB_POOL_TIMEOUT,
        "pool_recycle": settings.DB_POOL_RECYCLE,
    })

engine = create_engine(settings.DATABASE_URL, **engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Instrumentación no intrusiva de eventos del Pool de SQLAlchemy para métricas Prometheus
try:
    @event.listens_for(engine, "checkout")
    def on_db_checkout(dbapi_connection, connection_record, connection_proxy):
        try:
            checked_out = engine.pool.checkedout() if hasattr(engine.pool, "checkedout") else 0
            overflow = engine.pool.overflow() if hasattr(engine.pool, "overflow") else 0
            record_db_pool_metrics(checked_out=checked_out, overflow=overflow)
        except Exception:
            pass

    @event.listens_for(engine, "checkin")
    def on_db_checkin(dbapi_connection, connection_record):
        try:
            checked_out = engine.pool.checkedout() if hasattr(engine.pool, "checkedout") else 0
            overflow = engine.pool.overflow() if hasattr(engine.pool, "overflow") else 0
            record_db_pool_metrics(checked_out=checked_out, overflow=overflow)
        except Exception:
            pass
except Exception:
    pass

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

