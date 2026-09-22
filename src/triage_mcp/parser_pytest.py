"""Parses a pytest-json-report file into the same TestFailure shape the
Playwright parser produces, so clustering.py can treat both sources uniformly.

Built against the report shape produced by the `pytest-json-report` plugin
(https://pypi.org/project/pytest-json-report/):

    {
      "tests": [
        {
          "nodeid": "tests/test_api.py::test_returns_200",
          "outcome": "failed",
          "keywords": ["test_returns_200", "smoke", "tests/test_api.py", ...],
          "call": {"duration": 0.01, "outcome": "failed", "longrepr": "..."}
        },
        ...
      ]
    }

`keywords` mixes pytest markers (e.g. a `@pytest.mark.smoke` test carries a
"smoke" keyword) together with other implicit keywords (the test's own name,
its file path, etc.) -- pytest doesn't cleanly separate "markers I applied"
from "keywords" in this report. This parser treats every keyword as a
candidate tag; `cluster_failures()` only acts on the ones that match a
caller-supplied `priority_markers` set, so the noise doesn't matter in
practice. This has been verified against a synthetic fixture matching the
documented schema, not yet against a real project's pytest-json-report
output -- if a real report's field names differ, `_extract_keywords` and
`_extract_longrepr` are the two functions to adjust.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from triage_mcp.parser import TestFailure

FAILING_OUTCOMES = {"failed", "error"}


def parse_pytest_json_report(report_path: str | Path) -> list[TestFailure]:
    """Read a pytest-json-report file and return every failed/errored test."""
    path = Path(report_path)
    data = _load_json(path)
    return list(_extract_failures(data.get("tests", []) or []))


def parse_pytest_json_string(report_json: str) -> list[TestFailure]:
    """Same as parse_pytest_json_report, but from an in-memory JSON string."""
    import json

    data = json.loads(report_json)
    return list(_extract_failures(data.get("tests", []) or []))


def _load_json(path: Path) -> dict[str, Any]:
    import json

    if not path.exists():
        raise FileNotFoundError(f"pytest-json-report file not found: {path}")
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _extract_failures(tests: list[dict[str, Any]]):
    for test in tests:
        outcome = test.get("outcome", "")
        if outcome not in FAILING_OUTCOMES:
            continue

        nodeid = test.get("nodeid", "")
        file, _, title = nodeid.partition("::")

        call = test.get("call") or {}
        # if the failure happened in setup/teardown rather than the test body
        # (outcome == "error"), fall back to those phases for the traceback.
        phase = call if call.get("outcome") in FAILING_OUTCOMES else (
            test.get("setup") if (test.get("setup") or {}).get("outcome") in FAILING_OUTCOMES
            else test.get("teardown") or {}
        )

        message = _extract_longrepr(phase)
        duration_s = phase.get("duration") or call.get("duration") or 0

        yield TestFailure(
            test_title=title or nodeid,
            suite_path=file,
            file=file,
            project="",
            status="failed",
            error_message=message,
            error_stack="",
            duration_ms=int(float(duration_s) * 1000),
            retry=0,
            source="pytest",
            tags=_extract_keywords(test),
        )


def _extract_keywords(test: dict[str, Any]) -> list[str]:
    keywords = test.get("keywords")
    if keywords is None:
        return []
    if isinstance(keywords, dict):
        return list(keywords.keys())
    if isinstance(keywords, (list, tuple, set)):
        return [str(k) for k in keywords]
    return []


def _extract_longrepr(phase: dict[str, Any]) -> str:
    """Pull the concise failure summary out of a pytest `longrepr`.

    pytest's default text traceback prefixes the actual assertion/exception
    lines with "E " (e.g. "E   assert 500 == 200"). Those lines are the part
    that's stable across otherwise-identical failures -- the surrounding
    frames include file paths and line numbers that vary by call site even
    when the root cause is the same -- so we extract just the "E "-prefixed
    lines when present, and fall back to the raw longrepr otherwise.
    """
    longrepr = phase.get("longrepr")

    if isinstance(longrepr, dict):
        # "crash" style longrepr some pytest versions/plugins emit
        reprcrash = longrepr.get("reprcrash") or {}
        message = reprcrash.get("message")
        if message:
            return str(message).strip()
        return str(longrepr)

    text = str(longrepr or "").strip()
    if not text:
        return "(no longrepr reported)"

    e_lines = [
        line[len("E "):].strip()
        for line in text.splitlines()
        if line.startswith("E ")
    ]
    if e_lines:
        return "\n".join(e_lines)
    return text
