from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from prometheus_client import Counter, Histogram, generate_latest
import time

app = FastAPI(title="Abast-gp Vector Service V7 Alpha")

LATENCY = Histogram('v7_vector_search_latency_ms', 'Vector Search latency in ms')
INDEX_TOTAL = Counter('v7_vector_index_total', 'Total vectors indexed')
ERRORS_TOTAL = Counter('v7_vector_errors_total', 'Total errors')
RLS_DENIED_TOTAL = Counter('v7_vector_rls_denied_total', 'Total RLS Denied attempts')

@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = (time.time() - start_time) * 1000
    if request.url.path == "/v7/vector/search":
        LATENCY.observe(process_time)
    return response

@app.get("/metrics")
def metrics():
    return PlainTextResponse(generate_latest())

# We import router after defining metrics to avoid circular imports
from api.routes import router
app.include_router(router)

@app.on_event("startup")
def startup_event():
    from repositories.pgvector_repo import vector_repo
    vector_repo.setup_database()
