# Promtior Challenge — Meeting-Room Booking Chatbot

## Overview

Conversational chatbot for booking, listing, inspecting, and cancelling meeting rooms A–E at
Promtior's Cubo Itaú office. The implemented foundation currently includes the pure booking
domain, SQLite persistence, fixed-user authentication, four LangChain booking tools, and the
OpenAI model/prompt configuration, input guardrail, output-verifier unit, guarded booking
agent/tool loop, deterministic domain-error presentation, a static-fact-only semantic cache, and
a single-page Streamlit login/chat UI with session-scoped conversation memory. The complete UI →
guardrail → booking → verifier flow is wired.

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
│   ├── llm.py          # ChatOpenAI factory and grounded prompt builder
│   ├── guardrail.py    # Conservative SAFE/UNSAFE input classifier
│   ├── verifier.py     # Draft-answer grounding check against tool output
│   ├── error_presentation.py # Deterministic domain-error wording
│   └── orchestrator.py # Guardrail + tool loop + verified-response policy
├── cache/
│   └── semantic_cache.py # Static-fact-only in-memory semantic cache
└── ui/
    ├── session.py      # Tested auth gate, history, turn, and logout helpers
    └── streamlit_app.py # Thin single-page login and chat rendering
```

| Module | Responsibility and boundary | Why it lives there |
| --- | --- | --- |
| `domain/models.py` | Defines immutable, data-only `Room`, `User`, and `Booking` values. `Booking` stores a `room_id: str`, not a nested `Room`. | These are the shared domain vocabulary and have no infrastructure dependencies. Grouping them keeps the small, cohesive model together. |
| `domain/rules.py` | Validates 30-minute boundaries, positive duration up to three hours, capacity, non-empty title, and overlap. Rules take all inputs explicitly and raise typed domain errors. | Business rules remain pure and deterministic; they do no I/O and know nothing about SQLite, LangChain, or OpenAI. |
| `domain/exceptions.py` | Defines `BookingError` and one direct subclass per rule. | Callers can handle all rule failures uniformly or catch one precise rule without an elaborate hierarchy. |
| `data/db.py` | Opens SQLite, creates the `rooms`/`bookings` schema, and idempotently seeds rooms A–E. | Schema lifecycle and fixed persistence seed data belong at the infrastructure boundary, outside the domain. |
| `data/repository.py` | Maps booking rows to/from domain objects and implements parameterized save/find/delete operations. It persists only; it performs no booking validation. | Application code depends on repository methods rather than SQL details, while rules remain reusable and store-independent. |
| `auth/auth.py` | Authenticates the two fixed, case-sensitive challenge users using bcrypt hashes and returns a domain `User`. It does not use the bookings database. | The users are immutable challenge configuration, so a separate auth adapter avoids introducing mutable user persistence, roles, JWT, or session logic. |
| `tools/booking_tools.py` | Builds `create_booking`, `cancel_booking`, `list_available_rooms`, and `get_room_schedule`. It parses/returns LLM-friendly strings and delegates state to `BookingRepository` and validation to `domain.rules`; cancel denial and absence share one ID-free response. | LangChain is an outer adapter. Closing over the repository keeps infrastructure out of the LLM-visible tool schemas and keeps business rules in the domain. The indistinguishable cancel response prevents ownership enumeration. |
| `agent/llm.py` | Loads OpenAI configuration and builds the deterministic grounded system prompt. It contains no booking rules and does not bind tools. | Model-provider configuration is isolated from both business behavior and the future orchestration loop. Its injected datetime makes prompt construction testable and deterministic. |
| `agent/guardrail.py` | Uses an injected LLM and a strict structured-output prompt to classify one incoming message as SAFE or UNSAFE, returning a frozen `GuardrailResult`. It has no DB access, tool calls, or booking logic. | Input security is an agent-layer concern. Injecting the already-configured LLM avoids hidden construction/configuration and makes the classifier deterministic under test. |
| `agent/verifier.py` | Uses an injected LLM to compare a draft answer with this turn's serialized tool outputs, returning a frozen `VerifierResult` and an unsupported-claim reason when needed. It has no DB access, tool calls, or booking logic. | Output grounding is an agent-layer concern. Injecting the configured LLM and passing evidence explicitly keeps verification deterministic under test and separate from orchestration. |
| `agent/error_presentation.py` | Purely maps the Issue #4 `BookingError` types to fixed, actionable domain-language messages. It performs no I/O, LLM calls, or DB access and never echoes raw exception payloads. | Presentation belongs outside the domain vocabulary. The orchestrator calls it at its existing tool-error catch point, avoiding a second catch layer while keeping wording predictable and independently testable. |
| `agent/orchestrator.py` | Coordinates the guardrail, deterministic system prompt, server-bound tools, model → tool → model loop, and verifier. It records this turn's tool outputs, retries an ungrounded draft once without re-executing tools, and otherwise returns a safe fallback. It owns no SQL, auth, booking rules, or conversation storage. | Per-message control flow and the bounded verifier-failure policy belong in the outer agent layer. The orchestrator depends on sibling agent services and tool/data adapters; those layers never depend back on it, so business behavior stays independently testable. |
| `cache/semantic_cache.py` | Classifies only explicit static query categories, embeds eligible queries through an injected small/low-cost OpenAI embedder, and keeps answers in a process-local dictionary when cosine similarity exceeds a conservative threshold. It has no DB access or business logic. | The cache is an optional outer-layer optimization. Dependency injection prevents hidden API construction and makes similarity behavior deterministic in tests; ephemeral storage avoids coupling optimization data to booking persistence. |
| `ui/session.py` | Owns the testable server-side auth flag/username updates, LangChain message history mutations, auth-gate predicate, orchestrator-call assembly, and full logout reset. It imports no Streamlit and contains no booking rules, SQL, or model construction. | Session behavior is separated from rendering so security and multi-turn context can be unit-tested without a Streamlit runtime. It delegates authentication and message handling inward to the existing services. |
| `ui/streamlit_app.py` | Renders one login/chat page, gets credentials and chat input, displays messages, obtains the configured LLM through `build_llm`, and injects the current GMT-3 datetime into the session helper. | Streamlit is the outermost delivery detail. It depends inward on UI helpers, auth/agent services, and LangChain message types; no module depends back on it. Its render-only glue is the justified coverage omission. |

The domain depends only on the standard library. `data` and `auth` depend inward on domain
types; `tools` depends on the domain and data abstractions plus LangChain. SQL is confined to
the `data` layer: `db.py` owns schema/seed statements and `repository.py` owns booking CRUD
queries. Therefore, the implemented SQL boundary is the data layer—not `repository.py` alone.
All queries with external values are parameterized.
The orchestrator is the outer coordinator: dependencies flow from it toward the agent helpers,
tool adapter, repository, and domain exception contract, never from those layers back toward the
orchestrator. The UI sits outside that coordinator and depends inward; nothing in the domain,
data, tools, cache, or agent layers imports the UI.

## AI Workflow

The complete user-turn flow is **Streamlit UI → guardrail → booking agent + tool loop → output
verifier → Streamlit UI**. The UI first applies a single-page server-side authentication gate:
unauthenticated sessions see only the login form, while authenticated sessions see the chat. No
URL route or query parameter selects the protected view.

Inside the orchestrator, the flow is **guardrail → booking agent + tool loop → output verifier**:

1. **Guardrail (implemented and wired first):** `handle_message` calls
   `check_message(message, llm)` before it builds the system prompt, opens the repository, binds
   the booking agent, or invokes any tool. It marks clear prompt injection, improper data
   extraction, SQL-injection-looking input, and rule/scope-breaking requests UNSAFE. Ordinary
   booking language—including unusual or ambiguous phrasing—defaults to SAFE to minimize false
   positives. An unsafe result immediately returns one neutral refusal and exposes no classifier,
   prompt, database, or other-user details.
2. **Booking agent (implemented and wired):** For a safe message, the orchestrator builds the
   Issue #8 prompt from the caller-supplied GMT-3 datetime and username, then binds the Issue #7
   tools in their stable order. `create_booking` and `cancel_booking` are wrapped so the logged-in
   username is inserted server-side and absent from every model-visible schema. The explicit loop
   sends system prompt → caller-owned history → current message to the model, executes each tool
   call, returns a `ToolMessage` to the model, and repeats until the model returns a natural-language
   answer. At the existing tool-execution catch point, `BookingError` is passed to the pure
   deterministic presenter; raw exception text, identities, and internal IDs are never surfaced.
   The translated message becomes both the draft answer and turn evidence. It then follows the
   normal verifier step rather than bypassing output verification. Tool name/output evidence is
   retained internally for this turn.
3. **Output verifier (implemented and wired last):** As the final per-message step,
   `verify_response(draft_answer, tool_outputs, llm)` compares the drafted response with only the
   tool evidence produced in that turn. Room, availability, capacity, time, and booking claims
   must be supported. Greetings, conversational phrasing, and clarification questions are
   grounded; with no tool output, only those non-factual responses are grounded. An ungrounded
   draft is never emitted: the orchestrator performs one tool-free rewrite using the same evidence
   and verifies it again. If that retry is still ungrounded, it returns a neutral safe fallback.
   Tools are not re-executed during the retry, avoiding duplicate create/cancel side effects.

This is the same end-to-end flow depicted by the component diagram; the diagram and this README
describe one synchronized architecture, not separate target and implemented states.

The primary defense is architectural: the booking agent can call only constrained tools,
which use parameterized repository queries, fixed rooms, and an ownership check on cancellation;
it has no arbitrary-SQL surface. In addition, the model cannot set or override the acting user:
the username is injected by a server-side closure and `user` is absent from the exposed schemas.
This is what makes cancellation ownership enforceable—the model cannot ask the cancel tool to act
as the booking's actual owner. The LLM guardrail is a second layer for clear abuse, not the sole
security boundary. An unsafe turn costs one guardrail LLM call and stops. A safe grounded turn
costs one guardrail call, the booking agent's model round-trips (one initial generation plus one
after each tool-call batch), and one verifier call. An ungrounded turn adds one tool-free rewrite
call and one extra verifier call for the retry. Stable exact prefixes in the guardrail, booking,
retry, and verifier prompts can receive eligible OpenAI prompt-cache savings, offsetting part—but
not all—of that latency and token cost.

Anti-hallucination is deliberately layered across the full flow:

1. The Issue #8 system prompt requires every booking fact to be grounded in tool output.
2. The constrained booking tools are the only permitted source of room, availability, capacity,
   time, and booking facts.
3. The output verifier runs last against this turn's actual tool outputs and prevents every
   ungrounded draft from reaching the user.

No single layer is a complete guarantee; robustness comes from their combination. In particular,
the verifier is itself LLM-based, so the bounded retry and safe fallback reduce the chance and
impact of hallucination without claiming perfect detection.

Issue #8, now implemented, provides `build_llm` and `build_system_prompt`. The prompt requires
availability, capacity, booking, and schedule claims to come from tool calls; it also restricts
the assistant to rooms A–E. The prompt builder receives the logged-in username and current
datetime from its caller, converts the time to fixed GMT-3 (`-03:00`), and supplies absolute
today/tomorrow anchors in 24-hour format. It never reads the clock itself. The tools accept
absolute ISO datetimes and treat a missing offset as GMT-3.

The UI stores conversation history in Streamlit `session_state` as `HumanMessage` and
`AIMessage` objects. For each submitted turn, the session helper snapshots the prior history,
appends the new human message, and calls the orchestrator with the message, prior history,
server-side authenticated username, configured LLM, and `datetime.now()` computed in fixed GMT-3.
The orchestrator therefore receives multi-turn context without owning or mutating its storage and
without reading the clock. The returned reply is appended as an `AIMessage` and rendered. Logout
clears all session state and conversation history, while bookings remain durable in SQLite.

History is intentionally unbounded within this small challenge session. Very long sessions will
increase prompt tokens and latency. A production deployment should cap context to the last N
messages or summarize older turns; trimming/summarization is outside this scope.

The implemented semantic cache defines a narrow pre-LLM optimization seam for a future
composition step. Only an explicitly recognized static question such as room capacity or the
fixed room list may consult it before `handle_message`; a hit can avoid the LLM call, while a miss
continues into the flow above. Availability, schedules, bookings, free/occupied slots, and every
unrecognized query must bypass the cache entirely, so it can never sit in front of tool execution
for state-dependent questions. This UI issue does not construct the required embedding client or
wire that optional optimization into the turn path.

OpenAI prompt caching is engaged with the stable model-level key
`promtior-booking-agent-v1`, passed by `langchain-openai` as `prompt_cache_key`. OpenAI performs
the cache server-side automatically for eligible prompts (currently prompts of at least 1,024
tokens), and cache hits require an exact matching prefix. Accordingly, reusable grounding and
scope instructions appear first in the system prompt, while the changing datetime and username
appear at the end. The orchestrator binds tool definitions in a stable
create/cancel/list/schedule order, so eligible repeated system-prefix/tool-definition input can be
reused; the username itself is closure state, not changing schema content. Prompt caching lowers
the input cost of an eligible LLM call but still makes that call. The separate semantic cache can
avoid the call entirely, but only for repeated allowlisted static questions; it is not a general
prompt-response cache. The static dataset is just five rooms with fixed capacities, so the real
token savings here are modest. The mechanism demonstrates semantic caching and establishes a
safe pattern rather than addressing a major project cost driver. Prompt-cache usage remains
observable through the API response's cached-token metadata.

## Environment and configuration

Copy `.env.example` to `.env` for local development. `.env` is gitignored and must never be
committed.

| Variable | Required | Description |
| --- | --- | --- |
| `OPENAI_API_KEY` | Yes | OpenAI credential loaded with `python-dotenv`; never logged or hardcoded. |
| `OPENAI_MODEL` | No | Chat model name. Defaults to `gpt-4o-mini`, a cost-effective model with tool-calling support. |

These are the only environment variables currently read by application code. The orchestrator
passes the relative default `bookings.db` path directly to `data.db.connect`; it has no environment
variable. `SemanticCache` reads no environment variables and constructs no client; the future
composition layer supplies a small/low-cost OpenAI embedder configured with the existing API key,
so this issue adds no configuration. Room capacities and the two challenge usernames/shared
password are fixed in code. `.env.example` contains placeholders for both OpenAI variables, and
`.gitignore` explicitly excludes `.env`.

Run the single-page application from the repository root:

```bash
streamlit run app/ui/streamlit_app.py
```

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
  deeper hierarchy (out of scope). Callers can catch either the common base or a specific rule.
  Issue #4 defines this domain vocabulary; Issue #14 presents it to users without changing the
  exception types. Overlap messages stay neutral and never name the conflicting booking's owner.

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
  the orchestrator can translate them centrally through Issue #14's deterministic presenter.
  Malformed/unresolvable input (non-ISO datetime, unknown room) instead **returns a message
  string**, allowing the agent to retry with corrected arguments.
- **Cancel ownership + privacy.** `cancel_booking` deletes only if
  `booking.user == user`. A booking owned by someone else and an unknown booking produce the same
  generic response, which names neither the owner, booking details, nor the supplied ID. This
  prevents ownership/existence enumeration. Booking IDs are the first eight hex characters of a
  generated UUID and are enforced as primary keys by SQLite.
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
  1,024 prompt tokens) can reuse exact prefixes. Issue #11 now binds the tool definitions
  in stable order so they participate in the reusable request input; the LLM layer itself
  does not wire tools or maintain a separate local response cache.

### Issue #9 — Guardrail input classifier

- **The guardrail is a second layer of defense, not the security boundary.** It blocks clear
  prompt injection, improper data extraction, SQL-injection-looking text, and attempts to break
  booking scope/rules. The primary defense remains the constrained, parameterized booking-tool
  architecture, which exposes no arbitrary-SQL operation.
- **The configured LLM is injected into `check_message`.** The guardrail neither builds a model
  nor accesses the DB or booking rules. A strict structured classification is converted into a
  small frozen `GuardrailResult`; UNSAFE messages receive one neutral refusal that discloses no
  internal reason or data.
- **Classification defaults to SAFE for ordinary booking language.** Only clear abuse is marked
  UNSAFE, including when legitimate booking phrasing is unusual or ambiguous. This deliberately
  minimizes false positives; the constrained tool layer still enforces actual permissions and
  booking rules.
- **Defense in depth costs one extra LLM call per message.** That adds latency and input-token
  cost. Stable classifier prompts and the configured OpenAI prompt cache mitigate eligible
  repeated prefixes. Issue #11 calls the guardrail before constructing or invoking the booking
  agent, so an unsafe turn ends after classification.

### Issue #10 — Output verifier

- **The verifier is a second grounding check after draft generation.** The primary mechanism is
  the Issue #8 system prompt requiring room, availability, capacity, time, and booking facts to
  come from tools. The verifier compares the draft only with this turn's tool outputs and reports
  an unsupported claim; it does not replace prompt grounding or tool constraints.
- **The configured LLM and evidence are injected into `verify_response`.** The verifier builds no
  model and accesses neither the DB nor booking rules. Tool outputs are serialized with the draft
  as evidence for one strict structured decision, producing a frozen `VerifierResult`.
- **Non-factual no-tool turns are grounded.** Greetings, conversational phrasing, and requests
  for clarification do not require tool evidence, preventing the verifier from over-flagging
  normal dialogue. Specific room or booking facts still require tool support even when the turn
  contains no tool output.
- **Output verification costs one extra LLM call after each draft.** This adds latency and
  input-token cost on top of the guardrail and booking calls. Stable verifier prompts and the
  configured OpenAI prompt cache mitigate eligible repeated prefixes; Issue #11 invokes the
  verifier last and owns the regeneration/fallback policy.

### Issue #11, commit 1 — Guarded orchestrator and tool loop

- **The acting username is bound server-side and omitted from every tool schema.** The
  orchestrator wraps `create_booking` and `cancel_booking` with closures that inject the
  authenticated username; a model-supplied `user` value is ignored and cannot override it. This
  is required for enforceable cancellation ownership: otherwise the model could name the actual
  owner and bypass the tool's `booking.user == user` check. Read-only tool schemas already have no
  `user` argument.
- **The orchestrator receives history; it does not own or persist it.** The caller supplies
  LangChain message objects for each turn. The orchestrator places them in the prompt without
  mutating them, while Issue #13's UI remains responsible for session-state storage and logout
  cleanup. Booking persistence stays separate in SQLite.
- **A small explicit LangChain message loop coordinates tool calls.** The installed LangChain API
  exposes model tool binding directly, so no second agent abstraction is needed: model tool calls
  are executed, returned as `ToolMessage` evidence, and repeated until a final answer. Each turn
  also returns its tool name/output records internally for the verifier. Domain `BookingError`
  failures are caught here and passed to Issue #14's pure presenter; no second catch layer was
  added.
- **The orchestrator uses a turn-scoped connection to `bookings.db`.** It composes the existing
  repository and tool factory only after the guardrail passes, then closes the connection after
  the turn. This keeps SQL in `data`, business rules in `domain`, and persistence out of the LLM
  schema while preserving bookings between messages.

### Issue #11, commit 2 — Verifier policy and completed flow

- **An ungrounded draft gets one evidence-only retry, then a safe fallback.** The first draft is
  checked against this turn's captured tool outputs. If rejected, a tool-free model call rewrites
  it from the same evidence and the verifier checks that retry once. A second rejection returns
  `I couldn't produce a reliable answer. Please try again.` Neither ungrounded draft can be
  emitted. One bounded retry offers a chance to repair phrasing while preventing infinite loops;
  reusing evidence without rerunning tools also prevents duplicate booking or cancellation side
  effects.
