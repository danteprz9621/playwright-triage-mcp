"""MCP server exposing Playwright failure-triage tools.

Run it directly for local testing:
    python -m triage_mcp.server

Or point an MCP client (Claude Desktop, Claude Code, etc.) at this module
over stdio -- see README.md for the client config snippet.
"""

from __future__ import annotations

from typing import Literal

from mcp.server.mcpserver import MCPServer

from triage_mcp.clustering import DEFAULT_PRIORITY_MARKERS, cluster_failures
from triage_mcp.parser import parse_playwright_json_report
from triage_mcp.parser_pytest import parse_pytest_json_report

server = MCPServer(
    name="playwright-triage",
    instructions=(
        "Tools for triaging Playwright and pytest test failures. Given a "
        "Playwright JSON reporter file (`playwright test --reporter=json`) "
        "or a pytest-json-report file, group failures by normalized error "
        "signature so failures that likely share one root cause -- and one "
        "fix -- surface together, instead of as N separate-looking "
        "failures. Failures tagged with a priority marker (e.g. a pytest "
        "test marked `@pytest.mark.smoke`) are surfaced first regardless "
        "of cluster size."
    ),
)

ReportSource = Literal["playwright", "pytest"]

_PARSERS = {
    "playwright": parse_playwright_json_report,
    "pytest": parse_pytest_json_report,
}


def _parse(report_path: str, source: ReportSource):
    try:
        parse_fn = _PARSERS[source]
    except KeyError as exc:
        raise ValueError(f"Unknown source {source!r}; expected one of {list(_PARSERS)}") from exc
    return parse_fn(report_path)


@server.tool()
def list_failures(report_path: str, source: ReportSource = "playwright") -> list[dict]:
    """List every failed test in a report, unclustered.

    Args:
        report_path: Path to a Playwright JSON reporter file
            (`playwright test --reporter=json`) or a pytest-json-report
            file (`pytest --json-report --json-report-file=report.json`).
        source: Which report format `report_path` is in: "playwright" or
            "pytest".
    """
    failures = _parse(report_path, source)
    return [
        {
            "test_title": f.test_title,
            "suite_path": f.suite_path,
            "file": f.file,
            "project": f.project,
            "status": f.status,
            "error_message": f.error_message,
            "duration_ms": f.duration_ms,
            "retry": f.retry,
            "source": f.source,
            "tags": f.tags,
        }
        for f in failures
    ]


@server.tool()
def triage_report(
    report_path: str,
    source: ReportSource = "playwright",
    priority_markers: list[str] | None = None,
) -> dict:
    """Parse a test report and cluster failures by normalized error signature.

    Each cluster groups failures whose error messages are identical once
    run-to-run noise (timestamps, generated IDs, line numbers, quoted
    selector/value literals) is stripped out. A cluster with N tests is a
    strong signal that one root cause -- and one fix -- explains all N,
    which is far more actionable than a flat list of N separate failures.

    Clusters containing a failure tagged with one of `priority_markers`
    (e.g. a pytest test marked `@pytest.mark.smoke`) are sorted first,
    regardless of cluster size -- a broken smoke test blocking release
    outranks a bigger cluster of some unrelated, non-critical flake. Within
    each tier, larger clusters sort first.

    Args:
        report_path: Path to a Playwright JSON reporter file
            (`playwright test --reporter=json`) or a pytest-json-report
            file (`pytest --json-report --json-report-file=report.json`).
        source: Which report format `report_path` is in: "playwright" or
            "pytest". Playwright reports have no marker/keyword concept
            today, so priority tagging is currently only meaningful for
            `source="pytest"`.
        priority_markers: Marker/keyword names that mark a test as
            release-blocking (default: `["smoke"]`). Pass `[]` to disable
            priority tagging and sort purely by cluster size.
    """
    failures = _parse(report_path, source)
    markers = frozenset(priority_markers) if priority_markers is not None else DEFAULT_PRIORITY_MARKERS
    clusters = cluster_failures(failures, priority_markers=markers)

    return {
        "report_path": report_path,
        "source": source,
        "total_failures": len(failures),
        "cluster_count": len(clusters),
        "priority_cluster_count": sum(1 for c in clusters if c.is_priority),
        "clusters": [c.as_dict() for c in clusters],
    }


def main() -> None:
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
