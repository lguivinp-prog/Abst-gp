import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
from app.services.ocr.cleaner import clean_ocr_text

def test_clean_ocr_text_regex():
    """
    Verifica que la normalización de viñetas funciona sin generar la excepción:
    're.error: look-behind requires fixed-width pattern'
    """
    test_text = """
5.1 Características
Los bienes requeridos incluyen:

+ viñeta uno

o viñeta dos

- viñeta tres

* viñeta cuatro

• viñeta cinco

a) literal a
b) literal b

El color o tamaño puede variar.
"""
    cleaned = clean_ocr_text(test_text)
    
    print(cleaned)
    # Validar que no hay excepciones
    assert "- viñeta uno" in cleaned
    assert "- viñeta dos" in cleaned
    assert "- viñeta tres" in cleaned
    assert "- viñeta cuatro" in cleaned
    assert "- viñeta cinco" in cleaned
    assert "a) literal a" in cleaned
    assert "b) literal b" in cleaned
    assert "color o tamaño" in cleaned # La 'o' en oración no se rompe
    print("ALL TESTS PASSED")

if __name__ == "__main__":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    test_clean_ocr_text_regex()
