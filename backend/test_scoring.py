from app.models.domain import EvaluationMethod, ComparisonResultStatus
from app.services.comparison_engine.matcher import MatchCandidate
from app.services.comparison_engine.scoring import ComparisonScorer

scorer = ComparisonScorer()

def run_test(name, req_text, candidates):
    res = scorer.evaluate(req_text, candidates)
    print(f"\n{name}")
    print(f"Req: '{req_text}'")
    status = res.status.name
    score = res.confidence_score
    reasoning = res.reasoning
    cand_text = res.selected_candidate.text if res.selected_candidate else "None"
    print(f"Status: {status} | Score: {score} | Candidate: '{cand_text}'\nReasoning: {reasoning}")

c1 = MatchCandidate(1, "el equipo de 10 hp", EvaluationMethod.EXACT_MATCH, 1.0)
run_test("1. Exact match sin negación", "10 hp", [c1])

c2 = MatchCandidate(1, "el equipo no incluye 10 hp", EvaluationMethod.EXACT_MATCH, 1.0)
run_test("2. Exact match dentro de una frase negativa", "10 hp", [c2])

c3 = MatchCandidate(1, "el motor es de 15 hp", EvaluationMethod.NUMERIC_MATCH, 0.9, required_numeric_value=10.0, found_numeric_value=15.0, numeric_unit="hp")
run_test("3. Mínimo 10 HP frente a 15 HP", "potencia mínimo 10 hp", [c3])

c4 = MatchCandidate(1, "el motor es de 5 hp", EvaluationMethod.NUMERIC_MATCH, 0.9, required_numeric_value=10.0, found_numeric_value=5.0, numeric_unit="hp")
run_test("4. Mínimo 10 HP frente a 5 HP", "potencia mínimo 10 hp", [c4])

c5 = MatchCandidate(1, "entrega en 20 días", EvaluationMethod.NUMERIC_MATCH, 0.9, required_numeric_value=30.0, found_numeric_value=20.0, numeric_unit="días")
run_test("5. Máximo 30 días frente a 20 días", "máximo 30 días", [c5])

c6 = MatchCandidate(1, "entrega en 45 días", EvaluationMethod.NUMERIC_MATCH, 0.9, required_numeric_value=30.0, found_numeric_value=45.0, numeric_unit="días")
run_test("6. Máximo 30 días frente a 45 días", "máximo 30 días", [c6])

c7 = MatchCandidate(1, "motor de 15 hp", EvaluationMethod.NUMERIC_MATCH, 0.9, required_numeric_value=10.0, found_numeric_value=15.0, numeric_unit="hp")
run_test("7. Valor 10 HP frente a 15 HP sin modificador", "10 hp", [c7])

c8 = MatchCandidate(1, "peso de 10 kg", EvaluationMethod.FUZZY_MATCH, 0.86) 
run_test("8. 10 HP frente a 10 kg", "10 hp", [c8])

c9 = MatchCandidate(1, "potencia requerida del equipo", EvaluationMethod.FUZZY_MATCH, 0.92)
run_test("9. Fuzzy 0.90 sin diferencias críticas", "potencia requirida del equipo", [c9])

c10 = MatchCandidate(1, "potencia requerida de 15 kw", EvaluationMethod.FUZZY_MATCH, 0.92)
run_test("10. Fuzzy 0.90 con números diferentes", "potencia requerida de 10 kw", [c10])

c11 = MatchCandidate(1, "texto un poco similar", EvaluationMethod.FUZZY_MATCH, 0.65)
run_test("11. Fuzzy 0.65", "texto nada similar", [c11])

c12 = MatchCandidate(1, "palabra aleatoria", EvaluationMethod.FUZZY_MATCH, 0.41)
run_test("12. Fuzzy 0.41 aleatorio", "potencia 10 hp", [c12])

c13_1 = MatchCandidate(1, "ofrecemos equipo de 15 hp", EvaluationMethod.NUMERIC_MATCH, 0.9, required_numeric_value=10.0, found_numeric_value=15.0, numeric_unit="hp")
c13_2 = MatchCandidate(2, "no incluye motor de 10 hp", EvaluationMethod.EXACT_MATCH, 1.0)
run_test("13. Candidatos contradictorios", "mínimo 10 hp", [c13_1, c13_2])

run_test("14. Lista vacía de candidatos", "10 hp", [])
