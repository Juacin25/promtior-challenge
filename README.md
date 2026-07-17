# Promtior Challenge — Meeting-Room Booking Chatbot

## Overview

Conversational chatbot for booking, listing, inspecting, and cancelling meeting rooms A–E at
Promtior's Cubo Itaú office. The implemented foundation currently includes the pure booking
domain, SQLite persistence, fixed-user authentication, four LangChain booking tools, and the
OpenAI model/prompt configuration layer. The agent orchestrator and user interface are not yet
implemented.

## Architecture

Clean-Architecture layering keeps dependencies pointing toward the pure domain. The following
tree shows the current repository state; placeholder packages are identified explicitly and do
not imply implemented behavior.

```text
app/
├── domain/
│   ├── models.py       # Frozen Room, User, and Booking dataclasses
│   ├── rules.py        # Pure booking-rule validation
│   └── exceptions.py   # Flat typed booking-rule errors
├── data/
│   ├── db.py           # SQLite connection, schema, and fixed-room seed
│   └── repository.py   # Parameterized Booking persistence and row mapping
├── auth/
│   └── auth.py         # Fixed User1/User2 authentication with bcrypt
├── tools/
│   └── booking_tools.py # Four LangChain adapters over rules + repository
├── agent/
│   └── llm.py          # ChatOpenAI factory and grounded prompt builder
├── cache/__init__.py   # Empty package marker; semantic cache not built
└── ui/__init__.py      # Empty package marker; Streamlit UI not built
```

| Module | Responsibility and boundary | Why it lives there |
| --- | --- | --- |
| `domain/models.py` | Defines immutable, data-only `Room`, `User`, and `Booking` values. `Booking` stores a `room_id: str`, not a nested `Room`. | These are the shared domain vocabulary and have no infrastructure dependencies. Grouping them keeps the small, cohesive model together. |
| `domain/rules.py` | Validates 30-minute boundaries, positive duration up to three hours, capacity, non-empty title, and overlap. Rules take all inputs explicitly and raise typed domain errors. | Business rules remain pure and deterministic; they do no I/O and know nothing about SQLite, LangChain, or OpenAI. |
| `domain/exceptions.py` | Defines `BookingError` and one direct subclass per rule. | Callers can handle all rule failures uniformly or catch one precise rule without an elaborate hierarchy. |
| `data/db.py` | Opens SQLite, creates the `rooms`/`bookings` schema, and idempotently seeds rooms A–E. | Schema lifecycle and fixed persistence seed data belong at the infrastructure boundary, outside the domain. |
| `data/repository.py` | Maps booking rows to/from domain objects and implements parameterized save/find/delete operations. It persists only; it performs no booking validation. | Application code depends on repository methods rather than SQL details, while rules remain reusable and store-independent. |
| `auth/auth.py` | Authenticates the two fixed, case-sensitive challenge users using bcrypt hashes and returns a domain `User`. It does not use the bookings database. | The users are immutable challenge configuration, so a separate auth adapter avoids introducing mutable user persistence, roles, JWT, or session logic. |
| `tools/booking_tools.py` | Builds `create_booking`, `cancel_booking`, `list_available_rooms`, and `get_room_schedule`. It parses/returns LLM-friendly strings and delegates state to `BookingRepository` and validation to `domain.rules`. | LangChain is an outer adapter. Closing over the repository keeps infrastructure out of the LLM-visible tool schemas and keeps business rules in the domain. |
| `agent/llm.py` | Loads OpenAI configuration and builds the deterministic grounded system prompt. It contains no booking rules and does not bind tools. | Model-provider configuration is isolated from both business behavior and the future orchestration loop. Its injected datetime makes prompt construction testable and deterministic. |

The domain depends only on the standard library. `data` and `auth` depend inward on domain
types; `tools` depends on the domain and data abstractions plus LangChain. SQL is confined to
the `data` layer: `db.py` owns schema/seed statements and `repository.py` owns booking CRUD
queries. Therefore, the implemented SQL boundary is the data layer—not `repository.py` alone.
All queries with external values are parameterized.

