from pathlib import Path

from triage_mcp.parser_pytest import parse_pytest_json_report

FIXTURE = Path(__file__).parent / "fixtures" / "sample_pytest_report.json"


def test_parses_only_failed_tests():
    failures = parse_pytest_json_report(FIXTURE)

    # 5 failed, 1 passed in the fixture; the passed one must not appear.
    assert len(failures) == 5
    assert all(f.status == "failed" for f in failures)
    assert all(f.source == "pytest" for f in failures)


def test_splits_nodeid_into_file_and_title():
    failures = parse_pytest_json_report(FIXTURE)

    a = next(f for f in failures if f.test_title == "test_status_a")
    assert a.file == "tests/test_api.py"
    assert a.suite_path == "tests/test_api.py"


def test_extracts_concise_error_from_longrepr_e_lines():
    failures = parse_pytest_json_report(FIXTURE)

    a = next(f for f in failures if f.test_title == "test_status_a")
    # only the "E "-prefixed line(s) should survive, not the whole traceback
    assert a.error_message == "assert 500 == 200"
    assert "def test_status_a" not in a.error_message


def test_smoke_marked_test_carries_the_smoke_tag():
    failures = parse_pytest_json_report(FIXTURE)

    smoke = next(f for f in failures if f.test_title == "test_health_check")
    assert "smoke" in smoke.tags


def test_non_smoke_test_does_not_carry_the_smoke_tag():
    failures = parse_pytest_json_report(FIXTURE)

    non_smoke = next(f for f in failures if f.test_title == "test_status_a")
    assert "smoke" not in non_smoke.tags
