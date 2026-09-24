import pytest
from unittest.mock import patch, MagicMock
from app.services.extraction_engine.v2_pipeline import OCRV2Pipeline
from app.services.ocr.engine import process_pdf
from app.models.v6.case_requirement_matrix import CaseRequirementMatrix
from app.models.domain import UploadedDocument, CaseFile, User
from app.services.v6.extraction.service import RequirementExtractionService
from app.api.routers.v6_requirements import update_requirement, RequirementUpdate
from fastapi import HTTPException
import numpy as np

# A. digital native page -> OCR engine call count = 0
@patch("app.services.extraction_engine.ocr_engine.PaddleOCREngine.__init__", return_value=None)
@patch("app.services.extraction_engine.ocr_engine.TesseractEngine.__init__", return_value=None)
def test_a_digital_native_page_no_ocr_calls(mock_tess, mock_paddle):
    pipeline = OCRV2Pipeline()

    with patch("app.services.extraction_engine.ocr_engine.HybridOcrEngine.extract") as mock_extract, \
         patch("app.services.extraction_engine.pdf_classifier.PdfClassifier.classify") as mock_classify, \
         patch("fitz.open") as mock_fitz_open, \
         patch("app.services.extraction_engine.image_preprocessor.ImagePreprocessor.process") as mock_prep:

        mock_cls = MagicMock()
        mock_cls.document_type = "digital"
        mock_classify.return_value = mock_cls

        mock_doc = MagicMock()
        mock_page = MagicMock()
        mock_page.get_text.return_value = "This is a digital page with enough text to be considered native." * 10
        mock_page.rect = MagicMock(width=800, height=1000)
        mock_doc.__len__.return_value = 1
        mock_doc.__getitem__.return_value = mock_page
        mock_fitz_open.return_value = mock_doc

        mock_prep.return_value = {"processed_images": ["dummy_image_1.png"]}

        with patch("cv2.imread", return_value=np.zeros((1000, 800, 3))):
            pipeline.process_document("dummy.pdf")

        assert mock_extract.call_count == 0

# B. hybrid [native, scanned, native] -> OCR call count = 1 -> exclusivamente page 2
@patch("app.services.extraction_engine.ocr_engine.PaddleOCREngine.__init__", return_value=None)
@patch("app.services.extraction_engine.ocr_engine.TesseractEngine.__init__", return_value=None)
def test_b_hybrid_calls_ocr_only_on_scanned(mock_tess, mock_paddle):
    pipeline = OCRV2Pipeline()

    with patch("app.services.extraction_engine.ocr_engine.HybridOcrEngine.extract") as mock_extract, \
         patch("app.services.extraction_engine.pdf_classifier.PdfClassifier.classify") as mock_classify, \
         patch("fitz.open") as mock_fitz_open, \
         patch("app.services.extraction_engine.image_preprocessor.ImagePreprocessor.process") as mock_prep:

        mock_cls = MagicMock()
        mock_cls.document_type = "hybrid"
        mock_cls.page_results = [
            MagicMock(page_number=1, needs_ocr=False),
            MagicMock(page_number=2, needs_ocr=True),
            MagicMock(page_number=3, needs_ocr=False),
        ]
        mock_classify.return_value = mock_cls

        mock_doc = MagicMock()
        mock_page_native = MagicMock()
        mock_page_native.get_text.return_value = "This is a digital page with enough text." * 10
        mock_page_native.rect = MagicMock(width=800, height=1000)

        mock_page_scanned = MagicMock()
        mock_page_scanned.get_text.return_value = ""
        mock_page_scanned.rect = MagicMock(width=800, height=1000)

        mock_doc.__len__.return_value = 3
        mock_doc.__getitem__.side_effect = [mock_page_native, mock_page_scanned, mock_page_native]
        mock_fitz_open.return_value = mock_doc

        mock_prep.return_value = {"processed_images": ["p1.png", "p2.png", "p3.png"]}

        with patch("cv2.imread", return_value=np.zeros((100, 100, 3))):
            mock_extract.return_value = {"elements": []}
            pipeline.process_document("dummy.pdf")

        from unittest.mock import ANY
        assert mock_extract.call_count == 1
        mock_extract.assert_called_with(ANY, page_number=2)

