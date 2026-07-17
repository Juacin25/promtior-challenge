# Promtior Challenge — Meeting-Room Booking Chatbot

## Overview

_Placeholder._ Conversational chatbot to book, list, inspect and cancel meeting
rooms (A–E) at Promtior's Cubo Itaú office via natural language.

## Architecture

Clean-Architecture layering keeps dependencies pointing inward and business rules independent
of SQLite, LangChain, OpenAI, and Streamlit:

```text
app/
├── domain/             # Pure entities, booking rules, and domain errors
├── data/               # SQLite schema and repository; the only SQL boundary
├── auth/               # Login for the two fixed challenge users
├── tools/              # Thin LangChain adapters around application operations
├── agent/
│   ├── llm.py          # ChatOpenAI factory and grounded system-prompt builder
│   ├── guardrail.py    # Input security classifier (planned)
│   ├── verifier.py     # Output grounding check (planned)
│   └── orchestrator.py # Guardrail → booking agent → verifier wiring (Issue #11)
├── cache/              # Static-data-only semantic cache (planned)
└── ui/                 # Thin Streamlit login/chat adapter (planned)
```

`app/agent/llm.py` owns only LLM configuration and system-prompt construction; it contains no
booking rules, tool wiring, or other business logic. Its prompt builder receives the current
datetime instead of reading the clock. This makes the GMT-3 anchor deterministic in tests and
lets the caller define exactly when a turn starts. Domain rules remain pure and testable,
repositories hide SQL, tools translate between model arguments and application operations, and
the orchestrator coordinates the agent flow without absorbing business rules.

## AI Workflow

Per user message, three roles run in sequence: **guardrail → booking agent → output verifier**.
The guardrail blocks prompt injection and improper data-extraction attempts. The booking agent
selects parameterized application tools; it never writes SQL. The verifier checks that the draft
answer is supported by tool results before it reaches the user. This defense-in-depth flow costs
extra calls, so prompt caching is used to reduce repeated input-token work.

The booking system prompt enforces grounding: availability, capacity, bookings, schedules, and
all other room state must come from a tool call and must never be asserted from model memory. It
also limits the assistant to meeting-room operations for rooms A–E and requires unrelated
requests to be refused. Per turn, the caller passes the current datetime and logged-in username
to `build_system_prompt`. The builder converts the anchor to fixed GMT-3 (`-03:00`), states the
absolute current datetime, today's date, and tomorrow's date, and requires 24-hour absolute ISO
datetimes for tool arguments. It never reads the system clock itself.

This ticket provides the LLM-config layer only. Issue #11 will bind the booking tools in a fixed
order and coordinate the guardrail, booking, and verifier roles; no tools are wired in
`llm.py`. Conversation history will live in the Streamlit session, while bookings persist in
SQLite. State-dependent booking results are never semantically cached.

OpenAI prompt caching is engaged with the stable model-level key
`promtior-booking-agent-v1`, passed by `langchain-openai` as `prompt_cache_key`. OpenAI performs
the cache server-side automatically for eligible prompts (currently prompts of at least 1,024
tokens), and cache hits require an exact matching prefix. Accordingly, reusable grounding and
scope instructions appear first in the system prompt, while the changing datetime and username
appear at the end. When Issue #11 binds tool definitions, it must preserve their content and
ordering so the repeated system-prefix/tool-definition input remains reusable. There is no local
prompt-response cache and no claim that short, ineligible prompts produce a cache hit; usage can
be observed through the API response's cached-token metadata.

## Environment and configuration

Copy `.env.example` to `.env` for local development. `.env` is gitignored and must never be
committed.

| Variable | Required | Description |
| --- | --- | --- |
| `OPENAI_API_KEY` | Yes | OpenAI credential loaded with `python-dotenv`; never logged or hardcoded. |
| `OPENAI_MODEL` | No | Chat model name. Defaults to `gpt-4o-mini`, a cost-effective model with tool-calling support. |

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
- **Auth: two fixed users defined in code, not the DB.** The brief fixes User1 /
  User2 as immutable, so they are configuration, not mutable data — this keeps
  login decoupled from DB state and off the bookings database entirely.
