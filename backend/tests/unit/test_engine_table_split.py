import pytest
from unittest.mock import MagicMock
from app.services.ocr.engine import _extract_page_structure
from app.schemas.document import BBox

def test_table_split_by_empty_rows_and_spatial_distance():
    # Mocking fitz.Page and pdfplumber

    class MockRow:
        def __init__(self, bbox, cells):
            self.bbox = bbox
            self.cells = cells

    class MockTable:
        def __init__(self, rows, bbox):
            self.rows = rows
            self.bbox = bbox

        def extract(self):
            return [r.cells for r in self.rows]
    # Create a table where the first two rows are close together (Table A)
    # Then an empty row
    # Then a row far away (Table B)
    # Then another row close to Table B
    mock_table = MockTable(
    rows=[
        MockRow((10, 10, 100, 20), ["H1", "H2", "H3"]),
        MockRow((10, 20, 100, 30), ["V1", "V2", "V3"]),
        MockRow((10, 30, 100, 40), ["", "", ""]),
        MockRow((10, 80, 100, 90), ["H4", "H5", "H6"]),
        MockRow((10, 90, 100, 100), ["V4", "V5", "V6"]),
    ],
    bbox=(10, 10, 100, 100),
    )

    mock_pdfplumber_page = MagicMock()
    mock_pdfplumber_page.width = 500
    mock_pdfplumber_page.height = 500
    mock_pdfplumber_page.crop.return_value.find_tables.return_value = [mock_table]

    mock_fitz_page = MagicMock()
    mock_fitz_page.rect = MagicMock(x0=0, y0=0, x1=500, y1=500, width=500, height=500)
    mock_fitz_page.get_text.return_value = []

    # Patch pdfplumber using sys.modules since it is dynamically imported
    import sys
    mock_pdfplumber = MagicMock()
    mock_pdfplumber.open.return_value.__enter__.return_value.pages = [mock_pdfplumber_page]
    
    with pytest.MonkeyPatch.context() as m:
        m.setitem(sys.modules, "pdfplumber", mock_pdfplumber)
        
        # Act
        structured_page = _extract_page_structure(mock_fitz_page, 1, "scanned", "dummy.pdf")
        
        # Assert
        tables = [b for b in structured_page.blocks if b.type == "TABLE"]
        assert len(tables) == 2, f"Expected 2 tables, got {len(tables)}"
        
        table_a = tables[0].table_data
        assert table_a.row_count == 2
        assert table_a.rows[0].cells[0].text == "H1"
        
        table_b = tables[1].table_data
        assert table_b.row_count == 2
        assert table_b.rows[0].cells[0].text == "H4"
