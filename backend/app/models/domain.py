from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, Float, JSON, CheckConstraint, Index, UniqueConstraint, PrimaryKeyConstraint, text, Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
import enum
from app.models.base import Base

from sqlalchemy import event
from sqlalchemy.orm import Session

class ValidationDocumentCase(Base):
    __tablename__ = "validation_document_cases"
    
    case_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    validation_run_id = Column(UUID(as_uuid=True), nullable=False)
    uploaded_document_id = Column(Integer, ForeignKey("uploaded_documents.id", ondelete="RESTRICT", name="fk_validation_case_uploaded_document"), nullable=False)
    
    # Checksum of the PDF content. Same length as SHA-256 hex string.
    pdf_sha256 = Column(String(64), nullable=False)
    
    # Request idempotency derived from SHA256(validation_run_id + ":" + pdf_sha256)
    request_idempotency_key = Column(String(64), unique=True, nullable=False)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint('validation_run_id', 'pdf_sha256', name='uq_validation_case_run_sha'),
        UniqueConstraint('request_idempotency_key', name='uq_validation_case_request_idempotency_key'),
        CheckConstraint("pdf_sha256 ~ '^[0-9a-f]{64}$'", name="check_pdf_sha256_format"),
        CheckConstraint("request_idempotency_key ~ '^[0-9a-f]{64}$'", name="check_request_idempotency_key_format"),
        PrimaryKeyConstraint('case_id', name='pk_validation_document_cases')
    )

