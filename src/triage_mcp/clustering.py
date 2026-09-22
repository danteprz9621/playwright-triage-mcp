"""Groups test failures by a normalized error signature.

The core idea (carried over from log-triage tooling built for a production
CI pipeline): two failures that throw the *same* error message, once you
strip out the parts that vary run-to-run (timestamps, generated IDs, line
numbers, dynamic selector values), are very likely the same underlying bug --
so they should surface as one cluster instead of N separate tickets.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from triage_mcp.parser import TestFailure

# Applied in order. Each pattern's match is replaced by its placeholder so
# that two error messages differing only in these tokens normalize identically.
_NORMALIZATION_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\x1b\[[0-9;]*m"), ""),  # strip ANSI color codes first
    (re.compile(r"[A-Za-z]:\\[^\s:]+|/(?:[\w.\-]+/)+[\w.\-]+"), "<PATH>"),  # win/posix paths
    (re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"), "<UUID>"),
    (re.compile(r":\d+:\d+\b"), ":<LOC>"),  # "file.ts:42:7" -> "file.ts<LOC>" (path already stripped above, but covers bare loc refs)
    (re.compile(r"\b\d+ms\b"), "<DURATION>"),
    (re.compile(r"\"[^\"]*\"|'[^']*'"), "<STR>"),  # quoted literals (selectors, expected/received values)
    (re.compile(r"\b\d+\b"), "<NUM>"),
    (re.compile(r"\s+"), " "),
]


def normalize_error(message: str) -> str:
    """Collapse a raw Playwright error message into a stable signature."""
    text = message.strip()
    for pattern, replacement in _NORMALIZATION_RULES:
        text = pattern.sub(replacement, text)
    return text.strip()


@dataclass
class FailureCluster:
    """One group of failures that share a normalized error signature."""

    signature: str
    example_message: str
    count: int
    affected_tests: list[str] = field(default_factory=list)
    affected_files: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "signature": self.signature,
            "example_message": self.example_message,
            "count": self.count,
            "affected_tests": self.affected_tests,
            "affected_files": self.affected_files,
        }


def cluster_failures(failures: list[TestFailure]) -> list[FailureCluster]:
    """Group failures by normalized error signature, largest cluster first.

    Clusters with more members are surfaced first because they're the
    highest-leverage fix: one root cause likely explains all of them.
    """
    clusters: dict[str, FailureCluster] = {}

    for failure in failures:
        signature = normalize_error(failure.error_message)
        cluster = clusters.get(signature)
        if cluster is None:
            cluster = FailureCluster(
                signature=signature,
                example_message=failure.error_message,
                count=0,
            )
            clusters[signature] = cluster

        cluster.count += 1
        test_label = f"{failure.suite_path} > {failure.test_title}".strip(" >")
        if test_label not in cluster.affected_tests:
            cluster.affected_tests.append(test_label)
        if failure.file and failure.file not in cluster.affected_files:
            cluster.affected_files.append(failure.file)

    return sorted(clusters.values(), key=lambda c: c.count, reverse=True)
