from app.models.base import Base
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

class DocumentQualityAssessment(Base):
    __tablename__ = "document_quality_assessments"
    
    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, nullable=False, index=True) # Mock FK to general documents
    quality_status = Column(String(50), nullable=False) # QUALITY_GOOD, QUALITY_WARNING, QUALITY_BLOCKED, QUALITY_EXCEPTION_REQUIRED
    dpi_estimate = Column(Integer, nullable=True)
    rotation_detected = Column(Boolean, nullable=True)
    blur_score = Column(Float, nullable=True)
    ocr_expected_quality = Column(String(20), nullable=True)
    issues = Column(JSONB, nullable=True)
    analyzer_version = Column(String(20), nullable=False, default="1.0")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class DocumentQualityThresholdConfig(Base):
    __tablename__ = "document_quality_thresholds"
    
    id = Column(Integer, primary_key=True, index=True)
    min_dpi = Column(Integer, nullable=False, default=150)
    max_rotation_degrees = Column(Float, nullable=False, default=5.0)
    min_blur_score = Column(Float, nullable=False, default=100.0) # Laplacian variance threshold
    min_contrast_ratio = Column(Float, nullable=False, default=4.5)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