## AI Workflow

The target design is **guardrail → booking agent → output verifier**, but that sequence is not
yet executable: the guardrail, verifier, and orchestrator modules do not exist. Issue #7 provides
the four LLM-callable tool definitions. They can create a booking, cancel an owned booking, list
rooms fully free for a range, and show a room's 30-minute schedule. Tools never write arbitrary
SQL; they call the parameterized repository and domain rules.

Issue #8, now implemented, provides `build_llm` and `build_system_prompt`. The prompt requires
availability, capacity, booking, and schedule claims to come from tool calls; it also restricts
the assistant to rooms A–E. The prompt builder receives the logged-in username and current
datetime from its caller, converts the time to fixed GMT-3 (`-03:00`), and supplies absolute
today/tomorrow anchors in 24-hour format. It never reads the clock itself. The tools accept
absolute ISO datetimes and treat a missing offset as GMT-3.

Issue #11 will bind the current prompt, model, tool definitions, and future guardrail/verifier
into the per-message loop. Until then, no component invokes the LLM or tools as an agent, and no
output verifier enforces grounding at runtime. Conversation memory, the Streamlit chat flow, and
the semantic cache are also not implemented. Bookings alone currently have persistence through
SQLite.

OpenAI prompt caching is engaged with the stable model-level key
`promtior-booking-agent-v1`, passed by `langchain-openai` as `prompt_cache_key`. OpenAI performs
the cache server-side automatically for eligible prompts (currently prompts of at least 1,024
tokens), and cache hits require an exact matching prefix. Accordingly, reusable grounding and
scope instructions appear first in the system prompt, while the changing datetime and username
appear at the end. When Issue #11 binds tool definitions, it must preserve their content and
ordering so the repeated system-prefix/tool-definition input can become reusable. Because tools
are not yet bound, their definitions do not currently participate in an LLM request. There is no
local prompt-response cache and no claim that short, ineligible prompts produce a cache hit;
usage will be observable through the API response's cached-token metadata once invocation exists.

## Environment and configuration

Copy `.env.example` to `.env` for local development. `.env` is gitignored and must never be
committed.

| Variable | Required | Description |
| --- | --- | --- |
| `OPENAI_API_KEY` | Yes | OpenAI credential loaded with `python-dotenv`; never logged or hardcoded. |
| `OPENAI_MODEL` | No | Chat model name. Defaults to `gpt-4o-mini`, a cost-effective model with tool-calling support. |

These are the only environment variables currently read by application code. The SQLite path is
passed directly to `data.db.connect`; it has no environment variable. Room capacities and the two
challenge usernames/shared password are fixed in code. `.env.example` contains placeholders for
both OpenAI variables, and `.gitignore` explicitly excludes `.env`.

## Decision Log

Entries are grouped chronologically by the issue that introduced the implemented decision.

### Issue #1 — Project scaffolding

- **Dependency manager: `pyproject.toml`.** Single file holds deps *and* tool
  config (pytest, coverage, ruff), so no separate `requirements.txt` /
  `pytest.ini` / `ruff.toml`. Runtime deps unpinned; dev tools under the `dev`
  extra.

### Issue #2 — CI pipeline

- **Coverage: branch on, `source = ["app"]`, `fail_under = 100`.** The gate lives
  in `pyproject.toml` (single source); CI runs plain `pytest` and inherits it.
  The only configured file omission is `app/ui/streamlit_app.py`, reserved for
  logic-free UI glue; that file does not exist yet, so every currently implemented
  module is measured. The report also recognizes explicit `# pragma: no cover`
  lines, but none are currently present in `app`. Business logic is not omitted.
- **Lint: ruff** with `E,F,I,W,UP,B` rule sets and line length 100.
- **CI triggers on every push and every pull request.** The current workflow uses
  `on: [push, pull_request]` with no branch filters, so PRs are not limited to
  `develop`/`main`. It checks out the repository, installs Python 3.11 dependencies,
  runs `ruff check .`, then runs `pytest`; the inherited coverage gate fails CI below
  100%.

