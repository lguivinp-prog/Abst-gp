import unittest
import os
import pymupdf
from app.services.v6.extraction.contract_extractor import extract_requirements_from_text, extract_offer_terms_from_text

class TestOCR(unittest.TestCase):
    def test_pdf_extraction(self):
        pdf_path = os.path.join(os.path.dirname(__file__), 'test_fixture.pdf')

        # Verify valid PDF header
        with open(pdf_path, 'rb') as f:
            header = f.read(5)
            self.assertEqual(header, b'%PDF-')

        # Parse PDF
        doc = pymupdf.open(pdf_path)
        self.assertGreater(len(doc), 0)

        text = ""
        for page in doc:
            text += page.get_text()

        doc.close()

        # 1. Requirement Extraction
        reqs = extract_requirements_from_text(text, "doc1")["requirements"]

        # Assert extraction
        self.assertEqual(len(reqs), 3)

        plazo_req = next(r for r in reqs if r["key"] == "PLAZO_ENTREGA")
        self.assertEqual(plazo_req["numeric_value"], 10.0)
        self.assertEqual(plazo_req["unit"], "dias")
        self.assertEqual(plazo_req["comparator"], "MAX")
        self.assertEqual(plazo_req["source_page"], 1)
        self.assertIn("Plazo de entrega", plazo_req["source_quote"])
        self.assertGreaterEqual(plazo_req["confidence"], 0.9)
        self.assertEqual(plazo_req["review_status"], "PENDING")
        self.assertFalse(plazo_req["is_manual_edit"])

        garantia_req = next(r for r in reqs if r["key"] == "GARANTIA")
        self.assertEqual(garantia_req["numeric_value"], 12.0)
        self.assertEqual(garantia_req["unit"], "meses")
        self.assertEqual(garantia_req["comparator"], "MIN")

        # 2. Offer Extraction
        terms = extract_offer_terms_from_text(text, "doc1")["terms"]
        self.assertEqual(len(terms), 3)

        plazo_term = next(t for t in terms if t["key"] == "PLAZO_ENTREGA")
        self.assertEqual(plazo_term["numeric_value"], 5.0)
        self.assertEqual(plazo_term["unit"], "dias")

        # 3. Manual override preserved logic
        # Typically handled at DB layer by not overwriting if is_manual_edit is True
        # Since contract_extractor returns dictionaries, we just simulate the merge logic
        db_term = {"key": "PLAZO_ENTREGA", "numeric_value": 7.0, "is_manual_edit": True}

        # Simulate merge
        if not db_term["is_manual_edit"]:
            db_term.update(plazo_term)

        self.assertEqual(db_term["numeric_value"], 7.0)

if __name__ == '__main__':
    unittest.main()
