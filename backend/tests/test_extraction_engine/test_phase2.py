import pytest
import os
import cv2
import numpy as np
from unittest.mock import patch, MagicMock

from app.services.extraction_engine.pdf_classifier import PdfClassifier
from app.services.extraction_engine.image_preprocessor import ImagePreprocessor

class TestPdfClassifier:
    @patch("app.services.extraction_engine.pdf_classifier.fitz.open")
    def test_classify_digital(self, mock_fitz_open):
        mock_doc = MagicMock()
        mock_page = MagicMock()
        mock_page.get_text.return_value = "This is a digital page with a lot of text to cross the threshold."
        mock_page.get_images.return_value = []
        mock_doc.__len__.return_value = 2
        mock_doc.__getitem__.return_value = mock_page
        mock_fitz_open.return_value = mock_doc

        classifier = PdfClassifier(text_length_threshold=10)
        result = classifier.classify("dummy.pdf")

        assert result.document_type == "digital"
        assert result.pages == 2
        assert result.text_pages == 2
        assert result.image_pages == 0

    @patch("app.services.extraction_engine.pdf_classifier.fitz.open")
    def test_classify_scanned(self, mock_fitz_open):
        mock_doc = MagicMock()
        mock_page = MagicMock()
        mock_page.get_text.return_value = "  " # Empty text
        mock_page.get_images.return_value = [(1,)] # Has image
        mock_doc.__len__.return_value = 2
        mock_doc.__getitem__.return_value = mock_page
        mock_fitz_open.return_value = mock_doc

        classifier = PdfClassifier(text_length_threshold=10)
        result = classifier.classify("dummy.pdf")

        assert result.document_type == "scanned"
        assert result.pages == 2
        assert result.text_pages == 0
        assert result.image_pages == 2

    @patch("app.services.extraction_engine.pdf_classifier.fitz.open")
    def test_classify_hybrid(self, mock_fitz_open):
        mock_doc = MagicMock()
        
        page_digital = MagicMock()
        page_digital.get_text.return_value = "A lot of text here."
        
        page_scanned = MagicMock()
        page_scanned.get_text.return_value = ""
        
        mock_doc.__len__.return_value = 2
        mock_doc.__getitem__.side_effect = [page_digital, page_scanned]
        mock_fitz_open.return_value = mock_doc

        classifier = PdfClassifier(text_length_threshold=10)
        result = classifier.classify("dummy.pdf")

        assert result.document_type == "hybrid"
        assert result.pages == 2
        assert result.text_pages == 1
        assert result.image_pages == 1

class TestImagePreprocessor:
    @patch("app.services.extraction_engine.image_preprocessor.convert_from_path")
    def test_preprocessor_generates_images(self, mock_convert, tmp_path):
        from PIL import Image
        
        # Create a dummy image
        img = Image.new('RGB', (800, 600), color = 'white')
        mock_convert.return_value = [img, img]
        
        preprocessor = ImagePreprocessor(base_output_dir=str(tmp_path))
        result = preprocessor.process("doc123", "dummy.pdf")
        
        assert result["total_pages"] == 2
        assert len(result["original_images"]) == 2
        assert len(result["processed_images"]) == 2
        
        # Check files exist
        assert os.path.exists(result["original_images"][0])
        assert os.path.exists(result["processed_images"][0])
        
        # Check dimensions maintained (cv2 reads as H, W, C)
        proc_img = cv2.imread(result["processed_images"][0], cv2.IMREAD_GRAYSCALE)
        assert proc_img is not None
        assert proc_img.shape == (600, 800) # (Height, Width)
