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
- **Domain models: `Booking` references its room by `room_id: str`,** not a
  `Room` object — avoids duplicating room state and mirrors the SQLite layer
  (foreign key by id).
- **Domain entities grouped in one `models.py`.** `Room`, `User` and `Booking`
  are the shared domain vocabulary and evolve together (high cohesion); no
  per-class files. They are frozen dataclasses (immutable, value equality) and
  data-only — all validation lives in `domain/rules.py`.
- **Domain rules are pure functions in `domain/rules.py`.** Each rule (slot
  alignment, duration ≤ 3h, capacity, title, overlap) is single-responsibility,
  does no I/O, and takes its inputs directly — the overlap check receives the
  existing bookings as a list, so the repository supplies data later and rules
  stay decoupled from persistence.
- **Flat typed exceptions in `domain/exceptions.py`.** One subclass per rule
  (`SlotAlignmentError`, `DurationError`, `CapacityError`, `TitleRequiredError`,
  `OverlapError`) inheriting directly from a single `BookingError` base — no
  deeper hierarchy (out of scope). Aligns with Issue #14 error handling:
  surface layer catches `BookingError`; callers can catch a specific rule.
  Overlap messages stay neutral and never name the conflicting booking's owner.
- **Persistence: SQLite, repository is the only SQL boundary.** All SQL lives in
  `data/repository.py` (parameterized queries only) and `data/db.py` (schema +
  seed); no other layer touches SQL, and the repository does no business
  validation. `db.py` init is idempotent (`CREATE TABLE IF NOT EXISTS` +
  `INSERT OR IGNORE`), safe to call on every connection.
- **Room capacities are fixed and seeded on init:** A=2, B=2, C=4, D=8, E=10
  (single source: `ROOM_CAPACITIES` in `db.py`).
- **Datetimes stored as ISO strings** (`isoformat()` / `fromisoformat()`),
  round-tripping the GMT-3 (-03:00) offset — simple, human-readable storage
  consistent with the app timezone.

## Manual GitHub steps (not automated)

These are done in the GitHub UI, not in code:

1. Push a branch / open a PR to trigger the Action for the first time.
2. Enable branch protection with the CI check as a **required status check**
   (Settings → Branches).