- **Verification deliberately trades cost for defense in depth.** A safe grounded turn uses one
  guardrail call, the required booking-agent round-trips, and one verifier call. A retry adds one
  tool-free rewrite plus one extra verifier call. Exact repeated prompt prefixes remain eligible
  for OpenAI prompt caching, which offsets part of the added latency and token usage but does not
  remove it.

### Issue #12 — Static-only semantic cache

- **Caching is explicit-allowlist only and defaults to bypass.** Only clearly static room facts,
  currently capacities and the fixed A–E room list, are eligible. Availability, schedules, user
  bookings, and free/occupied slots always bypass the cache, as does every query the classifier
  does not recognize. Serving stale availability would produce an incorrect booking answer, so a
  miss is safer than an ambitious classification or a wrong hit.
- **Semantic matches must exceed a high similarity threshold.** The named `0.92` cosine threshold
  is deliberately conservative: equivalent phrasings can reuse an answer, while borderline or
  distant queries miss and continue to the normal LLM/tool flow. The embedding provider is
  injected rather than constructed by the cache, keeping provider configuration outside the
  module and tests deterministic without live API calls.
- **Cache entries live only in process memory.** They are not written to SQLite because cached
  responses are disposable optimization artifacts, not application data. Process restarts may
  discard them without affecting booking correctness, and persistence would add coupling with no
  benefit at this scale.
