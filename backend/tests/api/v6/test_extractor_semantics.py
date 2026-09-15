import pytest
from app.services.v6.extraction.deterministic_extractor import DeterministicRequirementExtractor

@pytest.fixture
def extractor():
    return DeterministicRequirementExtractor()

def test_noise_rejection(extractor):
    noise_examples = [
        "N° DE PEDIDO DE COMPRA SIGA: 0255",
        "FECHA Chachapoyas, 03 de agosto del 2026",
        "DIRECCION DE ADMINISTRACION DIRECCIÓN REGIONAL AGRARIA",
        "Actividad Operativa",
        "Meta Presupuestaria",
        "Descripción del CCMN",
        "ADQUISICION DE UTILES DE OFICINA",
        "Denominación de la",
        "FINALIDAD PÚBLICA (obligatorio)",
        "ESPECIFICACIONES TECNICAS PARA LA CONTRATACION DE BIENES EN GENERAL",
        "1. ENTIDAD CONVOCANTE",
        "2. OBJETO DE LA CONTRATACIÓN",
        "Pág. 1 de 5",
        "Firma del responsable",
        "Elaborado por:"
    ]
    for text in noise_examples:
        candidates = extractor.extract(text, "test.pdf")
        assert len(candidates) == 0, f"Failed: Noise '{text}' was extracted"

def test_valid_requirements_retention(extractor):
    valid_examples = [
        "El proveedor deberá entregar los bienes en un plazo máximo de 30 días calendario.",
        "El contratista está obligado a reponer productos defectuosos.",
        "Se requiere contar con certificación ISO 9001.",
        "El equipo debe operar a 220 V.",
        "Los bienes deben ser entregados en el almacén central.",
        "El postor deberá acreditar experiencia en bienes similares.",
        "La empresa garantizará el correcto funcionamiento por un año.",
        "El personal técnico debe tener capacitación comprobada.",
        "El producto deberá cumplir con las normas técnicas vigentes.",
        "EL PROVEEDOR DEBERÁ ENTREGAR LOS BIENES EN SUS CAJAS ORIGINALES."  # Uppercase requirement
    ]
    for text in valid_examples:
        candidates = extractor.extract(text, "test.pdf")
        assert len(candidates) > 0, f"Failed: Valid requirement '{text}' was rejected"

def test_line_reconstruction(extractor):
    fragmented_texts = [
        (
            "La adquisición de materiales de oficina se enfoca en garantizar que el\n"
            "personal administrativo cuente con los insumos necesarios.", 1
        ),
        (
            "El proveedor deberá asegurar que la entrega se realice\n"
            "dentro del horario de atención establecido.", 1
        ),
        (
            "Se requiere que todos los equipos\n"
            "sean de marca reconocida y cuenten con\n"
            "soporte técnico local.", 1
        ),
        (
            "El postor deberá acreditar la experiencia\n"
            "mediante copias simples de contratos u órdenes.", 1
        ),
        (
            "La garantía mínima será de 12 meses,\n"
            "contados a partir de la fecha de conformidad.", 1
        )
    ]
    for text, expected_count in fragmented_texts:
        candidates = extractor.extract(text, "test.pdf")
        assert len(candidates) == expected_count

def test_technical_attributes(extractor):
    attributes_text = (
        "- Capacidad mínima: 500 L\n"
        "- Material: acero inoxidable\n"
        "- Voltaje: 220 V\n"
        "- Frecuencia: 60 Hz\n"
        "- Garantía: 2 años\n"
        "- Diámetro: 50 mm"
    )
    candidates = extractor.extract(attributes_text, "test.pdf")
    assert len(candidates) == 6

def test_finalidad_publica_header(extractor):
    # Tests that the header is rejected, but the actual requirement following it is retained
    text = (
        "FINALIDAD PÚBLICA\n"
        "La presente contratación tiene por finalidad garantizar el abastecimiento.\n"
        "El proveedor deberá entregar los bienes en un plazo máximo de 30 días."
    )
    candidates = extractor.extract(text, "test.pdf")
    # 'FINALIDAD PÚBLICA' should be rejected.
    # 'La presente contratación...' doesn't have required keywords, so it might be rejected.
    # 'El proveedor deberá entregar...' must be extracted.
    assert any("deberá entregar" in c.description for c in candidates)
    assert not any(c.description == "FINALIDAD PÚBLICA" for c in candidates)

def test_metrics(extractor):
    corpus = [
        ("El proveedor deberá entregar los bienes en un plazo máximo de 30 días calendario.", True),
        ("Capacidad mínima: 500 L", True),
        ("Material: acero inoxidable AISI 304", True),
        ("Garantía mínima: 12 meses", True),
        ("El equipo debe operar a 220 V.", True),
        ("El postor deberá acreditar experiencia en bienes similares.", True),
        ("Diámetro: 50 mm", True),
        ("Los bienes deben ser entregados en el almacén central.", True),
        ("Se requiere contar con certificación ISO 9001.", True),
        ("EL PROVEEDOR DEBERÁ ENTREGAR LOS BIENES EN SUS CAJAS ORIGINALES.", True),
        ("N° DE PEDIDO DE COMPRA SIGA: 0255", False),
        ("FECHA Chachapoyas, 03 de agosto del 2026", False),
        ("DIRECCION DE ADMINISTRACION DIRECCIÓN REGIONAL AGRARIA", False),
        ("Actividad Operativa", False),
        ("Meta Presupuestaria", False),
        ("Descripción del CCMN", False),
        ("ADQUISICION DE UTILES DE OFICINA", False),
        ("Denominación de la", False),
        ("FINALIDAD PÚBLICA (obligatorio)", False),
        ("ESPECIFICACIONES TECNICAS PARA LA CONTRATACION DE BIENES EN GENERAL", False)
    ]

    tp = fp = tn = fn = 0
    for text, should_extract in corpus:
        candidates = extractor.extract(text, "test.pdf")
        extracted = len(candidates) > 0
        if extracted and should_extract:
            tp += 1
        elif extracted and not should_extract:
            fp += 1
        elif not extracted and not should_extract:
            tn += 1
        elif not extracted and should_extract:
            fn += 1

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0

    assert precision >= 0.90, f"Precision {precision:.2f} is below 0.90"
    assert recall >= 0.85, f"Recall {recall:.2f} is below 0.85"
