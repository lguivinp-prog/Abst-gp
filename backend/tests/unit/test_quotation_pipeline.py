import pytest
from app.services.extraction.supplier_extractor import extract_supplier_info
from app.services.extraction.product_extractor import extract_products_basic
from app.services.extraction.condition_extractor import extract_conditions

def test_extract_ruc_and_email():
    text = "COTIZACIÓN N° 001\nRUC: 20123456789\nEmpresa de prueba\nContacto: ventas@prueba.com\nTeléfono: 987654321"
    info = extract_supplier_info(text)
    
    assert info["supplier_ruc"]["value"] == "20123456789"
    assert info["supplier_ruc"]["confidence"] == 1.0
    assert info["supplier_email"]["value"] == "ventas@prueba.com"
    assert info["supplier_phone"]["value"] == "987654321"

def test_extract_amounts():
    text = "Total a pagar: S/ 1,500.50\nGracias por su compra."
    info = extract_products_basic(text)
    
    assert info["total_price"]["value"] == 1500.50
    assert info["currency"]["value"] == "PEN"
    
def test_extract_amounts_usd():
    text = "El importe es USD 450.00."
    info = extract_products_basic(text)
    
    assert info["total_price"]["value"] == 450.0
    assert info["currency"]["value"] == "USD"

def test_extract_conditions():
    text = "Condición de pago: 30 días\nTiempo de entrega: 15 días calendario\nGarantía: 12 meses"
    info = extract_conditions(text)
    
    assert "30 días" in info["payment_condition"]["value"]
    assert "15 días" in info["delivery_term"]["value"]
    assert "12 meses" in info["warranty_term"]["value"]
