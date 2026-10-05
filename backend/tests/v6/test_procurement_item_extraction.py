import pytest
from app.services.v6.extraction.deterministic_extractor import DeterministicRequirementExtractor

def test_extract_single_procurement_item():
    extractor = DeterministicRequirementExtractor()
    text = """3. CARACTERÍSTICAS TÉCNICAS DE LOS BIENES
ITEM CANTIDAD DESCRIPCIÓN UNIDAD MEDIDA
1 3 Tinta original para EPSON L14150 COD. REF. 504 - NEGRO UNIDAD
"""
    result = extractor.extract(text, source_document="doc.pdf")
    assert len(result.items) == 1
    assert result.items[0].item_number == "1"
    assert result.items[0].quantity == 3.0
    assert result.items[0].unit == "UNIDAD"
    assert "Tinta original" in result.items[0].description

def test_extract_multiple_procurement_items_table_format():
    extractor = DeterministicRequirementExtractor()
    text = """
1 3 Tinta original para EPSON L14150 COD. REF. 504 - NEGRO UNIDAD
2 2 Tinta original para EPSON L14150 COD. REF. 504 - CIAN UNIDAD
"""
    result = extractor.extract(text, source_document="doc.pdf")
    assert len(result.items) == 2

    assert result.items[0].item_number == "1"
    assert result.items[0].quantity == 3.0
    assert result.items[0].unit == "UNIDAD"
    assert "NEGRO" in result.items[0].description

    assert result.items[1].item_number == "2"
    assert result.items[1].quantity == 2.0
    assert result.items[1].unit == "UNIDAD"
    assert "CIAN" in result.items[1].description

def test_extract_handles_multiline_shredded_table():
    extractor = DeterministicRequirementExtractor()
    text = """
1
3
Tinta original para EPSON L14150
COD. REF. 504 - NEGRO
TIPO FRASCO
UNIDAD
2
2
Tinta original para EPSON L14150
COD. REF. 504 - CIAN
TIPO FRASCO
UNIDAD
"""
    result = extractor.extract(text, source_document="doc.pdf")
    assert len(result.items) == 2
    assert result.items[0].item_number == "1"
    assert result.items[0].quantity == 3.0
    assert result.items[0].unit == "UNIDAD"
    assert "COD. REF. 504 - NEGRO" in result.items[0].description

    assert result.items[1].item_number == "2"
    assert result.items[1].quantity == 2.0
    assert result.items[1].unit == "UNIDAD"
    assert "COD. REF. 504 - CIAN" in result.items[1].description

def test_extract_handles_frasco_units():
    extractor = DeterministicRequirementExtractor()
    text = """
10
5
Solucion Salina
500
ML
FRASCO
11
1
Alcohol
200
ML
FRASCOS
"""
    result = extractor.extract(text, source_document="doc.pdf")
    assert len(result.items) == 2
    assert result.items[0].item_number == "10"
    assert result.items[0].quantity == 5.0
    assert result.items[0].unit == "FRASCO"
    assert "Solucion Salina" in result.items[0].description

    assert result.items[1].item_number == "11"
    assert result.items[1].quantity == 1.0
    assert result.items[1].unit == "FRASCOS"
    assert "Alcohol" in result.items[1].description

def test_malformed_block_no_invented_items():
    extractor = DeterministicRequirementExtractor()
    # Number, number, but no unit within 25 lines
    text = "\n".join(["1", "5", "Just some description"] + ["noise"] * 30)
    result = extractor.extract(text, source_document="doc.pdf")
    assert len(result.items) == 0

def test_numeric_noise_in_narrative_text():
    extractor = DeterministicRequirementExtractor()
    text = "We need 5 units of product 123. It should be delivered in 2 days."
    result = extractor.extract(text, source_document="doc.pdf")
    assert len(result.items) == 0


def test_cross_item_boundary_protection():
    extractor = DeterministicRequirementExtractor()
    # Item 1 has no unit before item 2 starts.
    text = """
1
3
Item 1 without unit
2
5
Item 2 with unit
FRASCO
"""
    result = extractor.extract(text, source_document="doc.pdf")
    # Item 1 should be discarded or kept without unit? 
    # Current logic discards it if unit is not found.
    # What's important is that Item 2 is NOT absorbed by Item 1.
    # So we should get 1 item (Item 2)
    assert len(result.items) == 1
    assert result.items[0].item_number == "2"
    assert result.items[0].quantity == 5.0
    assert result.items[0].unit == "FRASCO"
    assert "Item 2 with unit" in result.items[0].description
    
def test_no_items_preserves_zero_state():
    extractor = DeterministicRequirementExtractor()
    text = """1. ALCANCE
El contratista deberá proveer los equipos en un plazo de 5 días.
No hay tabla de items aquí."""
    result = extractor.extract(text, source_document="doc.pdf")
    assert len(result.items) == 0
    assert len(result.requirements) > 0
