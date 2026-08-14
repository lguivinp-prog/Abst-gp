import pytest
from app.services.v6.engines.document_quality_analyzer import DocumentQualityAnalyzer
from app.models.v6.document_quality import DocumentQualityThresholdConfig
from sqlalchemy.orm import Session

def test_document_quality_analyzer_good(db_session: Session):
    config = DocumentQualityThresholdConfig()
    db_session.add(config)
    db_session.commit()
    
    analyzer = DocumentQualityAnalyzer(db_session)
    metrics = {
        "dpi": 300,
        "blur_score": 150.0,
        "rotation_degrees": 1.0,
        "contrast_ratio": 10.0,
        "empty_pages": False
    }
    
    assessment = analyzer.analyze(document_id=1, mock_pdf_metrics=metrics)
    assert assessment.quality_status == "QUALITY_GOOD"
    assert len(assessment.issues) == 0

def test_document_quality_analyzer_exception(db_session: Session):
    analyzer = DocumentQualityAnalyzer(db_session)
    metrics = {
        "dpi": 140, # triggers warning
        "blur_score": 50.0, # triggers exception
        "rotation_degrees": 1.0,
        "contrast_ratio": 10.0,
        "empty_pages": False
    }
    
    assessment = analyzer.analyze(document_id=2, mock_pdf_metrics=metrics)
    assert assessment.quality_status == "QUALITY_EXCEPTION_REQUIRED"
    assert any(i["type"] == "HIGH_BLUR" for i in assessment.issues)

def test_document_quality_analyzer_blocked(db_session: Session):
    analyzer = DocumentQualityAnalyzer(db_session)
    metrics = {
        "dpi": 300,
        "blur_score": 200.0,
        "rotation_degrees": 0.0,
        "contrast_ratio": 10.0,
        "empty_pages": True # triggers BLOCKED
    }
    
    assessment = analyzer.analyze(document_id=3, mock_pdf_metrics=metrics)
    assert assessment.quality_status == "QUALITY_BLOCKED"
