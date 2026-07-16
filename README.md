# Promtior Challenge — Meeting-Room Booking Chatbot

## Overview

_Placeholder._ Conversational chatbot to book, list, inspect and cancel meeting
rooms (A–E) at Promtior's Cubo Itaú office via natural language.

## Architecture

Clean-Architecture layering under `app/` (`domain` → `data` → `auth` → `tools` →
`agent` → `cache` → `ui`); dependencies point inward. Full layer descriptions and
boundary justifications live in [CLAUDE.md](CLAUDE.md).

## AI Workflow

_Placeholder._ Per user message, three LLM roles run in sequence (guardrail →
booking agent → output verifier). See [CLAUDE.md](CLAUDE.md#ai-workflow) until
this section is filled in.

## Decision Log

- **Dependency manager: `pyproject.toml`.** Single file holds deps *and* tool
  config (pytest, coverage, ruff), so no separate `requirements.txt` /
  `pytest.ini` / `ruff.toml`. Runtime deps unpinned; dev tools under the `dev`
  extra.
- **Coverage: branch coverage on, `source = ["app"]`, no `omit`.** UI/entrypoint
  glue is excluded per-line via justified `# pragma: no cover` only — business
  logic is never blanket-omitted. `fail_under` gate deferred to the CI issue.
- **Lint: ruff** with `E,F,I,W,UP,B` rule sets and line length 100.
