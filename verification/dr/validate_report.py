#!/usr/bin/env python3
"""
Validador estructurado de informe JSON para DR Continuous Validation (Fase P10).
Reemplaza la evaluación frágil por grep con validación estricta del esquema y métricas.
"""

import sys
import json
from pathlib import Path
from datetime import datetime, timezone


def validate_dr_report(report_path: Path) -> int:
    print("==== DR DRILL METRICS ====")
    print(f"Validation Timestamp: {datetime.now(timezone.utc).isoformat()}")
    print(f"Target Report: {report_path}")

    # 1. Comprobar que el archivo exista
    if not report_path.is_file():
        print(f"ERROR: El archivo de informe '{report_path}' no existe o no es un archivo regular.", file=sys.stderr)
        print("DR DRILL OUTCOME: FAILED", file=sys.stderr)
        return 1

    # 2. Leer y parsear como JSON válido
    try:
        content = report_path.read_text(encoding="utf-8")
        if not content.strip():
            print(f"ERROR: El archivo de informe '{report_path}' está vacío.", file=sys.stderr)
            print("DR DRILL OUTCOME: FAILED", file=sys.stderr)
            return 1
        data = json.loads(content)
    except json.JSONDecodeError as e:
        print(f"ERROR: El archivo '{report_path}' contiene JSON corrupto o inválido: {e}", file=sys.stderr)
        print("DR DRILL OUTCOME: FAILED", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"ERROR: Fallo inesperado leyendo '{report_path}': {e}", file=sys.stderr)
        print("DR DRILL OUTCOME: FAILED", file=sys.stderr)
        return 1

    if not isinstance(data, dict):
        print(f"ERROR: La raíz del informe JSON debe ser un objeto/dict, obtenido: {type(data).__name__}", file=sys.stderr)
        print("DR DRILL OUTCOME: FAILED", file=sys.stderr)
        return 1

    # 3. Validar estrictamente exitcode de pytest
    if "exitcode" not in data:
        print("ERROR: Clave obligatoria 'exitcode' no encontrada en el informe JSON.", file=sys.stderr)
        print("DR DRILL OUTCOME: FAILED", file=sys.stderr)
        return 1

    exitcode = data["exitcode"]
    if exitcode is None:
        print("ERROR: El campo 'exitcode' no puede ser nulo (null).", file=sys.stderr)
        print("DR DRILL OUTCOME: FAILED", file=sys.stderr)
        return 1

    if isinstance(exitcode, bool) or not isinstance(exitcode, int):
        print(f"ERROR: El campo 'exitcode' debe ser un entero estricto, obtenido: {type(exitcode).__name__} ({exitcode!r}).", file=sys.stderr)
        print("DR DRILL OUTCOME: FAILED", file=sys.stderr)
        return 1

    if exitcode != 0:
        print(f"ERROR: Pytest finalizó con exitcode no exitoso: {exitcode}", file=sys.stderr)
        print("DR DRILL OUTCOME: FAILED", file=sys.stderr)
        return 1

    # 4. Validar objeto summary
    summary = data.get("summary")
    if not isinstance(summary, dict):
        print("ERROR: Objeto 'summary' no encontrado o inválido en el informe JSON.", file=sys.stderr)
        print("DR DRILL OUTCOME: FAILED", file=sys.stderr)
        return 1

    # Extraer métricas con tipado estricto
    total = summary.get("total", 0)
    passed = summary.get("passed", 0)
    failed = summary.get("failed", 0)
    skipped = summary.get("skipped", 0)
    errors = summary.get("error", 0)
    duration = data.get("duration", 0.0)

    print(f"Total Duration (seconds): {duration:.2f}")
    print(f"Metrics: total={total}, passed={passed}, failed={failed}, skipped={skipped}, error={errors}, exitcode={exitcode}")

    # 5. Confirmar que se ejecutaron al menos las 15 pruebas esperadas
    MIN_EXPECTED_TESTS = 15
    if total < MIN_EXPECTED_TESTS:
        print(
            f"ERROR: Conteo de pruebas insuficiente. Esperado >= {MIN_EXPECTED_TESTS}, ejecutado={total}.",
            file=sys.stderr
        )
        print("DR DRILL OUTCOME: FAILED", file=sys.stderr)
        return 1

    # 6. Exigir cero pruebas fallidas, omitidas o con errores
    has_defects = False
    if failed != 0:
        print(f"ERROR: Se detectaron {failed} prueba(s) fallida(s).", file=sys.stderr)
        has_defects = True
    if skipped != 0:
        print(f"ERROR: Se detectaron {skipped} prueba(s) omitida(s). Prohibido omitir pruebas DR.", file=sys.stderr)
        has_defects = True
    if errors != 0:
        print(f"ERROR: Se detectaron {errors} error(es) en recolección/ejecución.", file=sys.stderr)
        has_defects = True

    # 7. Exigir passed == total
    if passed != total:
        print(f"ERROR: Conteo inconsistente: passed ({passed}) != total ({total}).", file=sys.stderr)
        has_defects = True

    if has_defects:
        print("DR DRILL OUTCOME: FAILED", file=sys.stderr)
        return 1

    print("DR DRILL OUTCOME: SUCCESS")
    return 0


def main():
    report_file = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("dr-validation-report.json")
    sys.exit(validate_dr_report(report_file))


if __name__ == "__main__":
    main()
