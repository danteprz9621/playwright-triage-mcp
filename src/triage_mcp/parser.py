"""Parses a Playwright JSON reporter report into a flat list of test failures.

Playwright's JSON reporter (`playwright test --reporter=json`) nests suites
inside suites, each holding specs, each spec holding one or more tests (one
per project/browser), each test holding one or more results (one per retry).
This module walks that tree defensively -- exact field presence has shifted
across Playwright versions -- and flattens every failed/timed-out result into
a single dataclass.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


FAILING_STATUSES = {"failed", "timedOut"}

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _strip_ansi(text: str) -> str:
    """Playwright's JSON reporter embeds terminal color codes straight into
    error messages; strip them so stored/displayed messages are plain text
    (clustering already strips them again during normalization, but the
    *raw* example_message shown to a human shouldn't carry escape codes)."""
    return _ANSI_RE.sub("", text)


@dataclass
class TestFailure:
    """A single failed test result, flattened out of a test report tree.

    Shared by every parser in this package (Playwright's JSON reporter,
    pytest-json-report, ...) so `clustering.py` doesn't need to know which
    framework produced a given failure.
    """

    test_title: str
    suite_path: str
    file: str
    project: str
    status: str
    error_message: str
    error_stack: str = ""
    duration_ms: int = 0
    retry: int = 0
    source: str = "playwright"
    tags: list[str] = field(default_factory=list)


def parse_playwright_json_report(report_path: str | Path) -> list[TestFailure]:
    """Read a Playwright JSON reporter file and return every failing result."""
    path = Path(report_path)
    data = _load_json(path)
    return list(_walk_suites(data.get("suites", []), suite_path=[]))


def parse_playwright_json_string(report_json: str) -> list[TestFailure]:
    """Same as parse_playwright_json_report, but from an in-memory JSON string.

    Useful when a caller already has the report contents (e.g. piped from CI)
    and doesn't want to write a temp file first.
    """
    import json

    data = json.loads(report_json)
    return list(_walk_suites(data.get("suites", []), suite_path=[]))


def _load_json(path: Path) -> dict[str, Any]:
    import json

    if not path.exists():
        raise FileNotFoundError(f"Playwright report not found: {path}")
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _walk_suites(suites: list[dict[str, Any]], suite_path: list[str]):
    for suite in suites:
        title = suite.get("title") or ""
        next_path = suite_path + [title] if title else suite_path
        file = suite.get("file", "")

        for spec in suite.get("specs", []) or []:
            yield from _walk_spec(spec, suite_path=next_path, default_file=file)

        # suites can nest arbitrarily deep (describe blocks inside describe blocks)
        yield from _walk_suites(suite.get("suites", []) or [], next_path)


def _walk_spec(spec: dict[str, Any], suite_path: list[str], default_file: str):
    spec_title = spec.get("title", "")
    spec_file = spec.get("file", default_file)

    for test in spec.get("tests", []) or []:
        project = test.get("projectName", "") or test.get("projectId", "")

        for result_idx, result in enumerate(test.get("results", []) or []):
            status = result.get("status", "")
            if status not in FAILING_STATUSES:
                continue

            error = _extract_error(result)
            yield TestFailure(
                test_title=spec_title,
                suite_path=" > ".join(p for p in suite_path if p),
                file=spec_file,
                project=str(project),
                status=status,
                error_message=error["message"],
                error_stack=error["stack"],
                duration_ms=result.get("duration", 0),
                retry=result.get("retry", result_idx),
            )


def _extract_error(result: dict[str, Any]) -> dict[str, str]:
    """Playwright reports can carry `error`, or a list under `errors`, or
    neither if the failure was a timeout with no thrown error object."""
    error = result.get("error")
    if error:
        return {
            "message": _strip_ansi((error.get("message") or "").strip()),
            "stack": _strip_ansi((error.get("stack") or "").strip()),
        }

    errors = result.get("errors") or []
    if errors:
        first = errors[0] or {}
        return {
            "message": _strip_ansi((first.get("message") or "").strip()),
            "stack": _strip_ansi((first.get("stack") or "").strip()),
        }

    status = result.get("status", "unknown")
    return {"message": f"(no error object reported; status={status})", "stack": ""}
