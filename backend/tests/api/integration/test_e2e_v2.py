import pytest
from fastapi.testclient import TestClient
import os

def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["api"] == "ok"
    # redis y db podrían variar dependiendo de si se corre dentro de docker con todos los servicios, 
    # pero al menos la ruta debe existir.
from unittest.mock import patch, Mock

@patch("app.api.routers.cases.task_queue")
@patch("app.services.extraction_engine.orchestrator.ocr_queue.enqueue")
@patch("app.services.extraction_engine.orchestrator.settings.OCR_ENGINE", "v2")
def test_full_integration_flow_v2(mock_ocr_enqueue, mock_queue, admin_client):
    print("1. Crear expediente")
    # 1. Crear expediente
    response = admin_client.post("/cases/", json={"title": "Test Integration V2", "contract_type": "bienes"})
    assert response.status_code == 200
    case = response.json()
    case_id = case["id"]
    
    # Rutas para PDFs (usando el mock_data que ya existe)
    mock_dir = os.path.join(os.path.dirname(__file__), "..", "..", "mock_data")
    req_pdf_path = os.path.join(mock_dir, "req_bienes_scanned.pdf")
    quot_pdf_path = os.path.join(mock_dir, "cotizacion_digital.pdf")
    
    # Si los PDFs no existen, saltar prueba
    if not os.path.exists(req_pdf_path):
        pytest.skip("Archivos mock PDF no encontrados")

    # Configurar mock de task_queue para devolver un ID de string
    mock_job_obj = Mock()
    mock_job_obj.id = "mock-job-id-456"
    mock_queue.enqueue.return_value = mock_job_obj

    print("2. Subir requerimiento")
    # 2. Subir requerimiento
    with open(req_pdf_path, "rb") as f:
        res = admin_client.post(f"/cases/{case_id}/requirement/upload", files={"file": ("req.pdf", f, "application/pdf")})
    assert res.status_code == 200
    
    print("3. Procesar requerimiento")
    # 3. Procesar requerimiento
    job_id = res.json()["job_id"]
    from app.worker.tasks import process_requirement_task
    
    # We will just patch the import in the test file using sys.modules or just patch the actual app module
    with patch("app.worker.tasks.process_requirement_task") as mock_prt:
        def dummy_prt(c_id, path):
            from app.core.database import SessionLocal
            from app.models.domain import ParsedSection, UploadedDocument, OCRProcessingRun
            db = SessionLocal()
            doc = UploadedDocument(case_id=c_id, document_type="requirement", stored_path=path, original_filename="req.pdf", mime_type="application/pdf")
            db.add(doc)
            db.commit()
            db.refresh(doc)
            db.add(ParsedSection(case_id=c_id, document_id=doc.id, title="OBJETIVO", current_text="mock", review_status="pending"))
            db.add(ParsedSection(case_id=c_id, document_id=doc.id, title="FORMA DE PAGO", current_text="mock", review_status="pending"))
            db.commit()
            
        mock_prt.side_effect = dummy_prt
        mock_prt(case_id, req_pdf_path)
    
    print("Fetching sections")
    res_case = admin_client.get(f"/cases/{case_id}")
    assert res_case.status_code == 200
    res = admin_client.get(f"/cases/{case_id}/sections")
    assert res.status_code == 200
    sections = res.json()
    assert len(sections) > 0
    
    print("Validating sections")
    # Seleccionar la primera seccin (ej. Objetivo) y la de Forma de pago
    for sec in sections:
        if "OBJETIVO" in sec["title"] or "FORMA DE PAGO" in sec["title"]:
            res = admin_client.put(f"/cases/sections/{sec['id']}", json={
                "is_selected": True,
                "review_status": "validated",
                "current_text": sec["current_text"]
            })
            assert res.status_code == 200
            
    print("4. Subir cotizacion")
    # 4. Subir cotizacin
    with open(quot_pdf_path, "rb") as f:
        res = admin_client.post(f"/cases/{case_id}/quotation/upload", files={"file": ("quot.pdf", f, "application/pdf")})
    assert res.status_code == 200
    
    print("5. Ejecutar comparacion")
    # 5. Ejecutar comparacin
    res = admin_client.post(f"/cases/{case_id}/comparison/run")
    assert res.status_code == 200
    
    print("6. Generar HTML")
    # 6. Generar HTML
    res = admin_client.post(f"/cases/{case_id}/generate/html")
    assert res.status_code == 200
    assert "version" in res.json()
    
    print("7. Validar salida")
    res = admin_client.get(f"/cases/{case_id}/output")
    assert res.status_code == 200
    output = res.json()
    assert "html" in output
    assert "plain_text" in output
    assert "Cuadro Comparativo" in output["html"]


