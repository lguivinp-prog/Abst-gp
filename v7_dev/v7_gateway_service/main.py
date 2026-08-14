from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import PlainTextResponse
from api.routes import router
from prometheus_client import Counter, Histogram, Gauge, generate_latest
from api.business import router as business_router
import time

app = FastAPI(title="Abast-gp Secure Gateway V7 Alpha")

# Metrics
LATENCY = Histogram('v7_gateway_latency_ms', 'Request latency in milliseconds')
BLOCK_TOTAL = Counter('v7_gateway_block_total', 'Total blocked requests')
QUARANTINE_TOTAL = Counter('v7_gateway_quarantine_total', 'Total quarantined requests')
ERROR_TOTAL = Counter('v7_gateway_errors_total', 'Total internal errors')
PII_DETECTED = Counter('v7_gateway_pii_detected_total', 'Total PII elements detected')

# Migration Metrics
ENGINE_SWITCH = Counter('v7_vector_engine_switch_total', 'Total times the vector engine state changed')
DUAL_READ_DIFF = Counter('v7_dual_read_difference_total', 'Total differences detected in Dual Read mode')
BACKFILL_PROGRESS = Counter('v7_backfill_progress_total', 'Backfill items processed')
MIGRATION_ERRORS = Counter('v7_migration_errors_total', 'Errors during migration operations')
SHADOW_DROPPED = Counter('v7_shadow_dropped_total', 'Dropped shadow evaluation logs due to full queue')
SHADOW_DROP_RATE = Gauge('v7_shadow_drop_rate', 'Rate of dropped shadow evaluation logs per minute')

@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    start_time = time.time()
    try:
        response = await call_next(request)
        
        # Simple tracking logic based on response logic (can be refined)
        # We would typically hook into the actual policy decision inside the route,
        # but for demonstration we can just let the route handle returning the status.
        return response
    except Exception as e:
        ERROR_TOTAL.inc()
        raise e
    finally:
        process_time = (time.time() - start_time) * 1000
        LATENCY.observe(process_time)

@app.get("/metrics")
def metrics():
    return PlainTextResponse(generate_latest())

app.include_router(router)
app.include_router(business_router)
