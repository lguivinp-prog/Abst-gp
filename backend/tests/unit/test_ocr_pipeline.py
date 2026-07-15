import os
import pytest
from app.services.ocr.cleaner import clean_ocr_text
from app.services.extraction.section_detector import extract_sections

def test_clean_ocr_text_hyphenated_words():
    raw_text = "Esta es una computado-\nras moderna."
    cleaned = clean_ocr_text(raw_text)
    assert "computadoras" in cleaned
    assert "computado-\nras" not in cleaned

def test_clean_ocr_text_unnecessary_newlines():
    raw_text = "Este es un párrafo que\nse dividió por el OCR."
    cleaned = clean_ocr_text(raw_text)
    assert "que se dividió" in cleaned

def test_clean_ocr_text_preserves_structure():
    raw_text = "Este es un párrafo\n1. Primer ítem\n5.1 Segundo ítem\na) Literal\n- Viñeta\nI. Romano"
    cleaned = clean_ocr_text(raw_text)
    assert "párrafo\n1." in cleaned
    assert "ítem\n5.1" in cleaned
    assert "ítem\na)" in cleaned
    assert "Literal\n-" in cleaned
    assert "Viñeta\nI." in cleaned

def test_section_detector_basic():
    text = "I. FINALIDAD PÚBLICA\nAdquirir computadoras.\nII. ANTECEDENTES\nNo hay."
    sections = extract_sections(text, "bienes")
    assert len(sections) == 2
    assert sections[0].original_roman == "I"
    assert sections[0].title == "FINALIDAD PÚBLICA"
    assert sections[1].title == "ANTECEDENTES"

def test_section_detector_fuzzy_ocr_errors():
    text = "l. FlNALlDAD PUBLlCA\nAdquirir computadoras.\nll. ANTECEDENTEs\nNo hay."
    sections = extract_sections(text, "bienes")
    assert len(sections) == 2
    assert sections[0].title == "FINALIDAD PÚBLICA"
    assert sections[0].confidence_score > 0.7
    # OCR l -> I
    assert sections[0].original_roman == "I"
    assert sections[1].title == "ANTECEDENTES"

def test_section_detector_missed_sections():
    # Solo encuentra I y III
    text = "I. FINALIDAD PÚBLICA\nAdquirir computadoras.\nIII. OBJETIVO DE LA CONTRATACIÓN\nRenovar 10 computadoras."
    sections = extract_sections(text, "bienes")
    assert len(sections) == 2
    assert sections[0].original_roman == "I"
    assert sections[1].original_roman == "III"

def test_section_detector_review_status():
    # Título muy corrupto que apenas pasa el threshold o no es exacto
    text = "I. FANALIDOD PUBLACA\nAdquirir computadoras."
    sections = extract_sections(text, "bienes")
    assert len(sections) == 1
    assert sections[0].review_status == "pending_review"
    assert "baja confianza" in sections[0].warnings

def test_build_structure_blocks():
    from app.services.extraction.section_detector import build_structure_blocks
    text = "Un párrafo inicial.\n5.1 Un numeral.\nOtro párrafo\na) Un literal.\n- Viñeta"
    blocks = build_structure_blocks(text)
    assert len(blocks) == 5
    assert blocks[0]["type"] == "paragraph"
    assert blocks[1]["type"] == "numbered_item"
    assert blocks[1]["label"] == "5.1"
    assert blocks[2]["type"] == "paragraph"
    assert blocks[3]["type"] == "letter_item"
    assert blocks[3]["label"] == "a)"
    assert blocks[4]["type"] == "bullet_item"
    assert blocks[4]["label"] == "-"

def test_build_structure_blocks_mandatory_test_case():
    from app.services.extraction.section_detector import build_structure_blocks
    from app.services.ocr.cleaner import normalize_structural_breaks
    
    text = "5.1 Descripción y cantidad de los bienes Los bienes solicitados son los siguientes: Mandilón descartable 200 Unidad 5.2 Características técnicas Mandilón descartable no estéril, con longitud por debajo de las rodillas. 5.3 Embalaje y rotulado Los mandilones descartables deberán ser entregados en empaques adecuados. 5.4 Transporte El traslado de los bienes deberá realizarse en condiciones seguras."
    
    cleaned = normalize_structural_breaks(text)
    blocks = build_structure_blocks(cleaned)
    
    assert len(blocks) == 8
    
    assert blocks[0]["type"] == "subsection_title"
    assert blocks[0]["label"] == "5.1"
    
    assert blocks[1]["type"] == "paragraph"
    assert "Los bienes solicitados" in blocks[1]["text"]
    
    assert blocks[2]["type"] == "subsection_title"
    assert blocks[2]["label"] == "5.2"
    
    assert blocks[3]["type"] == "paragraph"
    assert "Mandilón descartable no estéril" in blocks[3]["text"]
    
    assert blocks[4]["type"] == "subsection_title"
    assert blocks[4]["label"] == "5.3"
    
    assert blocks[5]["type"] == "paragraph"
    assert "Los mandilones descartables" in blocks[5]["text"]
    
    assert blocks[6]["type"] == "subsection_title"
    assert blocks[6]["label"] == "5.4"
    
    assert blocks[7]["type"] == "paragraph"
    assert "El traslado de los bienes" in blocks[7]["text"]