class OCRProcessingRun(Base):
    __tablename__ = "ocr_processing_runs"
    
    run_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    uploaded_document_id = Column(Integer, ForeignKey("uploaded_documents.id", ondelete="RESTRICT", name="fk_ocr_run_uploaded_document"), nullable=False)
    validation_case_id = Column(UUID(as_uuid=True), ForeignKey("validation_document_cases.case_id", ondelete="RESTRICT", name="fk_ocr_run_validation_case"), nullable=True, index=True)
    processing_job_id = Column(Integer, ForeignKey("processing_jobs.id", ondelete="RESTRICT", name="fk_ocr_run_processing_job"), nullable=True, index=True)
    execution_role = Column(String, nullable=False)
    engine = Column(String, nullable=False)
    status = Column(String, index=True, nullable=False)
    quality_status = Column(String, nullable=True)
    attempt_number = Column(Integer, nullable=False, default=1)
    dispatch_attempt_count = Column(Integer, nullable=False, default=0)
    worker_attempt_count = Column(Integer, nullable=False, default=0)
    dispatch_owner = Column(String, nullable=True)
    dispatch_token = Column(UUID(as_uuid=True), nullable=True)
    dispatch_claimed_at = Column(DateTime(timezone=True), nullable=True)
    dispatch_lease_expires_at = Column(DateTime(timezone=True), nullable=True)
    run_dedup_key = Column(String(64), nullable=False)
    source_run_id = Column(UUID(as_uuid=True), ForeignKey("ocr_processing_runs.run_id", ondelete="RESTRICT", name="fk_ocr_run_source"), nullable=True, index=True)
    rq_job_id = Column(String, nullable=True)
    score = Column(Float, nullable=True)
    review_threshold = Column(Float, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    heartbeat_at = Column(DateTime(timezone=True), nullable=True)
    last_dispatch_attempt_at = Column(DateTime(timezone=True), nullable=True)
    failure_code = Column(String, nullable=True)
    failure_detail = Column(Text, nullable=True)
    last_dispatch_error = Column(Text, nullable=True)
    structured_document_path = Column(String, nullable=True)
    structured_document_checksum = Column(String(64), nullable=True)
    metadata_ = Column("metadata", JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        PrimaryKeyConstraint('run_id', name='pk_ocr_processing_runs'),
        UniqueConstraint('run_dedup_key', name='uq_ocr_run_dedup_key'),
        Index("ix_ocr_run_rq_job_id", "rq_job_id", unique=True, postgresql_where=text("rq_job_id IS NOT NULL")),
        Index("ix_ocr_run_source_fallback", "source_run_id", unique=True, postgresql_where=text("execution_role = 'FALLBACK'")),
        Index("ix_ocr_run_doc_role_created", "uploaded_document_id", "execution_role", "created_at"),
        Index("ix_ocr_run_pending_dispatch", "status", "created_at", postgresql_where=text("status IN ('PENDING_DISPATCH', 'DISPATCHING')")),
        
        CheckConstraint("engine IN ('v1', 'v2')", name="check_engine"),
        CheckConstraint("execution_role IN ('PRIMARY', 'SHADOW', 'FALLBACK')", name="check_execution_role"),
        CheckConstraint("status IN ('PENDING_DISPATCH', 'DISPATCHING', 'QUEUED', 'RUNNING', 'COMPLETED', 'FAILED')", name="check_status"),
        CheckConstraint("quality_status IN ('APPROVED', 'REVIEW_REQUIRED')", name="check_quality_status_values"),
        CheckConstraint(
            "(status IN ('PENDING_DISPATCH', 'DISPATCHING', 'QUEUED', 'RUNNING', 'FAILED') AND quality_status IS NULL) OR "
            "(status = 'COMPLETED' AND quality_status IS NOT NULL AND quality_status IN ('APPROVED', 'REVIEW_REQUIRED'))",
            name="check_status_quality_relation"
        ),
        CheckConstraint("attempt_number >= 1", name="check_attempt_number"),
        CheckConstraint("dispatch_attempt_count >= 0", name="check_dispatch_attempt_count"),
        CheckConstraint("worker_attempt_count >= 0", name="check_worker_attempt_count"),
        CheckConstraint("score IS NULL OR (score >= 0.0 AND score <= 1.0)", name="check_score_range"),
        CheckConstraint("review_threshold IS NULL OR (review_threshold >= 0.0 AND review_threshold <= 1.0)", name="check_review_threshold_range"),
        CheckConstraint("run_dedup_key ~ '^[0-9a-f]{64}$'", name="check_run_dedup_key_format"),
        CheckConstraint("structured_document_checksum IS NULL OR structured_document_checksum ~ '^[0-9a-f]{64}$'", name="check_structured_document_checksum_format"),
        CheckConstraint("finished_at IS NULL OR started_at IS NULL OR finished_at >= started_at", name="check_time_order"),
        CheckConstraint(
            "(status IN ('PENDING_DISPATCH', 'DISPATCHING') AND started_at IS NULL AND finished_at IS NULL) OR "
            "(status = 'QUEUED' AND started_at IS NULL AND finished_at IS NULL) OR "
            "(status = 'RUNNING' AND started_at IS NOT NULL AND finished_at IS NULL) OR "
            "(status = 'COMPLETED' AND started_at IS NOT NULL AND finished_at IS NOT NULL AND failure_code IS NULL) OR "
            "(status = 'FAILED' AND finished_at IS NOT NULL AND failure_code IS NOT NULL)",
            name="check_status_lifecycle"
        ),
        CheckConstraint(
            "(execution_role = 'PRIMARY' AND source_run_id IS NULL) OR "
            "(execution_role = 'SHADOW' AND source_run_id IS NOT NULL AND engine = 'v2') OR "
            "(execution_role = 'FALLBACK' AND source_run_id IS NOT NULL AND engine = 'v1')",
            name="check_role_engine_source"
        ),
        CheckConstraint(
            "(validation_case_id IS NOT NULL AND processing_job_id IS NULL) OR "
            "(validation_case_id IS NULL AND processing_job_id IS NOT NULL)",
            name="check_exclusive_scope"
        ),
        CheckConstraint(
            "source_run_id IS NULL OR source_run_id <> run_id",
            name="check_no_immediate_circular_reference"
        )
    )


class Tenant(Base):
    __tablename__ = "tenants"
    id = Column(String(50), primary_key=True)
    name = Column(String(100), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String(50), ForeignKey("tenants.id", onupdate="RESTRICT", ondelete="RESTRICT"), nullable=True)
    tenant_resolution_status = Column(String(50), nullable=False, default="RESOLVED")
    username = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False, default="readonly") # admin, operator, readonly
    is_active = Column(Boolean, default=True, nullable=False)
    must_change_password = Column(Boolean, default=False, nullable=False)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    last_login_at = Column(DateTime(timezone=True), nullable=True)
    failed_login_count = Column(Integer, default=0, nullable=False)
    locked_until = Column(DateTime(timezone=True), nullable=True)
    password_changed_at = Column(DateTime(timezone=True), nullable=True)
    quarantined_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint(
            "(role = 'ADMIN' AND tenant_id IS NULL AND tenant_resolution_status = 'RESOLVED') OR (role != 'ADMIN' AND tenant_id IS NOT NULL)",
            name="chk_users_tenant_resolution"
        ),
    )

