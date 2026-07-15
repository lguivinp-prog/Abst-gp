import pytest
from app.services.extraction.document_extraction_agent import DocumentExtractionAgent

@pytest.fixture
def agent():
    return DocumentExtractionAgent()

def test_protect_ruc(agent):
    text = "El proveedor con RUC 20123456789 debe entregar el bien."
    normalized, corrections = agent._apply_corrections(text)
    assert "20123456789" in normalized

def test_protect_price(agent):
    text = "El costo es de S/ 5,000.00 inc IGV."
    normalized, corrections = agent._apply_corrections(text)
    assert "S/ 5,000.00" in normalized

def test_protect_quantity(agent):
    text = "Se requieren 10 unidades de laptops."
    normalized, corrections = agent._apply_corrections(text)
    assert "10 unidades" in normalized

def test_protect_date(agent):
    text = "La fecha de entrega es el 15/10/2024."
    normalized, corrections = agent._apply_corrections(text)
    assert "15/10/2024" in normalized

def test_protect_brand(agent):
    text = "Se requiere modelo XPS_15 con urgencia."
    normalized, corrections = agent._apply_corrections(text)
    assert "modelo XPS_15" in normalized

def test_remove_headers(agent):
    pages = ["GOBIERNO REGIONAL DE LIMA\n\nI. FINALIDAD PÚBLICA\n\nEl objetivo es..."]
    cleaned, excluded = agent.remove_repeated_headers_footers(pages)
    assert "GOBIERNO REGIONAL" not in cleaned
    assert "I. FINALIDAD PÚBLICA" in cleaned

def test_remove_page_numbers(agent):
    pages = ["I. FINALIDAD PÚBLICA\n\nEl objetivo es...\nPágina 1 de 10"]
    cleaned, excluded = agent.remove_repeated_headers_footers(pages)
    assert "Página 1 de 10" not in cleaned

def test_dictionary_replacement(agent):
    agent.dictionary = {"conpu tadora": "computadora"}
    text = "La conpu tadora es rápida."
    normalized, corrections = agent._apply_corrections(text)
    assert "computadora" in normalized
    assert "conpu tadora" not in normalized

def test_hyphen_join(agent):
    text = "La computa-\ndora es nueva."
    normalized, corrections = agent._apply_corrections(text)
    assert "computadora" in normalized

def test_structural_breaks(agent):
    # This is handled in process(), but we can test the regexes indirectly via section splitting or manually.
    text = ["I. FINALIDAD PÚBLICA\nEl requerimiento (obligatorio) es necesario."]
    results = agent.process(text, "bienes")
    assert len(results) >= 1
    # Check if (obligatorio) was removed
    assert "(obligatorio)" not in results[0].cleaned_text
