from app.services.comparison_engine.matcher import ComparisonMatcher
import json

sections = [
    {'id': 1, 'text': 'El equipo debe tener coincidencia textual directa.', 'page': 1},
    {'id': 2, 'text': 'Motor eléctrico de 10 hp de potencia.', 'page': 1},
    {'id': 3, 'text': 'Motor eléctrico con potencia de 15 hp', 'page': 1},
    {'id': 4, 'text': 'Peso del equipo de 10 kg', 'page': 1},
    {'id': 5, 'text': 'Nada que ver con lo buscado.', 'page': 1},
    {'id': 6, 'text': 'Esta es una sección extremadamente larga. ' * 50 + 'Aquí está la coincidencia perdida. ' + 'Sigue la sección inútil. ' * 50, 'page': 2},
    {'id': 7, 'text': 'Protección IP65 e ISO 9001.', 'page': 2}
]

matcher = ComparisonMatcher(quotation_sections=sections)

tests = [
    "coincidencia textual directa",
    "10 hp",
    "mínimo 10 hp",
    "10 hp", # vs 10 kg (will test behavior against section 4)
    "texto imposible de encontrar",
    "coincidencia perdida",
    "IP65",
]

for req in tests:
    candidates = matcher.find_candidates(req)
    print(f"\nRequisito: {req}")
    for c in candidates:
        print(f"  -> {c.evaluation_method.name} | Score: {c.similarity_score:.2f} | Text: {c.text[:50]}... | ReqVal: {c.required_numeric_value} | FoundVal: {c.found_numeric_value} | Unit: {c.numeric_unit}")
    if not candidates:
        print("  -> Ningún candidato encontrado.")