class UserTenantQuarantine(Base):
    __tablename__ = "user_tenant_quarantine"
    user_id = Column(Integer, ForeignKey("users.id", onupdate="CASCADE", ondelete="CASCADE"), primary_key=True)
    reason_code = Column(String, nullable=False)
    evidence_reviewed = Column(JSONB, nullable=True)
    status = Column(String, nullable=False, default="QUARANTINED")
    proposed_tenant_id = Column(String(50), ForeignKey("tenants.id"), nullable=True)
    quarantined_at = Column(DateTime(timezone=True), server_default=func.now())
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolution_reference = Column(String, nullable=True)


class SystemSettings(Base):
    __tablename__ = "system_settings"
    id = Column(Integer, primary_key=True, index=True)
    institution_name = Column(String, nullable=True)
    logo_path = Column(String, nullable=True)
    storage_path = Column(String, nullable=True)
    max_file_size = Column(Integer, default=10485760) # 10MB
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    active_ring = Column(Integer, nullable=False, default=0)

    __table_args__ = (
        CheckConstraint("active_ring >= 0", name="check_active_ring_non_negative"),
    )

class CaseFile(Base):
    __tablename__ = "case_files"
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String(50), ForeignKey("tenants.id", onupdate="RESTRICT", ondelete="RESTRICT"), server_default="mega_tenant", nullable=True)
    title = Column(String, nullable=False)
    contract_type = Column(String, nullable=False)
    siga_number = Column(String, nullable=True)
    office_unit = Column(String, nullable=True)
    status = Column(String(50), default="CREATED", nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"))
    assigned_to_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    assigned_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    assigned_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    documents = relationship("UploadedDocument", back_populates="case")
    
    assigned_to = relationship("User", foreign_keys=[assigned_to_user_id])
    assigned_by = relationship("User", foreign_keys=[assigned_by_user_id])

class UploadedDocument(Base):
    __tablename__ = "uploaded_documents"
    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("case_files.id"))
    document_type = Column(String, nullable=False) # requirement / quotation / logo
    original_filename = Column(String, nullable=False)
    stored_path = Column(String, nullable=False)
    mime_type = Column(String, nullable=False)
    text_extracted = Column(Text, nullable=True)
    ocr_used = Column(Boolean, default=False)
    ocr_metadata = Column(JSON, nullable=True)
    # Nuevos campos OCR V2
    ocr_engine_used = Column(String(50), nullable=True)
    ocr_score = Column(Float, nullable=True)
    ocr_status = Column(String(50), nullable=True) # PROCESSING, APPROVED, REVIEW_REQUIRED, FAILED
    ocr_processed_at = Column(DateTime(timezone=True), nullable=True)
    structured_document_path = Column(String, nullable=True)
    
    processing_job_id = Column(String(100), nullable=True)
    processing_status = Column(String(50), default="pending", nullable=False)
    processing_error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    case = relationship("CaseFile", back_populates="documents")

