import os
import tempfile
import pytest
import hashlib
import fitz
from app.services.v6.reporting.pdf_report_generator import PdfReportGenerator

@pytest.fixture
def sample_snapshot_and_meta():
    snapshot = {
        "metadata": {
            "case_code": "EXP-2026-TEST-001",
            "version_number": 1
        },
        "legal_regime_notice": "Ley N.º 32069 y D. S. N.º 009-2025-EF",
        "winner": {
            "supplier_name": "Corporación Perú Eficiente SAC",
            "supplier_ruc": "20556677889",
            "validation_status": "VERIFIED",
            "currency": "PEN",
            "total_amount": 45000.00
        },
        "requirements": [
            {
                "description": "Garantía de fábrica 24 meses",
                "mandatory": True,
                "evaluation_status": "PASSED",
                "evidence_document_name": "ficha_tecnica.pdf",
                "evidence_verified": True
            }
        ],
        "vfm_evaluation": [
            {
                "supplier_name": "Corporación Perú Eficiente SAC",
                "supplier_ruc": "20556677889",
                "currency": "PEN",
                "price": 45000.0,
                "total_score": 10.0,
                "vfm_ratio": 4500.0,
                "is_eligible": True,
                "derived_rank": 1,
                "reason": ""
            }
        ]
    }
    approval_meta = {
        "generated_by_name": "operador_test",
        "generated_at": "2026-10-17 10:00:00 UTC",
        "approved_by_name": "supervisor_test",
        "approved_at": "2026-10-17 11:00:00 UTC",
        "approval_notes": "Aprobado formalmente conforme a ley",
        "snapshot_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    }
    return snapshot, approval_meta

def test_generate_pdf_bytes_success(sample_snapshot_and_meta):
    snapshot, meta = sample_snapshot_and_meta
    pdf_bytes, pdf_hash = PdfReportGenerator.generate_pdf_bytes(snapshot, meta)
    
    assert len(pdf_bytes) > 1000
    assert pdf_hash == hashlib.sha256(pdf_bytes).hexdigest()

    # PyMuPDF verification
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    assert doc.page_count >= 1
    page0_text = doc.load_page(0).get_text()
    assert "INFORME TÉCNICO DE EVALUACIÓN" in page0_text
    assert "Corporación Perú Eficiente SAC" in page0_text
    assert "20556677889" in page0_text
    doc.close()

def test_pdf_footer_has_snapshot_hash_and_disclaimer(sample_snapshot_and_meta):
    snapshot, meta = sample_snapshot_and_meta
    pdf_bytes, _ = PdfReportGenerator.generate_pdf_bytes(snapshot, meta)

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page_text = doc.load_page(0).get_text()
    
    # Disclaimer text in footer
    assert "no constituye otorgamiento de la buena pro" in page_text
    # Snapshot hash printed in footer
    assert meta["snapshot_hash"][:16] in page_text
    doc.close()

def test_pdf_footer_does_not_contain_circular_pdf_hash(sample_snapshot_and_meta):
    snapshot, meta = sample_snapshot_and_meta
    pdf_bytes, pdf_hash = PdfReportGenerator.generate_pdf_bytes(snapshot, meta)

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page_text = doc.load_page(0).get_text()
    
    # The generated PDF MUST NOT contain its own pdf_hash (circularity prevention)
    assert pdf_hash not in page_text
    doc.close()

def test_pdf_atomic_persistence(sample_snapshot_and_meta):
    snapshot, meta = sample_snapshot_and_meta
    pdf_bytes, _ = PdfReportGenerator.generate_pdf_bytes(snapshot, meta)

    with tempfile.TemporaryDirectory() as tmpdir:
        filename = "test_report_v1.pdf"
        saved_path = PdfReportGenerator.persist_pdf_atomically(pdf_bytes, tmpdir, filename)

        assert os.path.exists(saved_path)
        assert os.path.basename(saved_path) == filename

        # Verify no orphan temp files remain
        remaining = os.listdir(tmpdir)
        assert filename in remaining
        for f in remaining:
            assert not f.startswith(".tmp_")

        with open(saved_path, "rb") as f:
            read_bytes = f.read()
        assert read_bytes == pdf_bytes

def test_pdf_path_traversal_rejection():
    with tempfile.TemporaryDirectory() as tmpdir:
        malicious_filename = "../../../etc/evil.pdf"
        with pytest.raises(ValueError, match="path traversal"):
            PdfReportGenerator.persist_pdf_atomically(b"fake", tmpdir, malicious_filename)

def test_pdf_byte_stability_successive_reads(sample_snapshot_and_meta):
    snapshot, meta = sample_snapshot_and_meta
    pdf_bytes, pdf_hash = PdfReportGenerator.generate_pdf_bytes(snapshot, meta)

    with tempfile.TemporaryDirectory() as tmpdir:
        saved_path = PdfReportGenerator.persist_pdf_atomically(pdf_bytes, tmpdir, "stable.pdf")

        with open(saved_path, "rb") as f1:
            bytes_1 = f1.read()
        with open(saved_path, "rb") as f2:
            bytes_2 = f2.read()

        assert bytes_1 == bytes_2
        assert hashlib.sha256(bytes_1).hexdigest() == pdf_hash
        assert hashlib.sha256(bytes_2).hexdigest() == pdf_hash

def test_pdf_corrupted_bytes_fails_verification():
    corrupted_bytes = b"NOT_A_VALID_PDF_HEADER_OR_CONTENT"
    with pytest.raises(Exception):
        PdfReportGenerator._verify_pdf_with_fitz(corrupted_bytes)

def test_pdf_path_traversal_sibling_prefix_rejection():
    """
    Reproducción exacta del hallazgo B10:
    Directorio raíz: /tmp/.../case_1
    Candidato: ../case_12/report.pdf
    El chequeo ingenuo startswith() fallaba al aceptar 'case_12' porque comienza con 'case_1'.
    commonpath() / realpath() debe rechazarlo categóricamente.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        case_1_dir = os.path.join(tmpdir, "case_1")
        os.makedirs(case_1_dir, exist_ok=True)
        sibling_candidate = "../case_12/report.pdf"

        with pytest.raises(ValueError, match="path traversal"):
            PdfReportGenerator.persist_pdf_atomically(b"%PDF-1.4 test", case_1_dir, sibling_candidate)

def test_pdf_xml_escaping_malicious_input(sample_snapshot_and_meta):
    """
    Verifica que ReportLab no falle con SAXParseException al recibir caracteres XML reservados
    (<, >, &, ", ') o intentos de inyección de markup en nombres, notas o descripciones.
    """
    snapshot, meta = sample_snapshot_and_meta
    snapshot["winner"]["supplier_name"] = "Proveedor <script>alert('xss')</script> & Cía. \"S.A.C.\""
    snapshot["requirements"][0]["description"] = "Requisito con <tag>inválido</tag> & ampersand & 'comillas'"
    meta["approval_notes"] = "Notas con <XML> & markup no confiable </XML>"

    pdf_bytes, pdf_hash = PdfReportGenerator.generate_pdf_bytes(snapshot, meta)
    assert len(pdf_bytes) > 1000
    assert pdf_hash is not None

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page_text = doc.load_page(0).get_text()
    assert "Proveedor" in page_text
    assert "alert('xss')" in page_text
    doc.close()

def test_pdf_reconcile_orphans():
    """
    Verifica el protocolo de recuperación post-fallo: eliminación de archivos temporales .tmp_*
    y PDFs huérfanos sin tocar archivos válidos registrados.
    """
    import time
    with tempfile.TemporaryDirectory() as tmpdir:
        # 1. Archivo válido
        valid_path = os.path.join(tmpdir, "valid_report_v1.pdf")
        with open(valid_path, "wb") as f:
            f.write(b"%PDF-valid")

        # 2. Archivo temporal huérfano viejo
        orphan_tmp = os.path.join(tmpdir, ".tmp_12345_report.pdf")
        with open(orphan_tmp, "wb") as f:
            f.write(b"%PDF-temp")

        # 3. Archivo PDF huérfano no referenciado viejo P13
        orphan_pdf = os.path.join(tmpdir, "report_p13_v2_unreferenced_orphan.pdf")
        with open(orphan_pdf, "wb") as f:
            f.write(b"%PDF-orphan")

        # 4. Archivo PDF de otro módulo (debe ser preservado)
        other_pdf = os.path.join(tmpdir, "other_unreferenced.pdf")
        with open(other_pdf, "wb") as f:
            f.write(b"%PDF-other")

        # Ajustar timestamps para simular antigüedad (> 10 segundos)
        old_time = time.time() - 3600
        os.utime(orphan_tmp, (old_time, old_time))
        os.utime(orphan_pdf, (old_time, old_time))
        os.utime(other_pdf, (old_time, old_time))

        cleaned = PdfReportGenerator.reconcile_orphans(tmpdir, [valid_path], max_age_seconds=10)
        assert cleaned == 2
        assert os.path.exists(valid_path)
        assert os.path.exists(other_pdf), "PDFs ajenos a P13 no deben ser eliminados"
        assert not os.path.exists(orphan_tmp)
        assert not os.path.exists(orphan_pdf)