### Issue #3 — Domain models

- **Domain models: `Booking` references its room by `room_id: str`,** not a
  `Room` object — avoids duplicating room state and mirrors the persisted
  `bookings.room_id` text column. The current SQLite schema does not declare a
  foreign-key constraint.
- **Domain entities grouped in one `models.py`.** `Room`, `User` and `Booking`
  are the shared domain vocabulary and evolve together (high cohesion); no
  per-class files. They are frozen dataclasses (immutable, value equality) and
  data-only — all validation lives in `domain/rules.py`.

### Issue #4 — Domain rules and errors

- **Domain rules are pure functions in `domain/rules.py`.** Each rule (slot
  alignment, duration ≤ 3h, capacity, title, overlap) is single-responsibility,
  does no I/O, and takes its inputs directly — the overlap check receives the
  existing bookings as a list, so the repository supplies data later and rules
  stay decoupled from persistence.
- **Flat typed exceptions in `domain/exceptions.py`.** One subclass per rule
  (`SlotAlignmentError`, `DurationError`, `CapacityError`, `TitleRequiredError`,
  `OverlapError`) inheriting directly from a single `BookingError` base — no
  deeper hierarchy (out of scope). Current callers can catch either the common
  base or a specific rule; no surface-layer translator is implemented yet.
  Overlap messages stay neutral and never name the conflicting booking's owner.

### Issue #5 — SQLite persistence

- **SQLite's boundary is the `data` layer.** `data/db.py` contains schema and seed
  SQL; `data/repository.py` contains parameterized booking CRUD queries. No other
  layer uses SQL, and the repository performs no business validation. Initialization
  is idempotent through `CREATE TABLE IF NOT EXISTS` and `INSERT OR IGNORE`.
- **Room capacities are fixed and seeded on init:** A=2, B=2, C=4, D=8, E=10
  (single source: `ROOM_CAPACITIES` in `db.py`).
- **Datetimes stored as ISO strings** (`isoformat()` / `fromisoformat()`),
  preserving the supplied timezone offset in a simple, human-readable form. The
  tool layer treats offset-less input as GMT-3 (`-03:00`); the repository itself
  does not rewrite timezone offsets.

### Issue #6 — Authentication

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

### Issue #7 — Booking tools

- **Mutating tools (`create_booking`, `cancel_booking`) are thin LangChain
  adapters.** They parse LLM args, call `domain/rules` + the repository, and
  translate results — no business logic inline. The repository is closed over by
  `build_booking_tools(repo)` rather than being a tool argument, so it never
  appears in the schema the LLM sees. The logged-in `user` is passed in by the
  caller; tools do no auth. A missing datetime offset is read as GMT-3 (the app's
  only timezone).
- **Two failure channels in the tools, by intent.** Rule violations
  (`BookingError` subclasses) **propagate** — the tools do *not* catch them, so
  callers currently receive the typed error directly. No central user-facing
  translator exists yet. Malformed/unresolvable input (non-ISO datetime, unknown
  room) instead **returns a message string**, allowing a future agent to retry with
  corrected arguments.
- **Cancel ownership + privacy.** `cancel_booking` deletes only if
  `booking.user == user`. A booking owned by someone else is refused with a
  generic "you cannot cancel booking '<id>'" that names neither the owner nor any
  booking detail; an unknown id gets a different "not found" message. Thus the
  implementation hides other-user data but does distinguish unknown IDs from
  existing IDs the caller does not own. Booking IDs are the first eight hex
  characters of a generated UUID and are enforced as primary keys by SQLite.
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
  free rooms that fit my group" without a separate feature.
- **Available-room output is deterministic and alphabetical (A→E).** The tool
  iterates over sorted room-capacity entries so repeated reads have stable ordering.
- **`get_room_schedule` walks fixed 30-minute slots** from start to end, marking
  each free/occupied via the same `_is_free` predicate — read-only, no mutation.

### Issue #8 — LLM configuration and prompt caching

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