- **Passwords hashed with bcrypt at module load.** The shared password is a
  constant used only to derive the hashes in `_CREDENTIALS`; the plaintext is
  never persisted or logged. Hashing at load (vs. committing precomputed hashes)
  keeps the source obviously correct and avoids storing a hash literal.
- **Generic auth error (no user enumeration).** Unknown username and wrong
  password raise the same `AuthError("Invalid username or password.")`, so
  failures never reveal which field was wrong. Usernames are case-sensitive.
- **Mutating tools (`create_booking`, `cancel_booking`) are thin LangChain
  adapters.** They parse LLM args, call `domain/rules` + the repository, and
  translate results — no business logic inline. The repository is closed over by
  `build_booking_tools(repo)` rather than being a tool argument, so it never
  appears in the schema the LLM sees. The logged-in `user` is passed in by the
  caller; tools do no auth. A missing datetime offset is read as GMT-3 (the app's
  only timezone).
- **Two failure channels in the tools, by intent.** Rule violations
  (`BookingError` subclasses) **propagate** — the tools do *not* catch them, so
  central translation (#14) handles them uniformly and the tools stay thin.
  Malformed/unresolvable input (non-ISO datetime, unknown room) instead **returns
  a message string**, since that is the LLM mis-supplying arguments and a readable
  string lets it retry with corrected ones.
- **Cancel ownership + privacy.** `cancel_booking` deletes only if
  `booking.user == user`. A booking owned by someone else is refused with a
  generic "you cannot cancel booking '<id>'" that names neither the owner nor any
  booking detail; an unknown id gets a "not found" message. Ids are opaque
  8-char uuids, so "not found" reveals nothing enumerable.
- **Read-only tools reuse the overlap rule, never re-implement it.**
  `list_available_rooms` and `get_room_schedule` compute freeness through
  `_is_free`, a thin predicate wrapper around `domain.rules.check_overlap` (probe
  booking → catch `OverlapError`), so overlap logic stays defined in exactly one
  place.
- **"Available"/"free" = fully free for the entire requested range.** The brief
  doesn't define partial availability, so a room counts as available only if no
  existing booking overlaps *any* part of the range; back-to-back bookings
  (touching endpoints) leave the room free.
- **`list_available_rooms` optional `attendees` capacity filter.** With
  `attendees` omitted it lists all fully-free rooms; with it set, only free rooms
  whose capacity ≥ attendees. One tool serves both "show free rooms" and "show
  free rooms that fit my group" without a separate feature. Output is
  deterministic alphabetical (A→E).
- **`get_room_schedule` walks fixed 30-minute slots** from start to end, marking
  each free/occupied via the same `_is_free` predicate — read-only, no mutation.
- **Default LLM: `gpt-4o-mini`, configurable with `OPENAI_MODEL`.** It is a
  cost-effective tool-calling default for the booking agent, while the environment
  override allows deployments to change models without a code edit. `OPENAI_API_KEY`
  is loaded from the environment/`.env` and is never hardcoded or logged.
- **LLM temperature is `0`.** Booking-tool selection and responses should be as
  repeatable as the model API permits, which improves predictability and testability
  for an operational workflow.
- **Grounding and scope live in the system prompt as explicit clauses.** The assistant
  must call tools before claiming availability, capacity, bookings, schedules, or any
  other current state; it cannot rely on memory. It serves only booking operations for
  rooms A–E and refuses unrelated requests. This complements, rather than replaces,
  the guardrail → booking agent → verifier architecture.
- **Prompt caching uses OpenAI's server-side automatic prefix cache plus an explicit
  `prompt_cache_key`.** `ChatOpenAI` receives the stable key
  `promtior-booking-agent-v1` through `model_kwargs`; static prompt instructions come
  before the per-turn datetime/username suffix. Eligible requests (currently at least
  1,024 prompt tokens) can reuse exact prefixes. Issue #11 must bind unchanged tool
  definitions in stable order so they participate in the reusable request input; this
  layer does not wire tools or maintain a separate local response cache.

## Manual GitHub steps (not automated)

These are done in the GitHub UI, not in code:

1. Push a branch / open a PR to trigger the Action for the first time.
2. Enable branch protection with the CI check as a **required status check**
   (Settings → Branches).
