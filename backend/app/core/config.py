from pydantic_settings import BaseSettings
import os

class Settings(BaseSettings):
    PROJECT_NAME: str = "Abst-gp"
    API_V1_STR: str = "/api/v1"
    
    SECRET_KEY: str = os.getenv("SECRET_KEY", "supersecretkey_change_in_production")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480
    
    DATABASE_URL: str = os.environ["DATABASE_URL"]
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    
    APP_ENV: str = os.getenv('APP_ENV', 'development')
    UPLOADS_DIR: str = os.getenv("UPLOADS_DIR", "./data/uploads")
    STORAGE_BACKEND: str = os.getenv("STORAGE_BACKEND", "local")
    
    # Object Storage Configuration (V6)
    S3_ENDPOINT_URL: str = os.getenv("S3_ENDPOINT_URL", "http://minio:9000")
    S3_ACCESS_KEY: str = os.getenv("S3_ACCESS_KEY", "minioadmin")
    S3_SECRET_KEY: str = os.getenv("S3_SECRET_KEY", "minioadmin123")
    S3_BUCKET_NAME: str = os.getenv("S3_BUCKET_NAME", "abst-documents")
    DOCUMENT_UPLOAD_MODE: str = os.getenv("DOCUMENT_UPLOAD_MODE", "legacy")
    
    # OCR Engine Configuration
    OCR_ENGINE: str = os.getenv("OCR_ENGINE", "v1")
    OCR_SHADOW_MODE: bool = os.getenv("OCR_SHADOW_MODE", "false").lower() == "true"
    OCR_REVIEW_THRESHOLD: float = float(os.getenv("OCR_REVIEW_THRESHOLD", "0.85"))

    # Feature Flags V5.3 (Async Processing & Domain Workers)
    FEATURE_ASYNC_PROCESSING: bool = os.getenv("FEATURE_ASYNC_PROCESSING", "false").lower() == "true"
    FEATURE_ASYNC_QUOTATION: bool = os.getenv("FEATURE_ASYNC_QUOTATION", "false").lower() == "true"
    FEATURE_ASYNC_COMPARISON: bool = os.getenv("FEATURE_ASYNC_COMPARISON", "false").lower() == "true"

    def is_async_quotation_enabled(self) -> bool:
        return self.FEATURE_ASYNC_PROCESSING or self.FEATURE_ASYNC_QUOTATION

    def is_async_comparison_enabled(self) -> bool:
        return self.FEATURE_ASYNC_PROCESSING or self.FEATURE_ASYNC_COMPARISON

    # Database Connection Pool Configuration (Fase 7.3)
    DB_POOL_SIZE: int = int(os.getenv("DB_POOL_SIZE", "20"))
    DB_MAX_OVERFLOW: int = int(os.getenv("DB_MAX_OVERFLOW", "10"))
    DB_POOL_TIMEOUT: int = int(os.getenv("DB_POOL_TIMEOUT", "30"))
    DB_POOL_RECYCLE: int = int(os.getenv("DB_POOL_RECYCLE", "1800"))

    # Tenant Capacity Governance (Fase 7.3)
    TENANT_MAX_CONCURRENT_PROCESSING_JOBS: int = int(os.getenv("TENANT_MAX_CONCURRENT_PROCESSING_JOBS", "5"))
    SYSTEM_MAX_CONCURRENT_PROCESSING_JOBS: int = int(os.getenv("SYSTEM_MAX_CONCURRENT_PROCESSING_JOBS", "20"))
    CAPACITY_GOVERNOR_ENABLED: bool = os.getenv("CAPACITY_GOVERNOR_ENABLED", "true").lower() == "true"

    class Config:
        case_sensitive = True

settings = Settings()

