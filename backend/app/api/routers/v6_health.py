from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.core.database import get_db

router = APIRouter()

@router.get("/health")
def health_check(db: Session = Depends(get_db)):
    """
    V6 Health Monitoring Endpoint
    Validates API and Database connectivity.
    """
    status = {
        "api": "ok",
        "database": "unknown"
    }
    
    try:
        # Ping DB
        db.execute(text("SELECT 1"))
        status["database"] = "ok"
    except Exception as e:
        status["database"] = f"error: {str(e)}"
        
    # In a full environment, Redis and Worker status would be pinged here
    status["redis"] = "ok (mock)"
    status["workers"] = "ok (mock)"
    
    return status
