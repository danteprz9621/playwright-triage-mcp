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

Two tools, exposed over MCP:

- **`list_failures(report_path)`** — every failed/timed-out test in a
  Playwright JSON report, flattened into a simple list.
- **`triage_report(report_path)`** — the same failures, grouped by normalized
  error signature and sorted largest cluster first.

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

## Project layout

```
src/triage_mcp/
  parser.py       # Playwright JSON report -> flat list of TestFailure
  clustering.py   # groups TestFailures by normalized error signature
  server.py       # MCP server wiring (list_failures, triage_report tools)
tests/
  test_parser.py
  test_clustering.py
  fixtures/sample_report.json   # synthetic report used by both test files
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

## Generating a real Playwright report to try it on

```bash
npx playwright test --reporter=json > report.json
```

Then call either tool with `report_path` pointing at `report.json`.

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

## Status

MVP. Deterministic parsing + clustering are done and tested. Natural next
steps if this grows past a demo: an optional tool that feeds each cluster to
an LLM for a one-line root-cause hypothesis, support for other reporters
(JUnit XML, raw stdout logs), and a `resources` endpoint that exposes the
latest CI run's report automatically instead of requiring a file path.
