import pytest
from app.services.comparison.comparison_engine import compare_field, run_comparison
from app.services.comparison.comparison_status import ComparisonStatus

def test_compare_field_coincide():
    res = compare_field("delivery_term", "15 días", "15 días")
    assert res["status"] == ComparisonStatus.COINCIDE.value
    assert res["final_value"] == "15 días"

def test_compare_field_reemplazo_plazo():
    # Plazo entrega, regla dice quotation prevalece
    res = compare_field("delivery_term", "10 días", "7 días")
    assert res["status"] == ComparisonStatus.REEMPLAZADO_POR_COTIZACION.value
    assert res["final_value"] == "7 días"

def test_compare_field_reemplazo_garantia():
    # Garantía, regla dice quotation prevalece
    res = compare_field("warranty_term", "12 meses", "24 meses")
    assert res["status"] == ComparisonStatus.REEMPLAZADO_POR_COTIZACION.value
    assert res["final_value"] == "24 meses"

def test_compare_field_no_detectado_req():
    res = compare_field("warranty_term", "", "12 meses")
    assert res["status"] == ComparisonStatus.NO_DETECTADO_REQUERIMIENTO.value
    assert res["final_value"] == "12 meses"

def test_compare_field_revision_manual():
    # Ninguno tiene el dato
    res = compare_field("payment_condition", "", "")
    assert res["status"] == ComparisonStatus.REVISION_MANUAL.value
    assert res["final_value"] is None

def test_run_comparison_matrix():
    req_data = {
        "delivery_term": "10 días",
        "warranty_term": "12 meses",
        "payment_condition": ""
    }
    quot_data = {
        "delivery_term": "7 días",
        "warranty_term": "12 meses",
        "payment_condition": "Contado"
    }
    
    results = run_comparison(req_data, quot_data)
    assert len(results) == 5 # Todos los campos definidos en fields_to_compare
    
    # Check specific results
    delivery = next((r for r in results if r["field_name"] == "delivery_term"), None)
    assert delivery["status"] == ComparisonStatus.REEMPLAZADO_POR_COTIZACION.value
    assert delivery["final_value"] == "7 días"
    
    warranty = next((r for r in results if r["field_name"] == "warranty_term"), None)
    assert warranty["status"] == ComparisonStatus.COINCIDE.value
    
    payment = next((r for r in results if r["field_name"] == "payment_condition"), None)
    assert payment["status"] == ComparisonStatus.NO_DETECTADO_REQUERIMIENTO.value
    assert payment["final_value"] == "Contado"
