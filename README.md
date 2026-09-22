# playwright-triage-mcp

An [MCP](https://modelcontextprotocol.io) server that parses a Playwright JSON
test report and groups failures by **normalized error signature**, so
failures that most likely share one root cause — and one fix — surface
together instead of looking like N unrelated bugs.

## Why

At a previous job I built internal Python tooling that parsed CI logs and
categorized failures: two tests failing with the same underlying error
message were treated as one likely fix, not two separate issues, which cut
down a lot of duplicate triage work. This project reimplements that idea as
an MCP server, so an AI client (Claude Desktop, Claude Code, or any other MCP
client) can pull structured, pre-clustered failure data straight out of a
Playwright run and reason about likely root causes — instead of scrolling
through a wall of raw test output.

The clustering itself is intentionally simple and deterministic (regex-based
normalization, exact-match grouping) — the server's job is to turn noisy logs
into structured signal; interpreting *why* a cluster is failing and what the
fix probably is is left to whichever LLM calls the tool.

## What it does

Two tools, exposed over MCP, each supporting two report formats:

- **`list_failures(report_path, source="playwright"|"pytest")`** — every
  failed test in a report, flattened into a simple list.
- **`triage_report(report_path, source=..., priority_markers=["smoke"])`** —
  the same failures, grouped by normalized error signature and sorted with
  priority clusters first, then largest-cluster-first.

`source="playwright"` reads a Playwright JSON reporter file
(`playwright test --reporter=json`). `source="pytest"` reads a
[pytest-json-report](https://pypi.org/project/pytest-json-report/) file
(`pytest --json-report --json-report-file=report.json`).

Normalization strips out the parts of an error message that vary run-to-run
but don't change the underlying cause: timestamps/durations, generated
IDs/UUIDs, file paths, quoted literals (selectors, expected/received values),
and bare numbers. So these three errors:

```
TimeoutError: locator.click: Timeout 5000ms exceeded waiting for locator('button#submit-4821')
TimeoutError: locator.click: Timeout 5000ms exceeded waiting for locator('button#submit-1190')
TimeoutError: locator.click: Timeout 5000ms exceeded waiting for locator('button#submit-6602')
```

normalize to the same signature and collapse into one 3-test cluster instead
of three separate-looking failures.

**Priority markers:** for `source="pytest"`, a test marked
`@pytest.mark.smoke` (or any marker name passed via `priority_markers`) that
fails always sorts to the top of the triage results, regardless of how big
its cluster is — a broken smoke test blocking a release outranks a 5-test
cluster of some unrelated, non-critical flake. `ci_triage.py` (see below)
also exits non-zero when a priority cluster is present, so a CI step can gate
on "did a release-blocking test fail" specifically.

## Project layout

```
src/triage_mcp/
  parser.py          # Playwright JSON report -> flat list of TestFailure
  parser_pytest.py    # pytest-json-report -> the same TestFailure shape
  clustering.py       # groups TestFailures by normalized error signature,
                       # with priority-marker-aware sorting
  server.py            # MCP server wiring (list_failures, triage_report tools)
scripts/
  ci_triage.py         # CI entry point: calls the MCP server over stdio,
                        # renders a GitHub Actions job-summary table
demo/
  tests/*.spec.ts       # a tiny Playwright suite with a few tests that fail
                         # on purpose, so CI has something real to triage
.github/workflows/triage.yml   # runs the demo suite, uploads its report as
                                # an artifact, downloads it in a second job,
                                # and triages it
tests/
  test_parser.py
  test_parser_pytest.py
  test_clustering.py
  test_clustering_priority.py
  fixtures/sample_report.json          # synthetic Playwright report
  fixtures/sample_pytest_report.json   # synthetic pytest report (incl. a
                                        # failing @pytest.mark.smoke test)
```

## Setup

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

## Running the tests

```bash
pytest tests/ -v
```

## Generating a real report to try it on

Playwright:

```bash
npx playwright test --reporter=json --output=report.json
# or configure `reporter: [['json', { outputFile: 'report.json' }]]` in
# playwright.config.ts, which is what demo/ does.
```

pytest (requires the `pytest-json-report` plugin):

```bash
pip install pytest-json-report
pytest --json-report --json-report-file=report.json
```

Then call either tool with `report_path` pointing at `report.json` and
`source` set accordingly.

## Using it as an MCP server

Run it directly over stdio:

```bash
python -m triage_mcp.server
```

To wire it into Claude Desktop (or Claude Code), add it to the client's MCP
config, e.g. `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "playwright-triage": {
      "command": "/absolute/path/to/.venv/bin/python",
      "args": ["-m", "triage_mcp.server"]
    }
  }
}
```

Then ask the client something like *"Run playwright-triage on
report.json and tell me which cluster I should fix first."*

## CI/CD integration (GitHub Actions)

`.github/workflows/triage.yml` wires this up as a real two-job pipeline:

1. **`playwright-tests`** — installs `demo/`'s dependencies, runs its
   Playwright suite (a few tests fail on purpose — see `demo/tests/*.spec.ts`
   — so there's something real to triage, not just the fixtures), and
   uploads the resulting `report.json` as a build artifact.
2. **`triage`** — downloads that artifact, then runs
   `scripts/ci_triage.py`, which spins up the MCP server as a subprocess and
   calls `triage_report` over the real MCP protocol (the same
   `mcp.client.stdio` session an AI client would use) — not just importing
   the Python functions directly. The clustered result is rendered as a
   Markdown table into the GitHub Actions job summary (visible right on the
   workflow run page) and uploaded as a `triage-summary.json` artifact.

`ci_triage.py` also supports `--source pytest` and `--priority-marker`, and
exits non-zero when a priority-marked cluster is present, so a pytest-based
pipeline elsewhere could use it as a "did a smoke test break" release gate.

## Status

Core parsing, clustering, priority-marker sorting, and the CI wiring are all
done and tested (17 pytest tests, plus a real end-to-end GitHub Actions run
against a genuine Playwright report). Natural next steps if this grows past
a demo: an optional tool that feeds each cluster to an LLM for a one-line
root-cause hypothesis, support for more reporters (JUnit XML, raw stdout
logs), and a `resources` endpoint that exposes the latest CI run's report
automatically instead of requiring a file path.