- **The expected savings are intentionally modest.** There are only five rooms and a small set of
  fixed facts. This feature demonstrates the technique and establishes a safe default-bypass
  caching pattern; it is not presented as a major token-cost reduction for this project. It
  complements prompt caching: prompt caching reduces repeated system-prompt/tool-definition input
  cost, whereas a semantic-cache hit avoids the LLM call altogether.

### Issue #13 — Thin Streamlit UI and session memory

- **Authentication gates one page through server-side `st.session_state`, not JWT or routing.**
  The app chooses login versus chat solely from the session's `authenticated` flag. Streamlit is
  a stateful single-page app here: there is no post-login URL, protected route, or query parameter
  a user can navigate to directly, and browser input cannot choose the server-side flag. JWT and
  session-cookie machinery would not close an additional route-bypass vector in this design.
  This is proportionate for the challenge, not a production-grade session system:
  `session_state` is ephemeral, a server restart or page reload returns the user to login (failing
  safe), and there is no configurable expiry or remote invalidation.
- **Conversation state and booking state have deliberately different lifetimes.** LangChain
  `HumanMessage`/`AIMessage` history lives only in `session_state` and is cleared completely on
  logout. Bookings remain in SQLite and therefore survive logout. This matches the requirement
  for multi-turn conversation without confusing chat memory with durable business data.
