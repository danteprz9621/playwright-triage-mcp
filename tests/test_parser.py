from pathlib import Path

from triage_mcp.parser import parse_playwright_json_report

FIXTURE = Path(__file__).parent / "fixtures" / "sample_report.json"


def test_parses_only_failing_results():
    failures = parse_playwright_json_report(FIXTURE)

    # sample_report.json has 6 failed/timedOut results and 1 passed test;
    # the passed test must not show up here.
    assert len(failures) == 6
    assert all(f.status in {"failed", "timedOut"} for f in failures)


def test_flattens_nested_suites():
    failures = parse_playwright_json_report(FIXTURE)

    nested = next(f for f in failures if f.test_title == "allows checkout without an account")
    assert nested.suite_path == "checkout.spec.ts > guest checkout"
    assert nested.project == "webkit"
    assert nested.retry == 1


def test_extracts_error_message_and_file():
    failures = parse_playwright_json_report(FIXTURE)

    api_failure = next(f for f in failures if "200" in f.error_message and "500" in f.error_message)
    assert api_failure.file == "notifications-api.spec.ts"
    assert "Object.is equality" in api_failure.error_message


def test_missing_report_raises_file_not_found():
    import pytest

    with pytest.raises(FileNotFoundError):
        parse_playwright_json_report("does/not/exist.json")