# B.1 SCANNED-ONLY -> OCR call count = N
@patch("app.services.extraction_engine.ocr_engine.PaddleOCREngine.__init__", return_value=None)
@patch("app.services.extraction_engine.ocr_engine.TesseractEngine.__init__", return_value=None)
def test_c_scanned_only_calls_ocr_for_every_page(mock_tess, mock_paddle):
    pipeline = OCRV2Pipeline()

    with patch("app.services.extraction_engine.ocr_engine.HybridOcrEngine.extract") as mock_extract, \
         patch("app.services.extraction_engine.pdf_classifier.PdfClassifier.classify") as mock_classify, \
         patch("fitz.open") as mock_fitz_open, \
         patch("app.services.extraction_engine.image_preprocessor.ImagePreprocessor.process") as mock_prep:

        mock_cls = MagicMock()
        mock_cls.document_type = "scanned"
        mock_classify.return_value = mock_cls

        mock_doc = MagicMock()
        mock_page_scanned = MagicMock()
        mock_page_scanned.get_text.return_value = ""
        mock_page_scanned.rect = MagicMock(width=800, height=1000)

        mock_doc.__len__.return_value = 3
        mock_doc.__getitem__.side_effect = [mock_page_scanned, mock_page_scanned, mock_page_scanned]
        mock_fitz_open.return_value = mock_doc

        mock_prep.return_value = {"processed_images": ["p1.png", "p2.png", "p3.png"]}

        with patch("cv2.imread", return_value=np.zeros((100, 100, 3))):
            mock_extract.return_value = {"elements": []}
            pipeline.process_document("dummy.pdf")

        # Expected behavior: calls OCR for all 3 pages
        assert mock_extract.call_count == 3

