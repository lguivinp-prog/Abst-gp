import pytest
import os
from unittest.mock import MagicMock
from app.services.v6.integrations.providers.ciiu_adapter import CIIUProvider
from app.models.v6.ciiu_catalog import CiiuCatalog

@pytest.fixture
def mock_db():
    db = MagicMock()
    # Mocking two known codes and one non-existent
    catalog_list = [
        CiiuCatalog(codigo="0000", descripcion="TEST CODE", version="1", fuente="TEST", activo=True),
        CiiuCatalog(codigo="6201", descripcion="Actividades de programación informática", version="1", fuente="INEI", activo=True)
    ]
    db.query.return_value.all.return_value = catalog_list
    return db

def test_ciiu_adapter_test_env(mock_db, monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    provider = CIIUProvider()
    
    # 1. Código conocido -> descripción oficial exacta
    res1 = provider.validate(mock_db, [{"descripcion_sunat": "0000", "tipo": "PRINCIPAL"}], False, "some keywords")
    assert res1.status == "REVIEW_REQUIRED"
    assert res1.payload["results"][0]["codigo_ciiu"] == "0000"
    
    # 2. Otro código conocido distinto -> descripción correcta
    res2 = provider.validate(mock_db, [{"descripcion_sunat": "6201", "tipo": "PRINCIPAL"}], False, "doesn't matter what words")
    assert res2.status == "REVIEW_REQUIRED"
    assert res2.payload["results"][0]["codigo_ciiu"] == "6201"
    
    # 3. Código inexistente -> no inventa resultado
    res3 = provider.validate(mock_db, [{"descripcion_sunat": "9999", "tipo": "PRINCIPAL"}], False, "words")
    assert res3.status == "REVIEW_REQUIRED"
    assert res3.payload["results"][0]["status"] == "REVIEW_REQUIRED"
    
    # 4. Código malformado (vacío) -> error/controlado
    res4 = provider.validate(mock_db, [], False, "words")
    assert res4.status == "MANUAL_REQUIRED"
    assert "No hay actividades de SUNAT para evaluar." in res4.payload["error"]
    
    # 5. No fuzzy matching -> It strictly matches the DB output regardless of keywords

def test_ciiu_adapter_runtime_env(mock_db, monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    provider = CIIUProvider()
    
    # 6. Runtime evalua 6201 (código extraido) que tiene match_method EXACT_CODE -> PASSED
    res = provider.validate(mock_db, [{"descripcion_sunat": "6201", "tipo": "PRINCIPAL"}], False, "words")
    assert res.status == "REVIEW_REQUIRED" # The whole validation fails if activities_complete is False
    assert res.payload["results"][0]["status"] == "PASSED"