class ParsedSection(Base):
    __tablename__ = "parsed_sections"
    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("case_files.id"))
    document_id = Column(Integer, ForeignKey("uploaded_documents.id", ondelete="CASCADE"), nullable=False, index=True)
    original_roman = Column(String(20), nullable=True)
    original_order = Column(Integer, nullable=True)
    title = Column(String(255), nullable=True)
    original_text = Column(Text, nullable=True)
    current_text = Column(Text, nullable=True)
    cleaned_text = Column(Text, nullable=True)
    normalized_text = Column(Text, nullable=True)
    structure_json = Column(JSONB, nullable=True)
    corrections_json = Column(JSONB, nullable=True)
    warnings_json = Column(JSONB, nullable=True)
    extraction_metadata = Column(JSONB, nullable=True)
    is_selected = Column(Boolean, default=False)
    confidence_score = Column(Float, nullable=True)
    warnings = Column(String, nullable=True) # Retained for backwards compatibility if needed, or we can drop it. The prompt says "Si alguna columna ya existe...". I'll keep warnings and add warnings_json.
    review_status = Column(String, default="pending_review") # pending_review, validated, rejected

class QuotationExtraction(Base):
    __tablename__ = "quotation_extractions"
    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("case_files.id"))
    supplier_ruc = Column(String, nullable=True)
    supplier_business_name = Column(String, nullable=True)
    supplier_address = Column(String, nullable=True)
    supplier_phone = Column(String, nullable=True)
    supplier_email = Column(String, nullable=True)
    contact_name = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    brand = Column(String, nullable=True)
    model = Column(String, nullable=True)
    quantity = Column(Integer, nullable=True)
    unit_price = Column(Float, nullable=True)
    total_price = Column(Float, nullable=True)
    currency = Column(String, nullable=True)
    payment_condition = Column(String, nullable=True)
    delivery_term = Column(String, nullable=True)
    execution_term = Column(String, nullable=True)
    warranty_term = Column(String, nullable=True)
    warranty_conditions = Column(Text, nullable=True)
    quote_validity = Column(String, nullable=True)
    confidence = Column(Float, nullable=True)
    raw_json = Column(JSON, nullable=True)
    review_status = Column(String, default="pending_review") # pending_review, validated, rejected

class FinalConditionComparison(Base):
    __tablename__ = "final_condition_comparisons"
    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("case_files.id"))
    field_name = Column(String, nullable=False)
    requirement_value = Column(String, nullable=True)
    quotation_value = Column(String, nullable=True)
    final_value = Column(String, nullable=True)
    status = Column(String, nullable=False) # Coincide, Reemplazado, Revisión Manual


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String(50), ForeignKey("tenants.id", onupdate="RESTRICT", ondelete="RESTRICT"), server_default="mega_tenant", nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    action = Column(String, nullable=False)
    entity_type = Column(String, nullable=False)
    entity_id = Column(String, nullable=False)
    status = Column(String, nullable=True)
    details = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_audit_logs_action_entity", "action", "entity_id"),
        Index("ix_audit_logs_tenant_created", "tenant_id", "created_at"),
    )

