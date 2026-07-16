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
- **Coverage: branch on, `source = ["app"]`, `fail_under = 100`.** The gate lives
  in `pyproject.toml` (single source); CI runs plain `pytest` and inherits it.
  Only the Streamlit entrypoint `app/ui/streamlit_app.py` is `omit`-ted — it is
  pure UI glue with no business logic. Any other untestable line uses a per-line
  `# pragma: no cover`; business logic is never blanket-omitted. _(Supersedes the
  earlier "no omit / gate deferred" note now that CI exists.)_
- **Lint: ruff** with `E,F,I,W,UP,B` rule sets and line length 100.
- **CI: GitHub Actions (`.github/workflows/ci.yml`).** Runs on push and
  pull_request: checkout → setup-python 3.11 → install → `ruff check` →
  `pytest`. The 100% coverage gate fails the build (verified locally: adding one
  uncovered line makes `pytest` exit 1; removing it returns to exit 0).

## Manual GitHub steps (not automated)

These are done in the GitHub UI, not in code:

1. Push a branch / open a PR to trigger the Action for the first time.
2. Enable branch protection with the CI check as a **required status check**
   (Settings → Branches).