@patch("app.api.routers.cases.task_queue")
@patch("app.services.extraction_engine.orchestrator.ocr_queue.enqueue")
def test_empty_extraction_v2_fallback(mock_ocr_enqueue, mock_queue, admin_client, tmp_path):
    # Generar un PDF vacio/sin estructura temporal
    pytest.importorskip("reportlab")
    from reportlab.pdfgen import canvas
    
    pdf_path = tmp_path / "empty_v2.pdf"
    c = canvas.Canvas(str(pdf_path))
    c.drawString(100, 750, "Pagina sin texto estructurado.")
    c.save()
    
    # 1. Crear expediente
    response = admin_client.post("/cases/", json={"title": "Empty V2", "contract_type": "bienes"})
    case_id = response.json()["id"]
    
    # 2. Subir PDF
    mock_job_obj = Mock()
    mock_job_obj.id = "mock-job-id-789"
    mock_queue.enqueue.return_value = mock_job_obj

    with open(pdf_path, "rb") as f:
        res = admin_client.post(f"/cases/{case_id}/requirement/upload", files={"file": ("empty_v2.pdf", f, "application/pdf")})
    assert res.status_code == 200
    
    # 3. Procesar
    job_id = res.json()["job_id"]
    from app.worker.tasks import process_requirement_task
    from app.services.extraction.exceptions import NoSectionsExtractedError
    
    # Sentinel: fallo si PaddleOCR intenta instanciarse
    class SentinelPaddleOCR:
        def __init__(self, *args, **kwargs):
            raise Exception("Sentinel: PaddleOCR real inicializado. Esto causaria red o descargas.")
            
    import sys
    sys.modules['paddleocr'] = Mock(PaddleOCR=SentinelPaddleOCR)

    # Hacemos que process_run_v2 se ejecute de manera sincrona cuando el orquestador encole V2
    def mock_enqueue(func_path, args, **kwargs):
        if func_path == "app.worker.ocr_worker_tasks.process_run_v2":
            from app.worker.ocr_worker_tasks import process_run_v2
            process_run_v2(*args)
        return Mock()
    mock_ocr_enqueue.side_effect = mock_enqueue
    
    # Simular que es V1 de base, para que active el fallback
    with patch("app.services.extraction_engine.orchestrator.settings.OCR_ENGINE", "v1"):
        with patch("app.worker.tasks.get_current_job") as mock_get_job:
            mock_job = Mock()
            mock_job.id = job_id
            mock_job.meta = {}
            mock_job.save_meta = Mock()
            mock_get_job.return_value = mock_job
            
            # Dejamos que execute_v1_pipeline corra para capturar la excepcion que lanza su
            # DocumentExtractionAgent nativamente al recibir texto vacio.
            with patch("app.worker.tasks.process_pdf") as mock_v1_process:
                from app.services.ocr.engine import OCRExtractionResult
                mock_v1_process.return_value = OCRExtractionResult(
                    text="", pages_text=[""], page_count=1, ocr_used=False, language="spa", confidence_avg=0, errors=[]
                )
                
                # PaddleOCR está mockeado via sys.modules arriba.
                if True:
                        # Mockeamos OCRV2Pipeline entero para que devuelva un StructuredDocument valido
                        # sin intentar instanciar HybridOcrEngine/PaddleOCREngine y golpear el Sentinel.
                        with patch("app.worker.ocr_worker_tasks.OCRV2Pipeline") as mock_pipeline_class:
                            mock_pipeline_instance = Mock()
                            
                            from app.services.extraction_engine.models.document import StructuredDocument, DocumentBlock
                            doc_mock = StructuredDocument()
                            doc_mock.confidence = 0.99
                            doc_mock.blocks = [
                                DocumentBlock(type="section", content="mock obj", original_text="OBJETIVO", page=1),
                                DocumentBlock(type="section", content="mock pago", original_text="FORMA DE PAGO", page=1)
                            ]
                            mock_pipeline_instance.process_document.return_value = doc_mock
                            mock_pipeline_class.return_value = mock_pipeline_instance
                            
                            process_requirement_task(case_id, str(pdf_path))
                            
                            # V2 se invoco una vez (es decir, encolo su job y lo corrio gracias a mock_enqueue)
                            assert mock_ocr_enqueue.called
                            
                            # Validar DB que el resultado final es correcto
                            from app.core.database import SessionLocal
                            from app.models.domain import ParsedSection
                            db = SessionLocal()
                            sections = db.query(ParsedSection).filter(ParsedSection.case_id == case_id).all()
                            assert len(sections) == 2
                            titles = [s.title for s in sections]
                            assert "OBJETIVO" in titles
                            assert "FORMA DE PAGO" in titles
                            db.close()
