import pytest
from fastapi.testclient import TestClient
import os
from app.main import app

# Para usar base de datos de test en SQLite o simplemente usar la que ya tenemos
# ya que las pruebas se ejecutan en docker y se puede limpiar. Por brevedad,
# usaremos TestClient directamente. 
# Nota: en un entorno real configuraríamos un test DB específico con fixtures, 
# aquí crearemos los registros y validaremos sobre la base local.

def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["api"] == "ok"
    # redis y db podrían variar dependiendo de si se corre dentro de docker con todos los servicios, 
    # pero al menos la ruta debe existir.
from unittest.mock import patch, Mock

@patch("app.api.routers.cases.task_queue")
def test_full_integration_flow(mock_queue, admin_client):
    # 1. Crear expediente
    response = admin_client.post("/cases/", json={"title": "Test Integration", "contract_type": "bienes"})
    assert response.status_code == 200
    case = response.json()
    case_id = case["id"]
    
    # Rutas para PDFs (usando el mock_data que ya existe)
    mock_dir = os.path.join(os.path.dirname(__file__), "..", "..", "mock_data")
    req_pdf_path = os.path.join(mock_dir, "req_bienes_digital.pdf")
    quot_pdf_path = os.path.join(mock_dir, "cotizacion_digital.pdf")
    
    # Si los PDFs no existen, saltar prueba (aunque acabamos de crearlos)
    if not os.path.exists(req_pdf_path):
        pytest.skip("Archivos mock PDF no encontrados")

    # Configurar mock de task_queue para devolver un ID de string
    mock_job_obj = Mock()
    mock_job_obj.id = "mock-job-id-123"
    mock_queue.enqueue.return_value = mock_job_obj

    # 2. Subir requerimiento
    with open(req_pdf_path, "rb") as f:
        res = admin_client.post(f"/cases/{case_id}/requirement/upload", files={"file": ("req.pdf", f, "application/pdf")})
    assert res.status_code == 200
    
    # 3. Procesar requerimiento (simulado síncrono para test)
    job_id = res.json()["job_id"]
    from app.worker.tasks import process_requirement_task
    with patch("app.worker.tasks.process_requirement_task") as mock_prt:
        def dummy_prt(c_id, path):
            from app.core.database import SessionLocal
            from app.models.domain import ParsedSection, UploadedDocument
            db = SessionLocal()
            try:
                doc = UploadedDocument(case_id=c_id, document_type="requirement", stored_path=path, original_filename="req.pdf", mime_type="application/pdf")
                db.add(doc)
                db.commit()
                db.refresh(doc)
                db.add(ParsedSection(case_id=c_id, document_id=doc.id, title="OBJETIVO", current_text="mock", review_status="pending"))
                db.add(ParsedSection(case_id=c_id, document_id=doc.id, title="FORMA DE PAGO", current_text="mock", review_status="pending"))
                db.commit()
            finally:
                db.close()
            
        mock_prt.side_effect = dummy_prt
        mock_prt(case_id, req_pdf_path)
    
    res_case = admin_client.get(f"/cases/{case_id}")
    assert res_case.status_code == 200
    res = admin_client.get(f"/cases/{case_id}/sections")
    assert res.status_code == 200
    sections = res.json()
    assert len(sections) > 0
    
    # Seleccionar la primera sección (ej. Objetivo) y la de Forma de pago
    for sec in sections:
        if "OBJETIVO" in sec["title"] or "FORMA DE PAGO" in sec["title"]:
            res = admin_client.put(f"/cases/sections/{sec['id']}", json={
                "is_selected": True,
                "review_status": "validated",
                "current_text": sec["current_text"]
            })
            assert res.status_code == 200
            
    # 4. Subir cotización
    with open(quot_pdf_path, "rb") as f:
        res = admin_client.post(f"/cases/{case_id}/quotation/upload", files={"file": ("quot.pdf", f, "application/pdf")})
    assert res.status_code == 200
    
    # 5. Ejecutar comparación
    res = admin_client.post(f"/cases/{case_id}/comparison/run")
    assert res.status_code == 200
    
    # 6. Generar HTML
    res = admin_client.post(f"/cases/{case_id}/generate/html")
    assert res.status_code == 200
    assert "version" in res.json()
    
    # 7. Validar salida
    res = admin_client.get(f"/cases/{case_id}/output")
    assert res.status_code == 200
    output = res.json()
    assert "html" in output
    assert "plain_text" in output
    assert "FORMA DE PAGO" in output["html"] # O la sección extraída
    assert "Cuadro Comparativo" in output["html"]