- **The UI owns the clock boundary.** `streamlit_app.py` computes `datetime.now()` with the fixed
  GMT-3 timezone and injects that value into the orchestrator call. Agent prompt and orchestration
  modules continue to receive time as data, keeping their tests deterministic.
- **Rendering stays separate from session behavior.** `streamlit_app.py` contains only login,
  chat, and logout widgets plus dependency wiring and is the justified coverage omission.
  `ui/session.py` contains the fully covered auth-state, history-ordering, trusted-username,
  prior-context, and reset behavior without importing Streamlit. The UI is the outermost detail:
  it depends inward and nothing depends on it.
- **History is unbounded only for this scoped implementation.** Token usage and latency grow with
  long conversations. Production should retain the last N messages or summarize older context;
  neither policy is added here because the challenge does not define a context budget.

### Issue #14 — Deterministic domain-error presentation

- **Issue #4 defines errors; Issue #14 only presents them.** The existing flat `BookingError`
  subclasses remain the domain vocabulary and no new hierarchy is introduced. The agent-layer
  `present_booking_error` function maps those types to fixed text with no I/O, DB access, or LLM
  call. Deterministic mapping was chosen over generated wording so messages are predictable,
  testable, and cannot hallucinate a rule that does not exist.
- **Error text exposes neither identity nor internal identifiers.** Fixed messages use room,
  date, time, title, and attendee language rather than exception names, stack traces, or database
  terms, and raw exception payloads are never echoed. Overlap text reveals no conflicting owner;
  cancel denial and absence return the same generic ID-free response. Suppressing booking IDs in
  successful confirmations, listings, and the wider cancellation conversation remains Issue #18;
  this decision covers error paths only.
- **Failures state the valid expected value.** Slot messages name `:00`/`:30` boundaries,
  duration requires an end after the start and no more than three hours, capacity states the
  permitted minimum and that room's numeric capacity, title rejects blanks, and overlap explains
  that some or all of the range is already booked. Issue #18 will pre-validate conversationally,
  so errors that still reach this layer are edge cases where actionable guidance matters most.
  No alternative room or time is suggested because alternative generation is out of scope.
- **Translation uses the orchestrator's existing catch point and still passes verification.** A
  caught domain error becomes a normal draft answer and captured tool evidence, then proceeds to
  the verifier like any other response. This adds neither a second exception boundary nor a path
  around the guardrail → booking → verifier workflow.
