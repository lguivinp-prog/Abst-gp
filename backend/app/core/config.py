from pydantic_settings import BaseSettings
import os

class Settings(BaseSettings):
    PROJECT_NAME: str = "Abst-gp"
    API_V1_STR: str = "/api/v1"
    
    SECRET_KEY: str = os.getenv("SECRET_KEY", "supersecretkey_change_in_production")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
    
    # P14 Hardening & MFA Configuration
    MFA_ENCRYPTION_KEY: str = os.getenv("MFA_ENCRYPTION_KEY", "deterministic_test_mfa_key_32b_!")
    BACKUP_ENCRYPTION_KEY: str = os.getenv("BACKUP_ENCRYPTION_KEY", "test_backup_enc_key_32bytes_!!")
    BACKUP_SIGNING_KEY: str = os.getenv("BACKUP_SIGNING_KEY", "test_backup_sign_key_32bytes_!!")
    MFA_CHALLENGE_EXPIRE_MINUTES: int = int(os.getenv("MFA_CHALLENGE_EXPIRE_MINUTES", "3"))
    RATE_LIMIT_LOGIN_MAX: int = int(os.getenv("RATE_LIMIT_LOGIN_MAX", "10"))
    RATE_LIMIT_LOGIN_WINDOW_SECONDS: int = int(os.getenv("RATE_LIMIT_LOGIN_WINDOW_SECONDS", "300"))
    TRUSTED_PROXIES: str = os.getenv("TRUSTED_PROXIES", "127.0.0.1,::1")
    ALERT_CHANNEL: str = os.getenv("ALERT_CHANNEL", "console") # console, email, telegram, mock, webhook
    ALERT_WEBHOOK_URL: str = os.getenv("ALERT_WEBHOOK_URL", "")
    ALERT_TELEGRAM_BOT_TOKEN: str = os.getenv("ALERT_TELEGRAM_BOT_TOKEN", "")
    ALERT_TELEGRAM_CHAT_ID: str = os.getenv("ALERT_TELEGRAM_CHAT_ID", "")
    
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

    # AI Provider Configuration (V6)
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    AI_PROVIDER: str = os.getenv("AI_PROVIDER", "auto") # auto, openai, anthropic, mock, none

    class Config:
        case_sensitive = True

settings = Settings()

if settings.APP_ENV in ("lan", "production"):
    from app.core.crypto import validate_and_parse_key
    if settings.SECRET_KEY in ("supersecretkey_change_in_production", "default_secret_key") or len(settings.SECRET_KEY) < 32:
        raise RuntimeError("FATAL: Insecure or short SECRET_KEY detected in production/lan environment.")
    if settings.MFA_ENCRYPTION_KEY == "deterministic_test_mfa_key_32b_!":
        raise RuntimeError("FATAL: Insecure MFA_ENCRYPTION_KEY detected in production/lan environment.")
    if settings.BACKUP_ENCRYPTION_KEY == "test_backup_enc_key_32bytes_!!":
        raise RuntimeError("FATAL: Insecure BACKUP_ENCRYPTION_KEY detected in production/lan environment.")
    if settings.BACKUP_SIGNING_KEY == "test_backup_sign_key_32bytes_!!":
        raise RuntimeError("FATAL: Insecure BACKUP_SIGNING_KEY detected in production/lan environment.")

    # Validar entropia y longitud exacta sin defaults (P14-R2-14)
    validate_and_parse_key(settings.MFA_ENCRYPTION_KEY, "MFA_ENCRYPTION_KEY", allow_test_defaults=False)
    validate_and_parse_key(settings.BACKUP_ENCRYPTION_KEY, "BACKUP_ENCRYPTION_KEY", allow_test_defaults=False)
    validate_and_parse_key(settings.BACKUP_SIGNING_KEY, "BACKUP_SIGNING_KEY", allow_test_defaults=False)

    val_key = os.getenv("VALIDATION_API_KEY", "")
    if val_key == "supersecret_validation_token" or not val_key:
        raise RuntimeError("FATAL: Insecure or missing VALIDATION_API_KEY detected in production/lan environment.")

    # Validar canal de alertas en entorno LAN/produccion (R4-05)
    if settings.ALERT_CHANNEL in ("console", "mock", "test_sink"):
        import logging
        logging.getLogger("app.security.config").warning(
            f"ADVERTENCIA DE SEGURIDAD (R4-05): ALERT_CHANNEL={settings.ALERT_CHANNEL} no constituye un transporte "
            f"externo fuera de banda verificado. En entorno LAN/produccion se requiere 'webhook' o 'telegram' para "
            f"notificaciones efectivas al propietario."
        )
    elif settings.ALERT_CHANNEL == "webhook" and not settings.ALERT_WEBHOOK_URL:
        raise RuntimeError("FATAL (R4-05): ALERT_CHANNEL=webhook configurado pero ALERT_WEBHOOK_URL esta vacia.")
    elif settings.ALERT_CHANNEL == "telegram" and (not settings.ALERT_TELEGRAM_BOT_TOKEN or not settings.ALERT_TELEGRAM_CHAT_ID):
        raise RuntimeError("FATAL (R4-05): ALERT_CHANNEL=telegram configurado pero falta ALERT_TELEGRAM_BOT_TOKEN o ALERT_TELEGRAM_CHAT_ID.")

