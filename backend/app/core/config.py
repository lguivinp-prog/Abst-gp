from pydantic_settings import BaseSettings
import os

class Settings(BaseSettings):
    PROJECT_NAME: str = "Abst-gp"
    API_V1_STR: str = "/api/v1"
    
    SECRET_KEY: str = os.getenv("SECRET_KEY", "supersecretkey_change_in_production")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480
    
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://abst_user:abst_password@localhost:5432/abst_gp")
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    
    UPLOADS_DIR: str = os.getenv("UPLOADS_DIR", "./data/uploads")
    
    # OCR Engine Configuration
    OCR_ENGINE: str = os.getenv("OCR_ENGINE", "v1")
    OCR_SHADOW_MODE: bool = os.getenv("OCR_SHADOW_MODE", "false").lower() == "true"
    OCR_REVIEW_THRESHOLD: float = float(os.getenv("OCR_REVIEW_THRESHOLD", "0.85"))

    class Config:
        case_sensitive = True

settings = Settings()