# B.2 native bbox matches document page coordinate space
@patch("app.services.extraction_engine.ocr_engine.PaddleOCREngine.__init__", return_value=None)
@patch("app.services.extraction_engine.ocr_engine.TesseractEngine.__init__", return_value=None)
def test_d_native_bbox_matches_document_page_coordinate_space(mock_tess, mock_paddle):
    pipeline = OCRV2Pipeline()

    with patch("app.services.extraction_engine.ocr_engine.HybridOcrEngine.extract") as mock_extract, \
         patch("app.services.extraction_engine.pdf_classifier.PdfClassifier.classify") as mock_classify, \
         patch("fitz.open") as mock_fitz_open, \
         patch("app.services.extraction_engine.image_preprocessor.ImagePreprocessor.process") as mock_prep:

        mock_cls = MagicMock()
        mock_cls.document_type = "digital"
        mock_classify.return_value = mock_cls

        import fitz
        mock_doc = MagicMock()
        mock_page = MagicMock()
        mock_page.get_text.return_value = "Digital text" * 10
        mock_page.rect = MagicMock(width=800, height=1000) # PDF points
        mock_page.rotation_matrix = fitz.Matrix(1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
        # Mock some words that would be returned by native extraction
        mock_page.get_text.side_effect = lambda arg: [(100, 200, 300, 250, "Digital", 0, 0, 0)] if arg == "words" else ("Digital text" * 10)

        mock_doc.__len__.return_value = 1
        mock_doc.__getitem__.return_value = mock_page
        mock_fitz_open.return_value = mock_doc

        mock_prep.return_value = {"processed_images": ["dummy_image_1.png"]}

        # Preprocessed image is scaled! (e.g. 1600x2000 pixels)
        with patch("cv2.imread", return_value=np.zeros((2000, 1600, 3))):
            doc = pipeline.process_document("dummy.pdf")

        assert len(doc.pages) > 0
        page = doc.pages[0]
        # Verify the dimensions match the processed image dimensions used for layout
        assert page.width == 1600.0
        assert page.height == 2000.0

        # We expect at least one element natively extracted
        # Since currently OCRV2Pipeline just calls OCR indiscriminately, this test will fail because elements will be empty or mock_extract elements
        # But if native extraction works, the bbox should be scaled properly
        # PDF bbox (100, 200, 300, 250) -> Image bbox (200, 400, 600, 500)
        assert len(page.elements) > 0
        element = page.elements[0]
        assert 0 <= element.x < element.x + element.width <= page.width
        assert 0 <= element.y < element.y + element.height <= page.height

# B.3 Provenance
@patch("app.services.extraction_engine.ocr_engine.PaddleOCREngine.__init__", return_value=None)
@patch("app.services.extraction_engine.ocr_engine.TesseractEngine.__init__", return_value=None)
def test_e_native_source_is_not_ocr(mock_tess, mock_paddle):
    pipeline = OCRV2Pipeline()

    with patch("app.services.extraction_engine.pdf_classifier.PdfClassifier.classify") as mock_classify, \
         patch("fitz.open") as mock_fitz_open, \
         patch("app.services.extraction_engine.image_preprocessor.ImagePreprocessor.process") as mock_prep:

        mock_cls = MagicMock()
        mock_cls.document_type = "digital"
        mock_classify.return_value = mock_cls

        import fitz
        mock_doc = MagicMock()
        mock_page = MagicMock()
        mock_page.get_text.return_value = "Digital text" * 10
        mock_page.rect = MagicMock(width=800, height=1000)
        mock_page.rotation_matrix = fitz.Matrix(1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
        mock_page.get_text.side_effect = lambda arg: [(100, 200, 300, 250, "Digital", 0, 0, 0)] if arg == "words" else ("Digital text" * 10)

        mock_doc.__len__.return_value = 1
        mock_doc.__getitem__.return_value = mock_page
        mock_fitz_open.return_value = mock_doc

        mock_prep.return_value = {"processed_images": ["p.png"]}

        with patch("cv2.imread", return_value=np.zeros((1000, 800, 3))):
            doc = pipeline.process_document("dummy.pdf")

        assert len(doc.pages) > 0
        assert len(doc.pages[0].elements) > 0
        assert doc.pages[0].elements[0].source == "native"
        assert doc.pages[0].elements[0].confidence == 1.0

@patch("app.services.extraction_engine.ocr_engine.PaddleOCREngine.__init__", return_value=None)
@patch("app.services.extraction_engine.ocr_engine.TesseractEngine.__init__", return_value=None)
def test_e_ocr_source_preserved(mock_tess, mock_paddle):
    pipeline = OCRV2Pipeline()

    with patch("app.services.extraction_engine.ocr_engine.HybridOcrEngine.extract") as mock_extract, \
         patch("app.services.extraction_engine.pdf_classifier.PdfClassifier.classify") as mock_classify, \
         patch("fitz.open") as mock_fitz_open, \
         patch("app.services.extraction_engine.image_preprocessor.ImagePreprocessor.process") as mock_prep:

        mock_cls = MagicMock()
        mock_cls.document_type = "scanned"
        mock_classify.return_value = mock_cls

        mock_doc = MagicMock()
        mock_page = MagicMock()
        mock_page.get_text.return_value = ""
        mock_page.rect = MagicMock(width=800, height=1000)
        mock_doc.__len__.return_value = 1
        mock_doc.__getitem__.return_value = mock_page
        mock_fitz_open.return_value = mock_doc

        mock_prep.return_value = {"processed_images": ["p.png"]}

        from app.services.extraction_engine.models.document import OcrElement
        with patch("cv2.imread", return_value=np.zeros((1000, 800, 3))):
            mock_extract.return_value = {"elements": [
                OcrElement(text="Scanned", confidence=0.9, x=10, y=10, width=50, height=20, page_number=1, source="paddleocr")
            ]}
            doc = pipeline.process_document("dummy.pdf")

        assert len(doc.pages) > 0
        assert len(doc.pages[0].elements) > 0
        assert doc.pages[0].elements[0].source == "paddleocr"
        assert doc.pages[0].elements[0].source != "native"
        assert doc.pages[0].elements[0].confidence == 0.9

# F.1 legacy OCR -> confidence_avg != 0.85 sintético
def test_f_legacy_ocr_confidence_not_085():
    import sys

    mock_ocrmypdf_module = MagicMock()
    mock_pytesseract = MagicMock()

    with patch.dict(sys.modules, {
        "ocrmypdf": mock_ocrmypdf_module,
        "ocrmypdf.exceptions": MagicMock(),
        "pytesseract": mock_pytesseract
    }), patch("fitz.open") as mock_fitz_open:

        mock_doc = MagicMock()
        mock_doc.__len__.return_value = 1
        mock_page = MagicMock()
        mock_page.get_text.return_value = "" # trigger OCR
        mock_rect = MagicMock()
        mock_rect.width = 800
        mock_rect.height = 1000
        mock_rect.x0 = 0
        mock_rect.y0 = 0
        mock_rect.x1 = 800
        mock_rect.y1 = 1000
        mock_page.rect = mock_rect
        mock_page.find_tables.return_value.tables = []
        mock_doc.__iter__.return_value = iter([mock_page])

        # Use return_value to avoid StopIteration if called more than twice due to fallback
        mock_fitz_open.return_value = mock_doc

        result = process_pdf("dummy.pdf", force_ocr=True)

        # Test will assert result.ocr_used is True and confidence_avg is None (post-patch expectation)
        assert result.ocr_used is True
        assert result.confidence_avg is None
        assert result.confidence_avg is None

# F.2 native legacy extraction -> keeps native certainty
def test_f_native_legacy_extraction_keeps_native_certainty():
    with patch("fitz.open") as mock_fitz_open:
        mock_doc = MagicMock()
        mock_doc.__len__.return_value = 1
        mock_page = MagicMock()
        mock_page.get_text.return_value = "Digital text enough to prevent OCR " * 10
        mock_page.rect = MagicMock(width=800, height=1000)
        mock_page.rect.x0 = 0
        mock_page.rect.y0 = 0
        mock_page.rect.x1 = 800
        mock_page.rect.y1 = 1000

        mock_doc.__iter__.return_value = [mock_page]
        mock_fitz_open.return_value = mock_doc

        result = process_pdf("dummy.pdf", force_ocr=False)

        assert result.ocr_used is False
        assert result.confidence_avg == 1.0

# G. classification says flows_to_contract=True pero requirement status REVIEW_REQUIRED -> persisted flows_to_contract=False
def test_g_requirement_status_invariant():
    service = RequirementExtractionService()

    with patch("app.services.v6.extraction.service.classify_requirement") as mock_classify:
        mock_classify.return_value = {
            "status": "REVIEW_REQUIRED",
            "flows_to_contract": True,
            "category": "TECHNICAL"
        }

        mock_db = MagicMock()
        mock_extractor = MagicMock()
        mock_extractor.extract.return_value = MagicMock(items=[], requirements=[
            MagicMock(description="Req 1", requirement_type="TECHNICAL", confidence=0.9, value=None, mandatory=True, source_document="doc.pdf", source_page=1, source_fragment="t")
        ])

        service.extractor = mock_extractor
        service.process_text_and_propose(
            db=mock_db, case_id=1, user_id=1, tenant_id="t1", text="test", document_name="test.pdf", document_id=10
        )

        added_req = None
        for call in mock_db.add.call_args_list:
            arg = call[0][0]
            if isinstance(arg, CaseRequirementMatrix):
                added_req = arg
                break

        assert added_req is not None
        assert added_req.flows_to_contract is False

# H. REJECTED -> flows_to_contract=False
def test_h_rejected_never_flows_to_contract():
    # If the user rejects the requirement, it should be flows_to_contract = False
    service = RequirementExtractionService()

    with patch("app.services.v6.extraction.service.classify_requirement") as mock_classify:
        mock_classify.return_value = {
            "status": "REJECTED",
            "flows_to_contract": True,
            "category": "TECHNICAL"
        }

        mock_db = MagicMock()
        mock_extractor = MagicMock()
        mock_extractor.extract.return_value = MagicMock(items=[], requirements=[
            MagicMock(description="Req 1", requirement_type="TECHNICAL", confidence=0.9, value=None, mandatory=True, source_document="doc.pdf", source_page=1, source_fragment="t")
        ])

        service.extractor = mock_extractor
        service.process_text_and_propose(
            db=mock_db, case_id=1, user_id=1, tenant_id="t1", text="test", document_name="test.pdf", document_id=10
        )

        added_req = None
        for call in mock_db.add.call_args_list:
            arg = call[0][0]
            if isinstance(arg, CaseRequirementMatrix):
                added_req = arg
                break

        assert added_req is not None
        assert added_req.flows_to_contract is False

# I. API route update invariant
def test_i_api_cannot_enable_contract_flow_while_review_required():
    mock_db = MagicMock()
    mock_req = CaseRequirementMatrix(id=1, case_id=1, status="REVIEW_REQUIRED", flows_to_contract=False)
    mock_db.query().filter().first.return_value = mock_req

    update_data = RequirementUpdate(
        status="REVIEW_REQUIRED",
        flows_to_contract=True,
        reason="test"
    )

    mock_user = MagicMock()
    mock_user.id = 1
    mock_user.tenant_id = "t1"

    try:
        updated = update_requirement(
            case_id=1, req_id=1, update_data=update_data, case=MagicMock(), current_user=mock_user, db=mock_db
        )
        # Should not be True!
        assert updated.flows_to_contract is False
    except HTTPException:
        # API might reject it completely, which is also valid!
        pass

# J. OCR quality REVIEW_REQUIRED -> flows_to_contract=False
def test_j_ocr_review_required_blocks_contract_flow():
    service = RequirementExtractionService()

    with patch("app.services.v6.extraction.service.classify_requirement") as mock_classify:
        # Classification says VALIDATED and flows_to_contract = True
        mock_classify.return_value = {
            "status": "VALIDATED",
            "flows_to_contract": True,
            "category": "TECHNICAL"
        }

        mock_db = MagicMock()
        mock_extractor = MagicMock()
        mock_extractor.extract.return_value = MagicMock(items=[], requirements=[
            MagicMock(description="Req 1", requirement_type="TECHNICAL", confidence=0.9, value=None, mandatory=True, source_document="doc.pdf", source_page=1, source_fragment="t")
        ])

        service.extractor = mock_extractor

        mock_doc = UploadedDocument(id=10, ocr_status="REVIEW_REQUIRED")
        # Simular query(UploadedDocument).get(document_id)
        mock_db.query().get.return_value = mock_doc

        service.process_text_and_propose(
            db=mock_db, case_id=1, user_id=1, tenant_id="t1", text="test", document_name="test.pdf", document_id=10
        )

        added_req = None
        for call in mock_db.add.call_args_list:
            arg = call[0][0]
            if isinstance(arg, CaseRequirementMatrix):
                added_req = arg
                break

        assert added_req is not None
        assert added_req.flows_to_contract is False

def test_j_ocr_failed_blocks_contract_flow():
    service = RequirementExtractionService()

    with patch("app.services.v6.extraction.service.classify_requirement") as mock_classify:
        mock_classify.return_value = {
            "status": "VALIDATED",
            "flows_to_contract": True,
            "category": "TECHNICAL"
        }

        mock_db = MagicMock()
        mock_extractor = MagicMock()
        mock_extractor.extract.return_value = MagicMock(items=[], requirements=[
            MagicMock(description="Req 1", requirement_type="TECHNICAL", confidence=0.9, value=None, mandatory=True, source_document="doc.pdf", source_page=1, source_fragment="t")
        ])

        service.extractor = mock_extractor

        mock_doc = UploadedDocument(id=10, ocr_status="FAILED")
        mock_db.query().get.return_value = mock_doc

        service.process_text_and_propose(
            db=mock_db, case_id=1, user_id=1, tenant_id="t1", text="test", document_name="test.pdf", document_id=10
        )

        added_req = None
        for call in mock_db.add.call_args_list:
            arg = call[0][0]
            if isinstance(arg, CaseRequirementMatrix):
                added_req = arg
                break

        assert added_req is not None
        assert added_req.flows_to_contract is False

@patch("app.services.extraction_engine.ocr_engine.PaddleOCREngine.__init__", return_value=None)
@patch("app.services.extraction_engine.ocr_engine.TesseractEngine.__init__", return_value=None)
def test_k_rotation_bbox_transformation(mock_tess, mock_paddle):
    import fitz
    import numpy as np
    from app.services.extraction_engine.v2_pipeline import OCRV2Pipeline
    results = {}
    for rot in [0, 90, 180, 270]:
        doc = fitz.open()
        page = doc.new_page(width=800, height=1000)
        page.insert_text((100, 200), "HelloRotation", fontsize=20)
        page.set_rotation(rot)
        doc.save(f"/tmp/test_rot_{rot}.pdf")
        doc.close()

        pipeline = OCRV2Pipeline()
        with patch("app.services.extraction_engine.pdf_classifier.PdfClassifier.classify") as mock_classify, \
             patch("app.services.extraction_engine.image_preprocessor.ImagePreprocessor.process") as mock_prep:
            mock_cls = MagicMock()
            mock_cls.document_type = "digital"
            mock_classify.return_value = mock_cls
            mock_prep.return_value = {"processed_images": [f"/tmp/test_rot_{rot}.pdf"]}

            if rot in [90, 270]:
                target_img = np.zeros((800, 1000, 3))
            else:
                target_img = np.zeros((1000, 800, 3))

            with patch("cv2.imread", return_value=target_img):
                result_doc = pipeline.process_document(f"/tmp/test_rot_{rot}.pdf")

            elements = result_doc.pages[0].elements
            hello_el = next(e for e in elements if "HelloRotation" in e.text)

            doc2 = fitz.open(f"/tmp/test_rot_{rot}.pdf")
            p2 = doc2[0]
            words = p2.get_text("words")
            w_raw = next(w for w in words if "HelloRotation" in w[4])
            raw_rect = fitz.Rect(w_raw[:4])
            expected_rect = raw_rect * p2.rotation_matrix
            doc2.close()

            assert abs(hello_el.x - expected_rect.x0) < 5
            assert abs(hello_el.y - expected_rect.y0) < 5

def test_l_provenance_chain():
    from app.services.extraction_engine.adapters.structured_document_adapter import StructuredDocumentAdapter
    from app.services.extraction_engine.layout_analyzer import LayoutAnalyzer
    from app.services.extraction_engine.models.document import OcrElement, DocumentPage, StructuredDocument, DocumentBlock

    doc = StructuredDocument()
    el1 = OcrElement(text="NativeText", confidence=1.0, x=0, y=0, width=10, height=10, page_number=1, source="native")
    el2 = OcrElement(text="PaddleText", confidence=0.9, x=0, y=20, width=10, height=10, page_number=1, source="paddleocr")
    el3 = OcrElement(text="TessText", confidence=0.8, x=0, y=40, width=10, height=10, page_number=1, source="tesseract")

    doc.pages.append(DocumentPage(page_number=1, width=100, height=100, elements=[el1, el2, el3]))

    blocks = [
        DocumentBlock(type="section", original_text="NativeText", content="NativeText", confidence=1.0, page=1, bounding_box={"x":0,"y":0,"w":10,"h":10}),
        DocumentBlock(type="section", original_text="PaddleText", content="PaddleText", confidence=0.9, page=1, bounding_box={"x":0,"y":20,"w":10,"h":10}),
        DocumentBlock(type="section", original_text="TessText", content="TessText", confidence=0.8, page=1, bounding_box={"x":0,"y":40,"w":10,"h":10}),
    ]
    # Simulate that layout analyzer passes source if we implement it,
    # but for now we'll just test if the adapter keeps it. Actually, wait.
    # DocumentBlock doesn't even HAVE a source field right now.
    # We can inject it setattr style to test the adapter assuming we change DocumentBlock soon.
    setattr(blocks[0], "source", "native")
    setattr(blocks[1], "source", "paddleocr")
    setattr(blocks[2], "source", "tesseract")

    doc.blocks = blocks
    adapter = StructuredDocumentAdapter()
    sections = adapter.to_parsed_sections(case_id=1, structured_doc=doc, document_id=1)

    sources = [s.extraction_metadata.get("source") for s in sections]
    assert "native" in sources
    assert "paddleocr" in sources
    assert "tesseract" in sources

def test_m_processing_contract_flow():
    service = RequirementExtractionService()
    with patch("app.services.v6.extraction.service.classify_requirement") as mock_classify:
        mock_classify.return_value = {"status": "VALIDATED", "flows_to_contract": True, "category": "TECHNICAL"}
        mock_db = MagicMock()
        mock_extractor = MagicMock()
        mock_extractor.extract.return_value = MagicMock(items=[], requirements=[
            MagicMock(description="Req 1", requirement_type="TECHNICAL", confidence=0.9, value=None, mandatory=True, source_document="doc.pdf", source_page=1, source_fragment="t")
        ])
        service.extractor = mock_extractor
        mock_doc = UploadedDocument(id=10, ocr_status="PROCESSING")
        mock_db.query().get.return_value = mock_doc
        service.process_text_and_propose(
            db=mock_db, case_id=1, user_id=1, tenant_id="t1", text="test", document_name="test.pdf", document_id=10
        )
        added_req = None
        for call in mock_db.add.call_args_list:
            arg = call[0][0]
            if isinstance(arg, CaseRequirementMatrix):
                added_req = arg
                break
        assert added_req is not None
        assert added_req.flows_to_contract is False

# F.3 RED TEST NATIVE PRE-DESKEW
@patch("app.services.extraction_engine.ocr_engine.PaddleOCREngine.__init__", return_value=None)
@patch("app.services.extraction_engine.ocr_engine.TesseractEngine.__init__", return_value=None)
def test_native_page_uses_original_pre_deskew_image(mock_tess, mock_paddle):
    pipeline = OCRV2Pipeline()

    with patch("app.services.extraction_engine.pdf_classifier.PdfClassifier.classify") as mock_classify, \
         patch("fitz.open") as mock_fitz_open, \
         patch("app.services.extraction_engine.image_preprocessor.ImagePreprocessor.process") as mock_prep, \
         patch("cv2.imread") as mock_imread:

        mock_cls = MagicMock()
        mock_cls.document_type = "digital"
        mock_cls.page_results = [MagicMock(page_number=1, needs_ocr=False)]
        mock_classify.return_value = mock_cls

        import fitz
        mock_doc = MagicMock()
        mock_page = MagicMock()
        mock_page.rect = MagicMock(width=800, height=1000)
        mock_page.rotation_matrix = fitz.Matrix(1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
        mock_page.get_text.side_effect = lambda arg: [(100, 200, 300, 250, "Digital", 0, 0, 0)] if arg == "words" else ("Digital text")

        mock_doc.__len__.return_value = 1
        mock_doc.__getitem__.return_value = mock_page
        mock_fitz_open.return_value = mock_doc

        # Preprocessor returns two lists
        mock_prep.return_value = {
            "processed_images": ["processed_1.png"],
            "original_images": ["original_1.png"]
        }

        def mock_imread_impl(path):
            if "original" in path:
                return np.zeros((1000, 800, 3)) # Geometría A
            return np.zeros((2000, 1600, 3)) # Geometría B (processed)

        mock_imread.side_effect = mock_imread_impl

        doc = pipeline.process_document("dummy.pdf")

        assert len(doc.pages) > 0
        page = doc.pages[0]

        # La página native debe tener la Geometría A (1000x800)
        assert page.width == 800.0
        assert page.height == 1000.0

# F.3 CONTROL OCR
@patch("app.services.extraction_engine.ocr_engine.PaddleOCREngine.__init__", return_value=None)
@patch("app.services.extraction_engine.ocr_engine.TesseractEngine.__init__", return_value=None)
def test_ocr_page_keeps_processed_image(mock_tess, mock_paddle):
    pipeline = OCRV2Pipeline()

    with patch("app.services.extraction_engine.ocr_engine.HybridOcrEngine.extract") as mock_extract, \
         patch("app.services.extraction_engine.pdf_classifier.PdfClassifier.classify") as mock_classify, \
         patch("fitz.open") as mock_fitz_open, \
         patch("app.services.extraction_engine.image_preprocessor.ImagePreprocessor.process") as mock_prep, \
         patch("cv2.imread") as mock_imread:

        mock_cls = MagicMock()
        mock_cls.document_type = "scanned"
        mock_cls.page_results = [MagicMock(page_number=1, needs_ocr=True)]
        mock_classify.return_value = mock_cls

        mock_doc = MagicMock()
        mock_doc.__len__.return_value = 1
        mock_doc.__getitem__.return_value = MagicMock()
        mock_fitz_open.return_value = mock_doc

        mock_prep.return_value = {
            "processed_images": ["processed_1.png"],
            "original_images": ["original_1.png"]
        }

        def mock_imread_impl(path):
            if "original" in path:
                return np.zeros((1000, 800, 3)) # Geometría A
            return np.zeros((2000, 1600, 3)) # Geometría B (processed)

        mock_imread.side_effect = mock_imread_impl

        mock_extract.return_value = {"elements": []}

        doc = pipeline.process_document("dummy.pdf")

        assert len(doc.pages) > 0
        page = doc.pages[0]

        # La página OCR debe tener la Geometría B (2000x1600)
        assert page.width == 1600.0
        assert page.height == 2000.0
