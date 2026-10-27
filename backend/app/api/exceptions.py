from fastapi import Request
from fastapi.responses import JSONResponse
import logging

logger = logging.getLogger(__name__)

# Base Domain Exception
class DomainException(Exception):
    def __init__(self, message: str, code: str = "INTERNAL_ERROR", status_code: int = 500):
        self.message = message
        self.code = code
        self.status_code = status_code
        super().__init__(self.message)

class NotFoundException(DomainException):
    def __init__(self, message: str):
        super().__init__(message, code="NOT_FOUND", status_code=404)

class ForbiddenException(DomainException):
    def __init__(self, message: str):
        super().__init__(message, code="FORBIDDEN", status_code=403)

class UnauthorizedException(DomainException):
    def __init__(self, message: str):
        super().__init__(message, code="UNAUTHORIZED", status_code=401)

class ValidationException(DomainException):
    def __init__(self, message: str):
        super().__init__(message, code="VALIDATION_ERROR", status_code=400)

class ConflictException(DomainException):
    def __init__(self, message: str):
        super().__init__(message, code="CONFLICT", status_code=409)

async def domain_exception_handler(request: Request, exc: DomainException):
    # Retrieve request ID if set by middleware, otherwise generate one or leave empty
    request_id = getattr(request.state, "request_id", "unknown")
    
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "request_id": request_id
            }
        }
    )

async def generic_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled server error: {exc}", exc_info=True)
    request_id = getattr(request.state, "request_id", "unknown")
    
    msg = str(exc)
    if "BLOQUEO OPERATIVO POR CUARENTENA DR" in msg or "B1-FAIL-CLOSED" in msg or "cuarentena" in msg.lower():
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "code": "SERVICE_UNAVAILABLE",
                    "message": "Servicio no disponible: Base de datos en cuarentena DR o fallo en inspeccion (B1-FAIL-CLOSED).",
                    "detail": msg,
                    "request_id": request_id
                }
            }
        )
    if "Fallo de control de escrituras (B2)" in msg or "congelamiento activo de documentos" in msg.lower():
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "code": "SERVICE_UNAVAILABLE",
                    "message": "Fallo de control de escrituras (B2): Respaldo LAN en curso. Congelamiento activo de documentos.",
                    "detail": msg,
                    "request_id": request_id
                }
            }
        )

    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "An unexpected error occurred.",
                "request_id": request_id
            }
        }
    )

def setup_exception_handlers(app):
    app.add_exception_handler(DomainException, domain_exception_handler)
    app.add_exception_handler(Exception, generic_exception_handler)
