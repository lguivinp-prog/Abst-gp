from pydantic import BaseModel, Field, ConfigDict, model_validator
from typing import Optional, List, Dict, Any
from datetime import datetime

class TechnicalReportGenerateRequest(BaseModel):
    template_version: Optional[str] = Field("1.0", description="Versión de la plantilla a utilizar")
    idempotency_key: Optional[str] = Field(None, max_length=128, description="Clave de idempotencia única por solicitud")
    model_config = ConfigDict(extra="forbid")

class TechnicalReportReviewSubmitRequest(BaseModel):
    notes: Optional[str] = Field(None, max_length=1000, description="Notas de remisión a revisión")
    model_config = ConfigDict(extra="forbid")

class TechnicalReportApproveRequest(BaseModel):
    approval_notes: Optional[str] = Field(None, max_length=2000, description="Notas u observaciones de aprobación formal")
    model_config = ConfigDict(extra="forbid")

class TechnicalReportRejectRequest(BaseModel):
    rejection_reason: str = Field(..., min_length=5, max_length=2000, description="Motivación obligatoria y detallada del rechazo")
    model_config = ConfigDict(extra="forbid")

class TechnicalReportResponse(BaseModel):
    id: int
    case_id: int
    template_id: int
    template_version: str
    report_kind: str
    version_number: int
    status: str
    accuracy_gate_result: str
    snapshot_hash: Optional[str] = None
    html_hash: Optional[str] = None
    pdf_hash: Optional[str] = None
    has_pdf: bool = False
    generated_by: Optional[int] = None
    generated_at: Optional[datetime] = None
    approved_by: Optional[int] = None
    approved_at: Optional[datetime] = None
    approval_notes: Optional[str] = None
    rejected_by: Optional[int] = None
    rejected_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None
    idempotency_key: Optional[str] = None
    source_snapshot: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="before")
    @classmethod
    def resolve_computed_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "has_pdf" not in data or data["has_pdf"] is False:
                data["has_pdf"] = bool(data.get("pdf_storage_path") and data.get("pdf_hash"))
            return data
        
        # Objeto ORM
        if hasattr(data, "pdf_storage_path") and hasattr(data, "pdf_hash"):
            path = getattr(data, "pdf_storage_path", None)
            h = getattr(data, "pdf_hash", None)
            calc_has_pdf = bool(path and h)
            # Si el objeto ya tiene propiedad has_pdf, respetarla
            if hasattr(data, "has_pdf"):
                calc_has_pdf = bool(getattr(data, "has_pdf") or calc_has_pdf)
            # Para Pydantic from_attributes, inyectar si es posible
            try:
                object.__setattr__(data, "has_pdf", calc_has_pdf)
            except (TypeError, AttributeError):
                pass
        return data

class TechnicalReportListResponse(BaseModel):
    reports: List[TechnicalReportResponse]
    total: int
    total_reports: Optional[int] = None
    case_id: Optional[int] = None

    @model_validator(mode="before")
    @classmethod
    def align_total(cls, data: Any) -> Any:
        if isinstance(data, dict):
            tot = data.get("total", 0)
            if "total_reports" not in data or data["total_reports"] is None:
                data["total_reports"] = tot
            if "total" not in data or data["total"] is None:
                data["total"] = data.get("total_reports", 0)
        return data

class TechnicalReportIntegrityResponse(BaseModel):
    report_id: int
    status: str
    snapshot_hash_stored: Optional[str] = None
    snapshot_hash_recalculated: Optional[str] = None
    snapshot_intact: bool
    html_hash_stored: Optional[str] = None
    html_hash_recalculated: Optional[str] = None
    html_intact: bool
    pdf_hash_stored: Optional[str] = None
    pdf_hash_recalculated: Optional[str] = None
    pdf_file_exists: bool
    pdf_intact: bool
    is_authentic: bool
    details: Optional[str] = None

    # Campos de compatibilidad directa con cliente React
    snapshot_hash_matches: Optional[bool] = None
    html_hash_matches: Optional[bool] = None
    pdf_hash_matches: Optional[bool] = None
    has_canonical_snapshot: Optional[bool] = None

    @model_validator(mode="before")
    @classmethod
    def harmonize_matches(cls, data: Any) -> Any:
        if isinstance(data, dict):
            snap_ok = bool(data.get("snapshot_intact"))
            html_ok = bool(data.get("html_intact"))
            pdf_ok = bool(data.get("pdf_intact"))
            data.setdefault("snapshot_hash_matches", snap_ok)
            data.setdefault("html_hash_matches", html_ok)
            data.setdefault("pdf_hash_matches", pdf_ok)
            data.setdefault("has_canonical_snapshot", bool(data.get("snapshot_hash_stored")))
        return data