class ProcessingJob(Base):
    __tablename__ = "processing_jobs"
    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(String(100), unique=True, index=True, nullable=True)
    case_id = Column(Integer, ForeignKey("case_files.id", ondelete="CASCADE"), nullable=True, index=True)
    tenant_id = Column(String(50), ForeignKey("tenants.id"), nullable=False, server_default="mega_tenant", index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    document_id = Column(Integer, ForeignKey("uploaded_documents.id"), nullable=True)
    job_type = Column(String(50), nullable=False, server_default="REQUIREMENT_OCR")  # REQUIREMENT_OCR, QUOTATION_EXTRACTION, COMPARISON_RUN
    worker_type = Column(String(50), nullable=False, default="abst_worker")  # abst_worker, abst_worker_ocr
    worker_name = Column(String(100), nullable=True)
    status = Column(String(50), default="QUEUED", nullable=False)  # QUEUED, PROCESSING, READY, FAILED
    progress = Column(Integer, default=0, nullable=False, server_default="0")
    status_message = Column(String(255), nullable=True)
    idempotency_key = Column(String(128), index=True, nullable=True)
    attempt_count = Column(Integer, default=1, nullable=False, server_default="1")
    max_retries = Column(Integer, default=3, nullable=False, server_default="3")
    failure_classification = Column(String(50), nullable=True)  # RETRYABLE, FINAL
    last_heartbeat_at = Column(DateTime(timezone=True), nullable=True)
    error_message = Column(Text, nullable=True)
    result_summary = Column(Text, nullable=True)  # JSON-serialized summary
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_processing_jobs_tenant_status", "tenant_id", "status"),
        Index("ix_processing_jobs_status_heartbeat", "status", "last_heartbeat_at"),
        Index("ix_processing_jobs_status_created", "status", "created_at"),
        Index("ix_processing_jobs_tenant_created", "tenant_id", "created_at"),
    )


class ProcessingMetrics(Base):
    __tablename__ = "processing_metrics"
    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(String(100), ForeignKey("processing_jobs.job_id", ondelete="CASCADE"), nullable=False, index=True)
    tenant_id = Column(String(50), ForeignKey("tenants.id", onupdate="RESTRICT", ondelete="RESTRICT"), nullable=False, server_default="mega_tenant", index=True)
    case_id = Column(Integer, ForeignKey("case_files.id", ondelete="CASCADE"), nullable=True, index=True)
    job_type = Column(String(50), nullable=False, index=True)
    queue_time_ms = Column(Integer, nullable=False, default=0, server_default="0")
    processing_time_ms = Column(Integer, nullable=False, default=0, server_default="0")
    total_time_ms = Column(Integer, nullable=False, default=0, server_default="0")
    worker_name = Column(String(100), nullable=False, default="unassigned", server_default="unassigned")
    pages_processed = Column(Integer, nullable=False, default=0, server_default="0")
    success = Column(Boolean, nullable=False, default=True, index=True)
    error_code = Column(String(50), nullable=True)
    error_category = Column(String(50), nullable=True)  # TRANSIENT_INFRA, CORRUPT_INPUT, BUSINESS_RULE
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    __table_args__ = (
        Index("ix_processing_metrics_tenant_created", "tenant_id", "created_at"),
        Index("ix_processing_metrics_type_created", "job_type", "created_at"),
        Index("ix_processing_metrics_success_created", "success", "created_at"),
    )


class WorkerHeartbeat(Base):
    __tablename__ = "worker_heartbeats"
    worker_name = Column(String(100), primary_key=True)
    worker_type = Column(String(50), nullable=False, index=True)
    hostname = Column(String(100), nullable=False, default="localhost", server_default="localhost")
    status = Column(String(30), nullable=False, default="IDLE", server_default="IDLE")  # IDLE, BUSY, UNRESPONSIVE, OFFLINE
    current_job_id = Column(String(100), nullable=True)
    tenant_id = Column(String(50), ForeignKey("tenants.id", onupdate="RESTRICT", ondelete="RESTRICT"), nullable=True)
    last_seen = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), index=True)
    started_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_worker_heartbeats_status_last_seen", "status", "last_seen"),
    )

class ComparisonRunStatus(str, enum.Enum):
    CREATED = "CREATED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

class RequirementItemType(str, enum.Enum):
    TECHNICAL = "TECHNICAL"
    COMMERCIAL = "COMMERCIAL"
    LEGAL = "LEGAL"
    DELIVERY = "DELIVERY"
    WARRANTY = "WARRANTY"

