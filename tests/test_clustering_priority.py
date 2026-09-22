from pathlib import Path

from triage_mcp.clustering import cluster_failures
from triage_mcp.parser_pytest import parse_pytest_json_report

FIXTURE = Path(__file__).parent / "fixtures" / "sample_pytest_report.json"


def test_priority_cluster_sorts_first_even_though_smaller():
    failures = parse_pytest_json_report(FIXTURE)
    clusters = cluster_failures(failures, priority_markers={"smoke"})

    # cluster sizes in the fixture: 3 (status codes), 1 (smoke), 1 (reports) --
    # the smoke cluster must lead despite being the smallest.
    assert clusters[0].is_priority is True
    assert clusters[0].count == 1
    assert "tests/test_smoke.py > test_health_check" in clusters[0].priority_tests

    # non-priority clusters still fall back to size ordering after that
    assert clusters[1].is_priority is False
    assert clusters[1].count == 3
    assert clusters[2].is_priority is False
    assert clusters[2].count == 1


def test_disabling_priority_markers_falls_back_to_pure_size_sort():
    failures = parse_pytest_json_report(FIXTURE)
    clusters = cluster_failures(failures, priority_markers=None)

    assert all(c.is_priority is False for c in clusters)
    assert [c.count for c in clusters] == [3, 1, 1]


def test_custom_priority_marker_name():
    failures = parse_pytest_json_report(FIXTURE)

    # "smoke" isn't in this set, so nothing should be flagged priority
    clusters = cluster_failures(failures, priority_markers={"critical"})
    assert all(c.is_priority is False for c in clusters)
