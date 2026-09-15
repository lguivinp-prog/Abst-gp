import pytest
import os
from unittest.mock import MagicMock
from app.services.v6.integrations.providers.ciiu_adapter import CIIUProvider
from app.models.v6.ciiu_catalog import CiiuCatalog

@pytest.fixture
def mock_db():
    db = MagicMock()
    # Mocking two known codes and one non-existent
    def mock_filter_by(codigo, activo):
        if codigo == "0000":
            return MagicMock(first=lambda: CiiuCatalog(codigo="0000", descripcion="TEST CODE", version="1", fuente="TEST", activo=True))
        if codigo == "6201":
            return MagicMock(first=lambda: CiiuCatalog(codigo="6201", descripcion="Actividades de programación informática", version="1", fuente="INEI", activo=True))
        return MagicMock(first=lambda: None)
    
    db.query.return_value.filter_by.side_effect = mock_filter_by
    return db

def test_ciiu_adapter_test_env(mock_db, monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    provider = CIIUProvider()
    
    # 1. Código conocido -> descripción oficial exacta
    res1 = provider.validate(mock_db, "0000", "some keywords")
    assert res1.status == "PASSED"
    assert res1.payload["descripcion"] == "TEST CODE"
    
    # 2. Otro código conocido distinto -> descripción correcta
    res2 = provider.validate(mock_db, "6201", "doesn't matter what words")
    assert res2.status == "PASSED"
    assert res2.payload["descripcion"] == "Actividades de programación informática"
    
    # 3. Código inexistente -> no inventa resultado
    res3 = provider.validate(mock_db, "9999", "words")
    assert res3.status == "WARNING"
    assert res3.payload["certeza"] == "UNKNOWN"
    assert "no encontrado" in res3.payload["msg"]
    
    # 4. Código malformado (vacío) -> error/controlado
    res4 = provider.validate(mock_db, "", "words")
    assert res4.status == "MANUAL_REQUIRED"
    assert "Missing" in res4.payload["error"]
    
    # 5. No fuzzy matching -> It strictly matches the DB output regardless of keywords

def test_ciiu_adapter_runtime_env(mock_db, monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    provider = CIIUProvider()
    
    # 6. Runtime no utiliza test fixture (debe devolver NO_DISPONIBLE_API)
    res = provider.validate(mock_db, "6201", "words")
    assert res.status == "NO_DISPONIBLE_API"
    assert "no disponible" in res.payload["error"]
