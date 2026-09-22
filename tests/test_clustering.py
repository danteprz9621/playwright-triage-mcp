from pathlib import Path

from triage_mcp.clustering import cluster_failures, normalize_error
from triage_mcp.parser import parse_playwright_json_report

FIXTURE = Path(__file__).parent / "fixtures" / "sample_report.json"


def test_normalize_error_strips_dynamic_ids_and_durations():
    a = normalize_error(
        "TimeoutError: locator.click: Timeout 5000ms exceeded waiting for locator('button#submit-4821')"
    )
    b = normalize_error(
        "TimeoutError: locator.click: Timeout 5000ms exceeded waiting for locator('button#submit-1190')"
    )
    assert a == b


def test_normalize_error_strips_variable_numbers():
    a = normalize_error("Expected: 200\nReceived: 500")
    b = normalize_error("Expected: 200\nReceived: 503")
    assert a == b


def test_normalize_error_keeps_genuinely_different_messages_distinct():
    a = normalize_error("TimeoutError: locator.click: Timeout 5000ms exceeded waiting for locator('button#submit-1')")
    b = normalize_error('Test timeout of 30000ms exceeded while waiting for navigation to "/dashboard"')
    assert a != b


def test_cluster_failures_groups_same_root_cause_and_sorts_by_size():
    failures = parse_playwright_json_report(FIXTURE)
    clusters = cluster_failures(failures)

    # 3 click-timeout failures, 2 API-500 failures, 1 unique navigation timeout
    assert [c.count for c in clusters] == [3, 2, 1]

    largest = clusters[0]
    assert largest.count == 3
    assert len(largest.affected_tests) == 3
    assert "checkout.spec.ts" in largest.affected_files


def test_cluster_as_dict_is_json_serializable():
    import json

    failures = parse_playwright_json_report(FIXTURE)
    clusters = cluster_failures(failures)

    # must not raise
    json.dumps([c.as_dict() for c in clusters])
