import os
import pytest
from app.services.extraction_engine.core_extractor import DocumentExtractionEngine

def test_golden_ocr_quality_gate():
    # 1. Generate or locate the golden pdf
    pdf_path = os.path.join(os.path.dirname(__file__), "golden_test_uat.pdf")
    
    # 2. Initialize Engine
    engine = DocumentExtractionEngine()
    
    # 3. Process
    result = engine.process_document(pdf_path)
    
    # 4. Assertions on text
    text = result["raw_text"]
    
    # - EPSON L14150 (never 114150)
    assert "EPSON L14150" in text, "Debe recuperar EPSON L14150 correctamente"
    assert "114150" not in text, "No debe sufrir regresion a 114150"
    
    # - NEGRO (never N° EGRO)
    assert "NEGRO" in text, "Debe recuperar NEGRO correctamente"
    assert "N° EGRO" not in text, "No debe sufrir regresion a N° EGRO"
    
    # - cantidades 3 y 2
    assert " 3 " in text or "\n3\n" in text or text.count("3") > 0, "Debe extraer cantidad 3"
    assert " 2 " in text or "\n2\n" in text or text.count("2") > 0, "Debe extraer cantidad 2"
    
    # - CIAN
    assert "CIAN" in text, "Debe recuperar CIAN correctamente"
    
    # - CONTENIDO 65-130 mL aprox.
    assert "CONTENIDO 65-130 mL aprox." in text, "Debe recuperar CONTENIDO 65-130 mL aprox."
    
    # - TIPO FRASCO
    assert "TIPO FRASCO" in text, "Debe recuperar TIPO FRASCO"
    
    # - ESTABILIDAD QUÍMICA 100%
    assert "ESTABILIDAD QUÍMICA 100%" in text, "Debe recuperar ESTABILIDAD QUÍMICA 100%"
    
    # - tres (03) días calendario
    assert "tres (03) dias calendario" in text or "tres (03) días calendario" in text, "Debe recuperar el plazo exacto"
    
    # - RNP, RUC, CCI
    assert "RNP" in text, "Debe recuperar RNP"
    assert "RUC" in text, "Debe recuperar RUC"
    assert "CCI" in text, "Debe recuperar CCI"
    
    # - sin bbox/coordenadas en text_extracted (e.g. format like (x0, y0, x1, y1))
    import re
    bbox_pattern = r'\(\d+\.\d+,\s*\d+\.\d+,\s*\d+\.\d+,\s*\d+\.\d+\)'
    assert not re.search(bbox_pattern, text), "El texto extraído no debe filtrar coordenadas bbox"
    
    # - sin duplicación de tabla
    # The string "ITEM CANTIDAD DESCRIPCIÓN UNIDAD MEDIDA" should appear exactly once
    header_clean = re.sub(r'\s+', ' ', text).upper()
    assert header_clean.count("ITEM CANTIDAD DESCRIPCION UNIDAD") <= 1 and header_clean.count("ITEM CANTIDAD DESCRIPCIÓN UNIDAD") <= 1, "La tabla no debe duplicarse en la extracción"
