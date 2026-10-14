import json
import pytest
from pathlib import Path

from verification.dr.validate_report import validate_dr_report


def test_validate_report_success_exact_15(tmp_path):
    report_file = tmp_path / "valid_report.json"
    data = {
        "created": 1728874800.0,
        "duration": 25.5,
        "exitcode": 0,
        "summary": {
            "passed": 15,
            "total": 15,
            "collected": 15
        }
    }
    report_file.write_text(json.dumps(data), encoding="utf-8")
    assert validate_dr_report(report_file) == 0


def test_validate_report_success_more_than_15(tmp_path):
    report_file = tmp_path / "valid_report_more.json"
    data = {
        "duration": 30.0,
        "exitcode": 0,
        "summary": {
            "passed": 20,
            "total": 20,
            "collected": 20
        }
    }
    report_file.write_text(json.dumps(data), encoding="utf-8")
    assert validate_dr_report(report_file) == 0


def test_validate_report_missing_file(tmp_path):
    missing_file = tmp_path / "does_not_exist.json"
    assert validate_dr_report(missing_file) == 1


def test_validate_report_empty_file(tmp_path):
    empty_file = tmp_path / "empty.json"
    empty_file.write_text("", encoding="utf-8")
    assert validate_dr_report(empty_file) == 1


def test_validate_report_whitespace_only_file(tmp_path):
    ws_file = tmp_path / "whitespace.json"
    ws_file.write_text("   \n\t  ", encoding="utf-8")
    assert validate_dr_report(ws_file) == 1


def test_validate_report_corrupted_json(tmp_path):
    corrupt_file = tmp_path / "corrupt.json"
    corrupt_file.write_text('{"summary": {"passed": 15, "total": 15}, "exitcode": 0', encoding="utf-8")
    assert validate_dr_report(corrupt_file) == 1


def test_validate_report_root_not_dict(tmp_path):
    list_file = tmp_path / "list_root.json"
    list_file.write_text('[{"passed": 15}]', encoding="utf-8")
    assert validate_dr_report(list_file) == 1


def test_validate_report_missing_summary(tmp_path):
    no_summary = tmp_path / "no_summary.json"
    no_summary.write_text(json.dumps({"exitcode": 0, "duration": 10.0}), encoding="utf-8")
    assert validate_dr_report(no_summary) == 1


def test_validate_report_insufficient_tests(tmp_path):
    under_15 = tmp_path / "under_15.json"
    data = {
        "exitcode": 0,
        "summary": {
            "passed": 14,
            "total": 14
        }
    }
    under_15.write_text(json.dumps(data), encoding="utf-8")
    assert validate_dr_report(under_15) == 1


def test_validate_report_has_failed_tests(tmp_path):
    failed_report = tmp_path / "failed.json"
    data = {
        "exitcode": 1,
        "summary": {
            "passed": 14,
            "failed": 1,
            "total": 15
        }
    }
    failed_report.write_text(json.dumps(data), encoding="utf-8")
    assert validate_dr_report(failed_report) == 1


def test_validate_report_has_skipped_tests(tmp_path):
    skipped_report = tmp_path / "skipped.json"
    data = {
        "exitcode": 0,
        "summary": {
            "passed": 14,
            "skipped": 1,
            "total": 15
        }
    }
    skipped_report.write_text(json.dumps(data), encoding="utf-8")
    assert validate_dr_report(skipped_report) == 1


def test_validate_report_has_errors(tmp_path):
    error_report = tmp_path / "error.json"
    data = {
        "exitcode": 1,
        "summary": {
            "passed": 14,
            "error": 1,
            "total": 15
        }
    }
    error_report.write_text(json.dumps(data), encoding="utf-8")
    assert validate_dr_report(error_report) == 1


def test_validate_report_inconsistent_passed_total(tmp_path):
    inconsistent = tmp_path / "inconsistent.json"
    data = {
        "exitcode": 0,
        "summary": {
            "passed": 14,
            "failed": 0,
            "total": 15
        }
    }
    inconsistent.write_text(json.dumps(data), encoding="utf-8")
    assert validate_dr_report(inconsistent) == 1


@pytest.mark.parametrize("nonzero_code", [1, 2, -1, 137])
def test_validate_report_nonzero_exitcode(tmp_path, nonzero_code):
    nonzero = tmp_path / "nonzero_exit.json"
    data = {
        "exitcode": nonzero_code,
        "summary": {
            "passed": 15,
            "total": 15
        }
    }
    nonzero.write_text(json.dumps(data), encoding="utf-8")
    assert validate_dr_report(nonzero) == 1


def test_validate_report_missing_exitcode(tmp_path):
    missing_exit = tmp_path / "missing_exit.json"
    data = {
        "summary": {
            "passed": 15,
            "total": 15
        }
    }
    missing_exit.write_text(json.dumps(data), encoding="utf-8")
    assert validate_dr_report(missing_exit) == 1


def test_validate_report_null_exitcode(tmp_path):
    null_exit = tmp_path / "null_exit.json"
    data = {
        "exitcode": None,
        "summary": {
            "passed": 15,
            "total": 15
        }
    }
    null_exit.write_text(json.dumps(data), encoding="utf-8")
    assert validate_dr_report(null_exit) == 1


def test_validate_report_string_exitcode(tmp_path):
    string_exit = tmp_path / "string_exit.json"
    data = {
        "exitcode": "0",
        "summary": {
            "passed": 15,
            "total": 15
        }
    }
    string_exit.write_text(json.dumps(data), encoding="utf-8")
    assert validate_dr_report(string_exit) == 1


@pytest.mark.parametrize("bool_val", [True, False])
def test_validate_report_boolean_exitcode(tmp_path, bool_val):
    bool_exit = tmp_path / "bool_exit.json"
    data = {
        "exitcode": bool_val,
        "summary": {
            "passed": 15,
            "total": 15
        }
    }
    bool_exit.write_text(json.dumps(data), encoding="utf-8")
    assert validate_dr_report(bool_exit) == 1
