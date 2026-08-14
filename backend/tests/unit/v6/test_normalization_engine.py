from app.services.v6.engines.normalization_engine import NormalizationEngine

def test_normalization_engine_numbers():
    res = NormalizationEngine.normalize_value("diez dias calendario")
    assert "10" in res
    assert "diez" not in res
    
def test_normalization_engine_preserves_unmapped():
    res = NormalizationEngine.normalize_value("cincuenta mesas")
    assert "cincuenta mesas" in res # since cincuenta is not in the basic map yet
