"""MCP server exposing Playwright failure-triage tools.

Run it directly for local testing:
    python -m triage_mcp.server

Or point an MCP client (Claude Desktop, Claude Code, etc.) at this module
over stdio -- see README.md for the client config snippet.
"""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from triage_mcp.clustering import cluster_failures
from triage_mcp.parser import parse_playwright_json_report

server = MCPServer(
    name="playwright-triage",
    instructions=(
        "Tools for triaging Playwright test failures. Given a Playwright "
        "JSON reporter file (`playwright test --reporter=json`), group "
        "failures by normalized error signature so failures that likely "
        "share one root cause -- and one fix -- surface together, instead "
        "of as N separate-looking failures."
    ),
)


@server.tool()
def list_failures(report_path: str) -> list[dict]:
    """List every failed/timed-out test in a Playwright JSON report, unclustered.

    Args:
        report_path: Path to a Playwright JSON reporter output file
            (produced by `playwright test --reporter=json`).
    """
    failures = parse_playwright_json_report(report_path)
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
        }
        for f in failures
    ]


@server.tool()
def triage_report(report_path: str) -> dict:
    """Parse a Playwright JSON report and cluster failures by normalized error
    signature, largest cluster first.

    Each cluster groups failures whose error messages are identical once
    run-to-run noise (timestamps, generated IDs, line numbers, quoted
    selector/value literals) is stripped out. A cluster with N tests is a
    strong signal that one root cause -- and one fix -- explains all N,
    which is far more actionable than a flat list of N separate failures.

    Args:
        report_path: Path to a Playwright JSON reporter output file
            (produced by `playwright test --reporter=json`).
    """
    failures = parse_playwright_json_report(report_path)
    clusters = cluster_failures(failures)

    return {
        "report_path": report_path,
        "total_failures": len(failures),
        "cluster_count": len(clusters),
        "clusters": [c.as_dict() for c in clusters],
    }


def main() -> None:
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
