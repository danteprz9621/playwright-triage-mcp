#!/usr/bin/env python
"""CI entry point for playwright-triage-mcp.

Spins up the MCP server as a subprocess (over stdio, using the real
mcp.client.stdio session -- the same protocol Claude Desktop/Claude Code
would use), calls its `triage_report` tool against a test report, and
renders the clustered result both as a GitHub Actions job-summary table and
as a JSON artifact for later inspection.

Usage:
    python scripts/ci_triage.py <report.json> [--source playwright|pytest]
                                 [--priority-marker smoke] [--out triage-summary.json]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def run_triage(report_path: str, source: str, priority_markers: list[str]) -> dict:
    params = StdioServerParameters(command=sys.executable, args=["-m", "triage_mcp.server"])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "triage_report",
                {
                    "report_path": report_path,
                    "source": source,
                    "priority_markers": priority_markers,
                },
            )
            if result.is_error:
                raise RuntimeError(f"triage_report tool call failed: {result.content}")
            return json.loads(result.content[0].text)


def render_markdown(triage: dict) -> str:
    lines = [
        "## Playwright failure triage",
        "",
        f"**{triage['total_failures']}** failing result(s) across "
        f"**{triage['cluster_count']}** distinct root-cause cluster(s) "
        f"({triage['priority_cluster_count']} priority).",
        "",
        "| # | Priority | Failures | Likely shared root cause (normalized error) | Affected tests |",
        "|---|----------|----------|-----------------------------------------------|-----------------|",
    ]
    for i, cluster in enumerate(triage["clusters"], start=1):
        priority = "**PRIORITY**" if cluster["is_priority"] else ""
        signature = cluster["signature"].replace("|", "\\|")
        tests = "<br>".join(t.replace("|", "\\|") for t in cluster["affected_tests"])
        lines.append(f"| {i} | {priority} | {cluster['count']} | `{signature}` | {tests} |")

    if triage["total_failures"] == 0:
        lines.append("")
        lines.append("No failures — clean run.")

    return "\n".join(lines)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report_path", help="Path to the test report file")
    parser.add_argument(
        "--source", choices=["playwright", "pytest"], default="playwright",
        help="Report format (default: playwright)",
    )
    parser.add_argument(
        "--priority-marker", dest="priority_markers", action="append", default=[],
        help="Marker/keyword that flags a test as release-blocking. Repeatable. "
             "Defaults to ['smoke'] if none given.",
    )
    parser.add_argument(
        "--out", default="triage-summary.json",
        help="Where to write the raw JSON triage result (default: triage-summary.json)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    priority_markers = args.priority_markers or ["smoke"]

    triage = asyncio.run(run_triage(args.report_path, args.source, priority_markers))

    output_path = Path(args.out)
    output_path.write_text(json.dumps(triage, indent=2), encoding="utf-8")
    print(f"Wrote {output_path}")

    markdown = render_markdown(triage)
    print(markdown)

    summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_file:
        with open(summary_file, "a", encoding="utf-8") as fh:
            fh.write(markdown + "\n")

    # Non-zero exit if a priority cluster failed, so the workflow step can
    # (optionally) fail the build on release-blocking failures specifically,
    # rather than on any failure at all.
    return 1 if triage["priority_cluster_count"] > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
