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

    @event.listens_for(engine, "checkout")
    def verify_quarantine_on_checkout(dbapi_connection, connection_record, connection_proxy):
        # B1-03: Extension de bloqueo operativo a cualquier proceso/worker que obtenga conexiones del pool
        if getattr(engine.dialect, "name", "") != "postgresql":
            return
        try:
            cursor = dbapi_connection.cursor()
            try:
                cursor.execute("SELECT to_regclass('public._dr_restoration_quarantine');")
                row = cursor.fetchone()
                if row and row[0]:
                    cursor.execute("SELECT reason FROM _dr_restoration_quarantine LIMIT 1;")
                    q = cursor.fetchone()
                    if q and q[0]:
                        raise RuntimeError(
                            f"BLOQUEO OPERATIVO POR CUARENTENA DR (B1-03): Acceso denegado. Base de datos en cuarentena: {q[0]}"
                        )
            except RuntimeError:
                raise
            except Exception as e:
                # B1-FAIL-CLOSED: En PostgreSQL, cualquier fallo al inspeccionar cuarentena deniega la conexion
                raise RuntimeError(
                    f"Fallo critico en verificacion de cuarentena DR en checkout de pool (B1-FAIL-CLOSED): {e}"
                ) from e
            finally:
                cursor.close()
        except RuntimeError:
            raise
except Exception:
    pass

from sqlalchemy import text

def get_db():
    db = SessionLocal()
    try:
        # B1-03 / B1-FAIL-CLOSED: Bloqueo operativo transversal si la base de datos esta en cuarentena
        try:
            if db.bind and getattr(db.bind.dialect, "name", "") == "postgresql":
                has_table = db.execute(text("SELECT to_regclass('public._dr_restoration_quarantine')")).scalar()
                if has_table:
                    q_row = db.execute(text("SELECT reason FROM _dr_restoration_quarantine LIMIT 1")).scalar()
                    if q_row:
                        raise RuntimeError(
                            f"BLOQUEO OPERATIVO POR CUARENTENA DR (B1-03): Acceso denegado. Base de datos en cuarentena: {q_row}"
                        )
        except RuntimeError:
            raise
        except Exception as e:
            # B1-FAIL-CLOSED: Ante cualquier error al verificar cuarentena (ej. PermissionError), denegar acceso inmediatamente
            raise RuntimeError(f"Fallo critico en verificacion de cuarentena DR (B1-FAIL-CLOSED): {e}") from e
        yield db
    finally:
        db.close()

