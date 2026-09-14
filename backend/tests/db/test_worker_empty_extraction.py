import pytest
from unittest.mock import patch, MagicMock
from app.models.domain import CaseFile, UploadedDocument, ParsedSection
from app.worker.tasks import execute_v1_pipeline
from app.services.extraction.exceptions import NoSectionsExtractedError

@pytest.fixture
def empty_extraction_case(db_session, tmp_path):
    # Crear un archivo temporal real para pasar la validación de storage
    fake_pdf = tmp_path / "fake.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4 dummy content")

    # Crear un caso
    case = CaseFile(
        title="Test Case",
        contract_type="services",
        status="CREATED"
    )
    db_session.add(case)
    db_session.commit()
    
    # Crear un documento asociado
    doc = UploadedDocument(
        case_id=case.id,
        document_type="requirement",
        original_filename="test.pdf",
        stored_path=str(fake_pdf),
        mime_type="application/pdf"
    )
    db_session.add(doc)
    db_session.commit()
    
    return case, doc

def test_execute_v1_pipeline_empty_extraction_raises_error(db_session, empty_extraction_case):
    case, doc = empty_extraction_case
    
    with patch("app.worker.tasks.process_pdf") as mock_process_pdf:
        # Mock ocr_result
        mock_result = MagicMock()
        mock_result.pages_text = "Texto sin estructura"
        mock_result.text = "Texto sin estructura"
        mock_result.ocr_used = False
        mock_result.page_count = 1
        mock_result.confidence_avg = 1.0
        mock_process_pdf.return_value = mock_result
        
        with patch("app.services.extraction.document_extraction_agent.DocumentExtractionAgent.process") as mock_process:
            # Simular agente devolviendo arreglo vacío
            mock_process.return_value = []
            
            mock_db = MagicMock(wraps=db_session)
            mock_db.close = MagicMock()
            with patch("app.worker.tasks.get_current_job") as mock_get_job, patch("app.worker.tasks.SessionLocal", return_value=mock_db):
                # Mock RQ job
                mock_job = MagicMock()
                mock_job.id = "fake_job_id"
                mock_job.meta = {}
                mock_get_job.return_value = mock_job
                
                # Asignar job id al documento
                doc.processing_job_id = "fake_job_id"
                db_session.commit()
                
                # Ejecutar pipeline y esperar excepcion
                with pytest.raises(NoSectionsExtractedError) as exc_info:
                    execute_v1_pipeline(case.id, doc.stored_path, "fake_job_id")
                
                assert "No se detectaron secciones" in str(exc_info.value)
                
                # Verificar persistencia en base de datos
                db_session.refresh(case)
                db_session.refresh(doc)
                
                assert case.status == "ERROR"
                assert doc.processing_status == "failed"
                assert doc.ocr_status == "FAILED"
                assert "No se detectaron secciones" in doc.processing_error
                
                # Verificar que no se crearon secciones
                sections = db_session.query(ParsedSection).filter(ParsedSection.case_id == case.id).all()
                assert len(sections) == 0

def test_execute_v1_pipeline_success(db_session, empty_extraction_case):
    case, doc = empty_extraction_case
    
    with patch("app.worker.tasks.process_pdf") as mock_process_pdf:
        # Mock ocr_result
        mock_result = MagicMock()
        mock_result.pages_text = "I. TITULO\nContenido"
        mock_result.text = "I. TITULO\nContenido"
        mock_result.ocr_used = False
        mock_result.page_count = 1
        mock_result.confidence_avg = 1.0
        mock_process_pdf.return_value = mock_result
        
        with patch("app.services.extraction.document_extraction_agent.DocumentExtractionAgent.process") as mock_process:
            # Simular agente devolviendo una sección
            mock_section = MagicMock()
            mock_section.metadata = {"original_roman": "I", "title": "TITULO"}
            mock_section.original_text = "Contenido"
            mock_section.cleaned_text = "Contenido"
            mock_section.normalized_text = "Contenido"
            mock_section.structure_json = {}
            mock_section.corrections_json = {}
            mock_section.warnings_json = {}
            
            mock_process.return_value = [mock_section]
            
            mock_db = MagicMock(wraps=db_session)
            mock_db.close = MagicMock()
            with patch("app.worker.tasks.get_current_job") as mock_get_job, patch("app.worker.tasks.SessionLocal", return_value=mock_db):
                # Mock RQ job
                mock_job = MagicMock()
                mock_job.id = "fake_job_id"
                mock_job.meta = {}
                mock_get_job.return_value = mock_job
                
                # Asignar job id al documento
                doc.processing_job_id = "fake_job_id"
                db_session.commit()
                
                # Ejecutar pipeline exitosamente
                execute_v1_pipeline(case.id, doc.stored_path, "fake_job_id")
                
                # Verificar persistencia en base de datos
                db_session.refresh(case)
                db_session.refresh(doc)
                
                assert case.status == "REVIEW_SECTIONS"
                assert doc.processing_status == "finished"
                
                # Verificar que se creó la sección
                sections = db_session.query(ParsedSection).filter(ParsedSection.case_id == case.id).all()
                assert len(sections) == 1
                assert sections[0].original_roman == "I"
