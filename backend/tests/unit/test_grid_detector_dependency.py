import sys
import importlib
import pytest
from unittest.mock import patch

def test_grid_detector_optional_import_no_pytesseract():
    """
    Simula que pytesseract NO est instalado (lanza ImportError al importar)
    y verifica que grid_detector haga una degradacin elegante y no rompa el sistema.
    """
    # 1. Asegurar estado limpio
    if 'pytesseract' in sys.modules:
        del sys.modules['pytesseract']
    if 'backend.app.services.ocr.grid_detector' in sys.modules:
        del sys.modules['app.services.ocr.grid_detector']

    import builtins
    original_import = builtins.__import__

    def mock_import(name, *args, **kwargs):
        if name == 'pytesseract':
            raise ImportError("Simulated missing pytesseract")
        return original_import(name, *args, **kwargs)

    try:
        builtins.__import__ = mock_import

        # 2. Verificar que se puede importar sin pytesseract
        from app.services.ocr import grid_detector
        importlib.reload(grid_detector)

        # 3. Comprobar comportamiento interno de grid_detector
        assert getattr(grid_detector, 'pytesseract', object) is None, "pytesseract fallback debe ser None"
        assert hasattr(grid_detector, 'Output'), "Clase Output fallback debe existir"
        assert getattr(grid_detector.Output, 'DICT', None) == "dict", "Output.DICT fallback debe existir"

    finally:
        # Restaurar entorno
        builtins.__import__ = original_import
        if 'app.services.ocr.grid_detector' in sys.modules:
            del sys.modules['app.services.ocr.grid_detector']
        # Recargar normal para no afectar a otros tests
        importlib.reload(importlib.import_module('app.services.ocr.grid_detector'))
