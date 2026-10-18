from app.models.base import Base
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Index, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

class GeneratedOutput(Base):
    __tablename__ = "generated_outputs"
    __table_args__ = (
        Index(
            'uq_generated_outputs_p13_version',
            'case_id', 'report_kind', 'version_number',
            unique=True,
            postgresql_where=text("report_kind = 'INFORME_TECNICO_EVALUACION'")
        ),
        Index(
            'uq_generated_outputs_p13_idempotency',
            'case_id', 'report_kind', 'idempotency_key',
            unique=True,
            postgresql_where=text("report_kind = 'INFORME_TECNICO_EVALUACION' AND idempotency_key IS NOT NULL")
        ),
        {'extend_existing': True}
    )
    
    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("case_files.id", ondelete="CASCADE"), nullable=False, index=True)
    template_id = Column(Integer, ForeignKey("output_templates.id", ondelete="RESTRICT"), nullable=False)
    content_rendered = Column(Text, nullable=False)
    generation_hash = Column(String, nullable=False)
    generated_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    generated_at = Column(DateTime(timezone=True), server_default=func.now())
    template_version = Column(String(20), nullable=False)
    accuracy_gate_result = Column(String(50), nullable=False)
    source_snapshot = Column(JSONB, nullable=False)
    status = Column(String(50), nullable=False, default="GENERATED")  # GENERATED, UNDER_REVIEW, APPROVED, EXPORTED, REJECTED
    version_number = Column(Integer, nullable=False, default=1)
    html_output = Column(Text, nullable=True)
    plain_text_output = Column(Text, nullable=True)

    # P13 attributes
    report_kind = Column(String(50), nullable=False, default="CONDICIONES")
    approved_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    approval_notes = Column(Text, nullable=True)
    rejected_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    rejected_at = Column(DateTime(timezone=True), nullable=True)
    rejection_reason = Column(Text, nullable=True)
    idempotency_key = Column(String(128), nullable=True)
    request_hash = Column(String(64), nullable=True)
    snapshot_hash = Column(String(64), nullable=True)
    html_hash = Column(String(64), nullable=True)
    pdf_hash = Column(String(64), nullable=True)
    pdf_storage_path = Column(String(512), nullable=True)
    
    case = relationship("CaseFile")
    template = relationship("OutputTemplate")
    approver = relationship("User", foreign_keys=[approved_by])
    rejecter = relationship("User", foreign_keys=[rejected_by])
    generator = relationship("User", foreign_keys=[generated_by])

    @property
    def has_pdf(self) -> bool:
        """
        Determina si el reporte dispone de un artefacto PDF físico verificado.
        """
        return bool(self.pdf_storage_path and self.pdf_hash)