class ComparisonResultStatus(str, enum.Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    MANUAL_REVIEW = "MANUAL_REVIEW"

class EvaluationMethod(str, enum.Enum):
    EXACT_MATCH = "EXACT_MATCH"
    NUMERIC_MATCH = "NUMERIC_MATCH"
    FUZZY_MATCH = "FUZZY_MATCH"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    NO_MATCH = "NO_MATCH"

class ComparisonRun(Base):
    __tablename__ = "comparison_runs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id = Column(Integer, ForeignKey("case_files.id", ondelete="RESTRICT"), nullable=False, index=True)
    requirement_doc_id = Column(Integer, ForeignKey("uploaded_documents.id", ondelete="RESTRICT"), nullable=False)
    quotation_doc_id = Column(Integer, ForeignKey("uploaded_documents.id", ondelete="RESTRICT"), nullable=False)
    status = Column(SAEnum(ComparisonRunStatus, name="comparison_run_status_enum", create_type=False), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relaciones
    case = relationship("CaseFile", foreign_keys=[case_id])
    requirement_doc = relationship("UploadedDocument", foreign_keys=[requirement_doc_id])
    quotation_doc = relationship("UploadedDocument", foreign_keys=[quotation_doc_id])
    results = relationship("ComparisonResult", back_populates="run", cascade="all, delete-orphan")

class RequirementItem(Base):
    __tablename__ = "requirement_items"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    parsed_section_id = Column(Integer, ForeignKey("parsed_sections.id", ondelete="CASCADE"), nullable=False)
    item_type = Column(SAEnum(RequirementItemType, name="requirement_item_type_enum", create_type=False), nullable=False)
    content_text = Column(String, nullable=False)
    is_approved = Column(Boolean, default=False, nullable=False)

    # Relaciones
    parsed_section = relationship("ParsedSection")

class ComparisonResult(Base):
    __tablename__ = "comparison_results"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id = Column(UUID(as_uuid=True), ForeignKey("comparison_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    requirement_item_id = Column(UUID(as_uuid=True), ForeignKey("requirement_items.id", ondelete="CASCADE"), nullable=False, index=True)
    quotation_section_id = Column(Integer, ForeignKey("parsed_sections.id", ondelete="SET NULL"), nullable=True)
    status = Column(SAEnum(ComparisonResultStatus, name="comparison_result_status_enum", create_type=False), nullable=False, index=True)
    evaluation_method = Column(SAEnum(EvaluationMethod, name="comparison_evaluation_method_enum", create_type=False), nullable=False)
    confidence_score = Column(Float, nullable=False)
    reasoning = Column(String, nullable=True)
    evidence_text = Column(String, nullable=True)
    requirement_page = Column(Integer, nullable=True)
    quotation_page = Column(Integer, nullable=True)

    # Relaciones
    run = relationship("ComparisonRun", back_populates="results")
    requirement_item = relationship("RequirementItem")
    quotation_section = relationship("ParsedSection")

    __table_args__ = (
        UniqueConstraint('run_id', 'requirement_item_id', name='uq_comparison_run_requirement'),
    )


class RolloutTenantAssignment(Base):
    __tablename__ = "rollout_tenant_assignments"
    
    tenant_id = Column(String(50), ForeignKey("tenants.id", onupdate="RESTRICT", ondelete="RESTRICT"), primary_key=True)
    assigned_ring = Column(Integer, nullable=True)
    assignment_version = Column(String(20), nullable=False)
    routing_mode = Column(String(50), nullable=False, default="AUTO")
    override_until = Column(DateTime(timezone=True), nullable=True)
    reason = Column(String(100), nullable=True)
    assigned_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

class BootstrapLedger(Base):
    __tablename__ = "bootstrap_ledger"
    operation_id = Column(String(100), primary_key=True)
    payload_hash = Column(String(64), nullable=False)
    executed_at = Column(DateTime(timezone=True), server_default=func.now())
