# Promtior Challenge — Meeting-Room Booking Chatbot

## Overview

Conversational chatbot for booking, listing, inspecting, and cancelling meeting rooms A–E at
Promtior's Cubo Itaú office. The implemented foundation currently includes the pure booking
domain, SQLite persistence, fixed-user authentication, four LangChain booking tools, and the
OpenAI model/prompt configuration, input guardrail, output-verifier unit, guarded booking
agent/tool loop, mandatory booking slot collection, deterministic booking/output presentation,
an implemented-and-tested but intentionally unwired static-fact semantic-cache seam (see
[Caching](#caching)), and a single-page Streamlit login/chat UI with session-scoped conversation
memory. The complete live UI → guardrail → booking → verifier flow is wired without that optional
cache seam.

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
│   ├── conversation.py # Slot pre-validation + ID-free output formatting
│   └── orchestrator.py # Guardrail + tool loop + verified-response policy
├── cache/
│   └── semantic_cache.py # Tested static-fact cache seam; intentionally unwired
└── ui/
    ├── session.py      # Tested auth gate, history, turn, and logout helpers
    └── streamlit_app.py # Thin single-page login and chat rendering
```

| Module | Responsibility and boundary | Why it lives there |
| --- | --- | --- |
| `domain/models.py` | Defines immutable, data-only `Room`, `User`, and `Booking` values. `Booking` stores a `room_id: str` and the explicitly supplied attendee count. | These are the shared domain vocabulary and have no infrastructure dependencies. Persisting attendees is required so authenticated booking listings can report grounded data rather than infer it. |
| `domain/rules.py` | Validates 30-minute boundaries, positive duration up to three hours, capacity, non-empty title, and overlap. Rules take all inputs explicitly and raise typed domain errors. | Business rules remain pure and deterministic; they do no I/O and know nothing about SQLite, LangChain, or OpenAI. |
| `domain/exceptions.py` | Defines `BookingError` and one direct subclass per rule. | Callers can handle all rule failures uniformly or catch one precise rule without an elaborate hierarchy. |
| `data/db.py` | Opens SQLite, creates the `rooms`/`bookings` schema, idempotently seeds rooms A–E, and adds the attendee column to a legacy database when needed. | Schema lifecycle, compatibility migration, and fixed persistence seed data belong at the infrastructure boundary, outside the domain. |
| `data/repository.py` | Maps booking rows—including attendee count—to/from domain objects, enforces the single fixed-offset GMT-3 datetime representation without converting it, and implements parameterized save/find/delete operations. It persists only; it performs no booking validation. | Application code depends on repository methods rather than SQL details, while the persistence boundary prevents mixed datetime representations and rules remain store-independent. |
| `auth/auth.py` | Authenticates the two fixed, case-sensitive challenge users using bcrypt hashes and returns a domain `User`. It does not use the bookings database. | The users are immutable challenge configuration, so a separate auth adapter avoids introducing mutable user persistence, roles, JWT, or session logic. |
| `tools/booking_tools.py` | Builds `create_booking`, `cancel_booking`, `list_available_rooms`, and `get_room_schedule`. Successful writes return the persisted/deleted `Booking`; read and input-failure results remain strings. It accepts only fixed-offset GMT-3 ISO datetimes, delegates state to `BookingRepository` and validation to `domain.rules`, and keeps cancel denial and absence identical. | Returning the entity makes write confirmation evidence complete at its source. Closing over the repository keeps infrastructure out of the LLM-visible schemas and business rules in the domain. |
| `agent/llm.py` | Loads OpenAI configuration and builds the deterministic grounded system prompt, including explanatory five-field collection, unsupported-action guidance, direct read-only tool routing, room choice, cancellation, and the exact GMT-3 confirmation contract. It does not bind tools or perform validation. | Conversational instructions belong with agent behavior. Its injected datetime makes prompt construction deterministic, while authoritative booking validation remains in the domain. |
| `agent/guardrail.py` | Uses an injected LLM and a strict structured-output prompt to classify one incoming message as SAFE or UNSAFE, returning a frozen `GuardrailResult`. Unsafe requests receive fixed guidance about the supported booking actions. It has no DB access, tool calls, or booking logic. | Input security is an agent-layer concern. Injecting the already-configured LLM avoids hidden construction/configuration and makes the classifier deterministic under test; clearer refusal text does not weaken the short-circuit. |
| `agent/verifier.py` | Uses an injected LLM to compare a draft with the user message, current/tomorrow date anchors, fixed conversational/action boundaries, and serialized tool outputs. It returns a frozen `VerifierResult` and logs rejected reasoning/evidence server-side. User text grounds intent and clarification; state claims require tools, and draft dates/times must exactly match GMT-3 evidence. | Output grounding is an agent-layer concern. Explicit date and action anchors prevent valid guidance from being rejected while continuing to block invented room or booking facts. |
| `agent/error_presentation.py` | Purely maps the Issue #4 `BookingError` types plus the attempted safe booking fields to fixed, actionable domain-language messages. It performs no I/O, LLM calls, or DB access and never echoes raw exception payloads. | Rule-error presentation belongs outside the domain vocabulary. The orchestrator calls it at its existing tool-error catch point, avoiding a second catch layer while keeping wording predictable and independently testable. |
| `agent/conversation.py` | Purely performs conversational create pre-validation, aggregates missing fields while acknowledging supplied details, renders create/cancel confirmations from the `Booking` returned by the write tool, labels GMT-3 evidence, partitions schedule slots into available/occupied sections, and resolves cancellation descriptions against supplied owned bookings. An omitted date uses the injected default date and requires confirmation. It performs no SQL, auth, LLM calls, or repository access. | Rendering and clarification belong in deterministic presentation helpers. Inputs and tool invokers remain injected, making tool suppression, formatting, privacy, and ambiguity fully testable. |
| `agent/orchestrator.py` | Coordinates the guardrail, deterministic system prompt, server-bound tool adapters, model → tool → model loop, and verifier. It adds authenticated list/cancel adapters, passes attempted tool arguments to deterministic error presentation, and binds the injected current date without changing the four underlying tool signatures. It owns no SQL, auth, booking rules, or conversation storage. | Per-message control flow and the bounded verifier-failure policy belong in the outer agent layer. The orchestrator depends on sibling agent services and tool/data adapters; those layers never depend back on it, so business behavior stays independently testable. |
| `cache/semantic_cache.py` | Classifies only explicit static query categories, embeds eligible queries through an injected embedder, and keeps answers in a process-local dictionary when cosine similarity exceeds a conservative threshold. It has no DB access or business logic and is not imported or instantiated by the live application. | The designed-and-tested cache is an intentionally unwired outer-layer optimization seam. Dependency injection prevents hidden API construction and makes similarity behavior deterministic in tests; ephemeral storage avoids coupling optimization data to booking persistence. |
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

Issue #18 made one explicitly approved persistence exception to its original agent-only boundary:
`Booking`, the SQLite schema, and repository mapping now carry `attendees`, because that value did
not previously exist anywhere durable and therefore could not be shown truthfully in “my
bookings.” No domain validation rule, repository operation, or signature of the four Issue #7
booking tools changed. The schema/persistence change is kept as a separate review/commit unit from
the agent behavior that consumes it.

## AI Workflow

The complete user-turn flow is **Streamlit UI → guardrail → booking agent + tool loop → output
verifier → Streamlit UI**. The UI first applies a single-page server-side authentication gate:
unauthenticated sessions see only the login form, while authenticated sessions see the chat. No
URL route or query parameter selects the protected view.

Inside the orchestrator, the flow is **guardrail → booking agent + tool loop → output verifier**:

1. **Guardrail (implemented and wired first):** `handle_message` calls
   `check_message(message, llm)` before it builds the system prompt, opens the repository, binds
   the booking agent, or invokes any tool. It marks clear prompt injection, improper data
   extraction, SQL-injection-looking input, and off-domain requests UNSAFE. Ordinary booking
   language—including unusual, ambiguous, or understood-but-unsupported booking actions—defaults
   to SAFE so the booking agent can explain the exact limitation. An unsafe result immediately
   returns plain guidance that the assistant can create, list, inspect, or cancel only the
   authenticated user's meeting-room bookings; it exposes no classifier, prompt, database, or
   other-user details.
2. **Booking agent (implemented and wired):** For a safe message, the orchestrator builds the
   Issue #8 prompt from the caller-supplied GMT-3 datetime and username, then binds the Issue #7
   tools in their stable order. Before creation, the booking agent collects room → date → start
   and end → non-blank title → attendee count, asking for every missing value together, briefly
   explaining why it is needed, acknowledging already-understood values, and never supplying a
   default. Multi-room, recurring/repeating, past, modification, and other-user requests do not
   call tools or partially execute: the agent states that the action is unsupported and explains
   the supported single-future-booking and authenticated-user read/cancel operations. The
   server-bound create adapter repeats the friendly boundary/duration/capacity/title
   checks before invoking the tool; this is a UX layer, while Issue #4 remains authoritative.
   Direct availability questions call `list_available_rooms`; direct room-schedule/free-slot
   questions call `get_room_schedule` once their room/date/range is known and present every exact
   30-minute slot under available or occupied without owner/title/ID details. These read-only paths
   ask only for missing range details, not creation-only title or attendee fields. When only the
   room is missing from a booking request, the agent calls `list_available_rooms`, presents every
   match, and waits for the user's choice even if only one matches. `create_booking` and descriptive
   `cancel_booking` are wrapped so the logged-in username is inserted server-side and absent from
   every model-visible schema. A separate no-argument `list_my_bookings` adapter reads only that
   authenticated user's records. Cancellation filters those same owned records by the supplied
   room, date, start/end time, and/or title. An omitted date is resolved against the injected
   current date and the ID-free candidate is shown for confirmation; cancellation does not run on
   that first turn. With an explicit date, one match invokes the existing ID-based tool internally,
   several return ID-free choices, and none return a clear no-match response. The explicit loop
   sends system prompt → caller-owned history → current message to the model, executes each tool
   call, returns a `ToolMessage` to the model, and repeats until the model returns a natural-language
   answer. The loop has a fixed eight-step ceiling and returns the safe fallback if a model keeps
   requesting tools. Deterministic create corrections—including the three-hour limit—terminate the
   loop immediately instead of being sent back for another model attempt. Adapters preserve the
   accepted GMT-3 wall time unchanged, format slot/list/confirmation evidence, preserve schedule
   room/date context, and remove IDs before it
   reaches the model or verifier. At the existing tool-execution catch point, `BookingError` and
   the attempted safe booking fields are passed to the pure deterministic presenter. It names the
   violated rule and expected value, reflects the user's requested value, and gives a direct
   correction; raw exception text, identities, and internal IDs are never surfaced.
   Creation evidence includes an explicit `GMT-3` label, and the model must copy its date/time
   verbatim rather than convert, recalculate, or adjust it.
   The translated message becomes both the draft answer and turn evidence. It then follows the
   normal verifier step rather than bypassing output verification. Tool name/output evidence is
   retained internally for this turn.
3. **Output verifier (implemented and wired last):** As the final per-message step,
   `verify_response(..., user_message=..., current_dt=...)` compares the draft with three explicit
   evidence classes: user intent, deterministic current/tomorrow dates, and tool output. The user
   message may ground only request details the
   user supplied—desired room, date/time, title, and attendee count—so a no-tool clarification may
   safely repeat them, identify missing fields, and explain fixed supported-action boundaries.
   Rule-error wording is grounded by the captured tool result. Availability, capacity, room
   existence, and created/cancelled/persisted state still require tool output. Successful write
   adapters render every confirmation field from
   the returned `Booking`, so verification is possible by construction. An ungrounded draft is
   never emitted: one rejection returns the neutral fallback promptly. Its reason and tool evidence
   are logged server-side while the user sees only the generic message.

This is the same end-to-end flow depicted by the component diagram
([doc/component-diagram.svg](doc/component-diagram.svg), editable source
[doc/component-diagram.drawio](doc/component-diagram.drawio)); the diagram and this README
describe one synchronized architecture, not separate target and implemented states.

The primary defense is architectural: the booking agent can call only constrained tools,
which use parameterized repository queries, fixed rooms, and an ownership check on cancellation;
it has no arbitrary-SQL surface. In addition, the model cannot set or override the acting user:
the username is injected by a server-side closure and `user` is absent from the exposed schemas.
This is what makes cancellation ownership enforceable—the model cannot ask the cancel tool to act
as the booking's actual owner. The LLM guardrail is a second layer for clear abuse, not the sole
security boundary. An unsafe turn costs one guardrail LLM call and stops. A safe grounded turn
costs one guardrail call, the booking agent's model round-trips (one initial generation plus one
   after each tool-call batch), and one verifier call. An ungrounded turn stops there; it adds no
   rewrite or second verifier call. Stable exact prefixes in the guardrail, booking, and verifier
   prompts can receive eligible OpenAI prompt-cache savings, offsetting part—but not all—of that
   latency and token cost.

Anti-hallucination is deliberately layered across the full flow:

1. The Issue #8 system prompt requires every booking fact to be grounded in tool output.
2. The constrained booking tools are the only permitted source of room, availability, capacity,
   time, and booking facts.
3. The output verifier runs last against the current user message plus this turn's actual tool
   outputs. User text proves intent and can support corrections for the fixed 30-minute,
   positive-order, maximum-three-hour, and minimum-one-attendee collection constraints. Tool output
   still proves room capacity, availability, existence, and booking state. Every draft unsupported
   by the appropriate evidence is blocked.

No single layer is a complete guarantee; robustness comes from their combination. In particular,
the verifier is itself LLM-based, so the safe fallback prevents a rejected draft from escaping
without claiming perfect detection.

Issue #8, extended by Issue #18, provides `build_llm` and `build_system_prompt`. The prompt requires
availability, capacity, booking, and schedule claims to come from tool calls; it restricts the
assistant to rooms A–E and pins the required-field, user-owned room-choice, cancellation, and
output-format behaviors. The prompt builder receives the logged-in username and current
datetime from its caller already expressed with the fixed GMT-3 (`-03:00`) offset and supplies
today/tomorrow anchors in 24-hour format. It never reads or converts the clock itself. Tools accept
only ISO datetimes carrying `-03:00`; offset-less or foreign-offset values are rejected rather than
localized or translated. The accepted clock value is stored and displayed unchanged.

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

### Caching

The implemented and tested `SemanticCache` is a narrow, intentionally unwired pre-LLM optimization
seam for a possible future composition step. If wired, only an explicitly recognized static
question such as room capacity or the fixed room list could consult it before `handle_message`; a
hit would avoid the LLM call, while a miss would continue into the flow above. Availability,
schedules, bookings, free/occupied slots, and every unrecognized query would bypass the cache
entirely, so it could never sit in front of tool execution for state-dependent questions. The live
application does not import or instantiate `SemanticCache`, construct an embedding client, or add
a cache step to the turn path.

OpenAI prompt caching is engaged with the stable model-level key
`promtior-booking-agent-v1`, passed by `langchain-openai` as `prompt_cache_key`. OpenAI performs
the cache server-side automatically for eligible prompts (currently prompts of at least 1,024
tokens), and cache hits require an exact matching prefix. Accordingly, reusable grounding and
scope instructions appear first in the system prompt, while the changing datetime and username
appear at the end. The orchestrator binds tool definitions in a stable
create/cancel/availability/schedule/my-bookings order, so eligible repeated
system-prefix/tool-definition input can be reused; the username itself is closure state, not
changing schema content. Prompt caching lowers
the input cost of an eligible LLM call but still makes that call. If wired, the separate semantic
cache could avoid the call entirely, but only for repeated allowlisted static questions; it is not
a general prompt-response cache. The static dataset is just five rooms with fixed capacities, so
the real token savings here are modest. The seam demonstrates semantic caching and establishes a
safe pattern rather than addressing a major project cost driver. Prompt-cache usage remains
observable through the API response's cached-token metadata.

## User-facing messages

Requests that cannot run use three deliberately separate message categories:

1. **Rule violations** come from a typed domain error and are translated deterministically at the
   orchestrator's existing catch point. The message reflects the attempted safe fields, names the
   violated rule and valid value, and gives the next correction. Example: `The requested 3 hours
   30 minutes exceeds the 3-hour maximum. Choose a shorter time range.`
2. **Missing parameters** are handled by the conversation adapter and booking prompt before a
   write. All missing domain fields are requested together, while supplied values are acknowledged.
   Example: `I understood date 2026-07-21, time range 14:30 - 16:00, attendee count 5. To create
   the booking, please provide: room (so I know which room to reserve); meeting title (required and
   cannot be blank).`
3. **Unsupported or impossible requests** are explained by the booking agent without any partial
   tool execution; clear abuse, improper access, and off-domain requests still short-circuit at the
   guardrail with the same plain supported-action guidance. Example: `Recurring bookings aren't
   supported. I can help create a single future booking.`

Messages use domain language only: no booking IDs, exception names, stack traces, database terms,
or conflicting-owner identity. Permission denial and a missing cancellation target remain
indistinguishable. Booking-agent guidance proceeds through the normal verifier. User-supplied
values and fixed action/rule boundaries can ground corrective guidance, while room capacity,
availability, existence, and booking state still require matching tool output. The fixed guardrail
refusal remains the intentional pre-agent/pre-verifier security short-circuit and asserts no room
or booking-state fact.

## Output formats

Free times are always rendered as discrete 30-minute slots, one per line, using zero-padded
24-hour time and exactly one spaced hyphen:

```text
11:30 - 12:00
12:00 - 12:30
12:30 - 13:00
```

Contiguous slots are never merged: a free 11:30–13:00 block is the three lines above, not one
range. “to”, am/pm, en dashes, and alternative separators are not valid slot output.
Schedules preserve the requested range and represent both states in separate sections. Each slot
line retains the exact format above; occupied output contains no owner, title, or booking ID:

```text
Schedule for room C on 2026-07-21 (GMT-3):
Available:
09:00 - 09:30
10:00 - 10:30
Occupied:
09:30 - 10:00
```

If a section has no slots, it contains `None.` Contiguous slots are never merged and a misaligned
range is rejected rather than widened or truncated.

Each “my bookings” entry shows the required four booking details—title, `HH:MM - HH:MM` time
range, attendee count, and room—with its date on a separate line. The empty state is `You have no
bookings.` Creation confirmations show title, room, date, `HH:MM - HH:MM GMT-3`, and attendee count.
Cancellation choices show title, date, time, and room. Booking IDs are internal and never appear
in any confirmation, listing, cancellation candidate, or cancellation success response.

## Environment and configuration

Copy `.env.example` to `.env` for local development. `.env` is gitignored and must never be
committed.

| Variable | Required | Description |
| --- | --- | --- |
| `OPENAI_API_KEY` | Yes | OpenAI credential loaded with `python-dotenv`; never logged or hardcoded. |
| `OPENAI_MODEL` | No | Chat model name. Defaults to `gpt-4o-mini`, a cost-effective model with tool-calling support. |
| `BOOKINGS_DB_PATH` | No locally; yes for Railway persistence | SQLite file path. Defaults to the existing relative `bookings.db`; set it to `/data/bookings.db` when the Railway volume is mounted at `/data`. |
| `PORT` | Railway only; injected | Port used by the Railway start command. Railway supplies it automatically; do not add it manually. |

Application code reads the first three variables; `PORT` is consumed by the version-controlled
Railway start command. `SemanticCache` reads no environment variables and constructs no client;
if the seam is wired later, the composition layer would supply a small/low-cost OpenAI embedder
configured with the existing API key. The unwired seam adds no configuration. Room capacities and
the two challenge usernames/shared password are fixed in code. `.env.example` contains safe local
placeholders for the three user-supplied variables, and `.gitignore` excludes `.env`.

Run the single-page application from the repository root:

```bash
streamlit run app/ui/streamlit_app.py
```

## Deployment

Railway uses the repository-root `railway.toml` as config as code. It holds the exact Streamlit
start command so the service always binds Railway's injected port, listens on every interface,
and runs headless:

```bash
python -m streamlit run app/ui/streamlit_app.py --server.port $PORT --server.address 0.0.0.0 --server.headless true
```

This mechanism was chosen over a dashboard-only command or `Procfile` because Railway reads
`railway.toml` directly and the reviewed start command stays versioned with the application.
Railway's native Railpack builder detects Python from `.python-version`, installs the pinned
runtime dependencies from the root `requirements.txt`, and expands `$PORT` in the shell-run start
command. `python -m streamlit` keeps the repository root on Python's import path, so the app's
absolute `app.*` imports work without installing the project package. `.python-version` pins
Railway to Python 3.11, matching CI. A Dockerfile is unnecessary.

`pyproject.toml` remains the project's authoritative dependency declaration for local development
and CI. The root `requirements.txt` exists only because Railpack did not install dependencies from
that declaration in the observed build. It mirrors the runtime dependency names from
`pyproject.toml`, with versions pinned from the validated local environment; when a runtime
dependency changes in `pyproject.toml`, update its corresponding pin in `requirements.txt` in the
same change. Development-only packages remain in the `dev` extra and are not shipped to Railway.

> [!WARNING]
> A Railway volume is mandatory for booking persistence. Mount it at `/data` and set
> `BOOKINGS_DB_PATH=/data/bookings.db`. Without both settings, SQLite writes to the ephemeral
> container filesystem and the booking database is wiped on every service restart or redeploy.

### Prerequisites

- A Railway account and a fresh Railway project.
- This repository pushed to a GitHub repository Railway can access.
- An OpenAI API key with billing enabled. Add it only in Railway's Variables dashboard; never put
  it in Git, `railway.toml`, or any committed `.env` file.

### Deploy from a fresh Railway project

1. In Railway, choose **New Project**, select **Deploy from GitHub repo**, authorize access if
   prompted, and select this repository. Railpack detects Python from `.python-version` and
   installs the root `requirements.txt`.
2. Open the new service's **Variables** tab and add `OPENAI_API_KEY`. Optionally set
   `OPENAI_MODEL`; otherwise the app uses `gpt-4o-mini`. Do not set `PORT` because Railway injects
   it at runtime.
3. Add a volume to this same service and environment, set its mount path to `/data`, then add
   `BOOKINGS_DB_PATH=/data/bookings.db` in **Variables**. These two settings must agree.
4. Deploy or redeploy the service. `railway.toml` supplies the Streamlit start command; no build
   or start command needs to be copied into the dashboard.
5. In the service's **Settings**, generate a public domain under **Networking**, then open that
   URL after the deployment reports success.

### Verify persistence

1. Open the public URL and sign in as `User1` with password `TechnicalChallengePromtior`.
2. Create a uniquely titled future booking and list your bookings to confirm it exists.
3. Restart the Railway service.
4. Sign in again and list your bookings. The same booking must still exist; this restart check is
   what proves `/data` and `BOOKINGS_DB_PATH` are wired correctly.

This remains a public challenge/demo instance, not private production access control. The
credentials are fixed by the brief, so anyone who has the deployment URL and those credentials
can use the app. A normal safe turn makes three OpenAI calls—guardrail, booking agent, and output
verifier—and each call is billed to the configured API key; additional tool rounds can add calls.

## Development tooling

Project-scoped Claude Code automation lives in `.claude/settings.json`; its command hooks call the
offline, repository-relative `.claude/hooks/checks.py` runner:

- **After `Edit` or `Write`:** Python files under `app/` or `tests/` trigger
  `python -m ruff check .`. Other paths and non-Python files return immediately, keeping the edit
  loop fast. A failure starts with `LINT CHECK FAILED`, shows the command, and includes the Ruff
  code, file/line excerpt, and suggested correction. Ruff excludes `doc/`, whose executable
  notebook is documentation rather than application or test code.
- **Before Claude Code runs `git commit`:** the hook runs `python -m pytest --cov`. The options in
  `pyproject.toml` automatically enable branch coverage and the 100% gate. Failing tests are
  labelled `TEST CHECK FAILED`; a suite that passes but misses the threshold is labelled
  `COVERAGE CHECK FAILED`. Both outputs include a shortened pytest excerpt with the relevant
  failure and summary. Tests remain deterministic and mocked, so neither hook needs network or
  OpenAI access.

`git commit --no-verify ...` deliberately bypasses the pre-commit runner. This escape hatch is
for an explicit, reviewed exception only; bypassing is discouraged because it removes the local
test/coverage evidence. These are Claude Code project hooks, so a commit executed outside Claude
Code also does not trigger them; CI and review remain necessary backstops.

The repository-local `.claude/skills/add-agent-behavior` skill scaffolds the repeated workflow for
an agent-layer behavior change. It accepts a behavior name/description, determines (or asks for)
the integration point—system prompt, orchestrator, or deterministic presentation—and can accept a
concrete user message, expected reply, and tools that must not fire. Its bundled generator creates
one named, Ruff-clean test skeleton per scenario under `tests/agent/`, with mocked LLM/agent
objects, exact observable output, and `assert_not_called` checks. The skeleton intentionally fails
until its TODO invocation is wired through the existing agent API. The skill does **not** create
production files, implement behavior, call a model, or scaffold booking tools.

Issue #18 is the concrete use that validates this scope: the skill generated red-first skeletons
for slot collection, room selection, strict output, authenticated booking listings,
cancel-by-description, the BookingError regression, and user-message evidence for no-tool
clarifications. Those skeletons were then wired to mocked LLM/agent objects and deterministic
helpers before implementation; no test makes a live API call.

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
- **Datetimes stored as fixed-offset GMT-3 ISO strings** (`isoformat()` / `fromisoformat()`) in a
  simple, human-readable form. The tool and repository boundaries reject missing or foreign
  offsets; neither converts them. This keeps one aware representation (`-03:00`) end to end.

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
  caller; tools do no auth. Datetimes must carry `-03:00`; a missing or different offset produces
  an actionable input error instead of an implicit conversion.
- **Two failure channels in the tools, by intent.** Rule violations
  (`BookingError` subclasses) **propagate** — the tools do *not* catch them, so
  the orchestrator can translate them centrally through Issue #14's deterministic presenter.
  Malformed/unresolvable input (non-ISO datetime, unknown room) instead **returns a message
  string**, allowing the agent to retry with corrected arguments.
- **Cancel ownership + privacy.** `cancel_booking` deletes only if
  `booking.user == user`. A booking owned by someone else and an unknown booking produce the same
  generic response, which names neither the owner, booking details, nor the supplied ID. This
  prevents ownership/existence enumeration. Booking IDs are the first eight hex characters of a
  generated UUID, enforced as primary keys by SQLite, and retained only inside the tool/agent
  boundary; Issue #18 removes them from user-facing output.
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
  come from tools. The verifier compares the draft with the current user message and this turn's
  tool outputs, applying different authority to each: user text grounds requested values, while
  tool output alone grounds room and booking state. It does not replace prompt grounding or tool
  constraints.
- **The configured LLM and evidence are injected into `verify_response`.** The verifier builds no
  model and accesses neither the DB nor booking rules. The user message, injected current/tomorrow
  anchors, and tool outputs are serialized with the draft for one strict decision, producing a frozen
  `VerifierResult`.
- **No-tool clarifications may repeat user-supplied request details.** Greetings and ordinary
  clarification language remain grounded, and a clarification may echo the user's desired room,
  date/time, title, or attendee count. This prevents valid slot-filling questions from falling
  into the safe fallback. A user's assertion still cannot prove availability,
  capacity, room existence, or booking state; those claims require tool evidence.
- **Output verification costs one extra LLM call after each draft.** This adds latency and
  input-token cost on top of the guardrail and booking calls. Stable verifier prompts and the
  configured OpenAI prompt cache mitigate eligible repeated prefixes; Issue #11 invokes the
  verifier last and owns the fallback policy.

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

### Issue #11, commit 2 — Original verifier policy (superseded)

- **An ungrounded draft gets one evidence-only retry, then a safe fallback.** The first draft is
  checked against the current user message and this turn's captured tool outputs. If rejected, a
  tool-free model call rewrites it from the same evidence and the verifier checks that retry once. A second rejection returns
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
  distant queries return a miss. If wired later, the composition step would continue those misses
  into the normal LLM/tool flow. The embedding provider is injected rather than constructed by the
  cache, keeping provider configuration outside the module and tests deterministic without live
  API calls.
- **Cache entries live only in process memory.** They are not written to SQLite because cached
  responses would be disposable optimization artifacts, not application data. If wired, process
  restarts could discard them without affecting booking correctness, and persistence would add
  coupling with no benefit at this scale.
- **The expected savings are intentionally modest.** There are only five rooms and a small set of
  fixed facts. This unwired seam demonstrates the technique and establishes a safe default-bypass
  caching pattern; it is not presented as a live feature or major token-cost reduction. It
  complements prompt caching: prompt caching reduces repeated system-prompt/tool-definition input
  cost, whereas a semantic-cache hit would avoid the LLM call altogether if wired.

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
  cancel denial and absence return the same generic ID-free response. Issue #18 now suppresses
  booking IDs in successful confirmations, listings, and the wider cancellation conversation;
  Issue #14 itself still owns error paths only.
- **Failures state the valid expected value.** Slot messages name `:00`/`:30` boundaries,
  duration requires an end after the start and no more than three hours, capacity states the
  permitted minimum and that room's numeric capacity, title rejects blanks, and overlap explains
  that some or all of the range is already booked. Issue #18 now pre-validates conversationally,
  so errors that still reach this layer are edge cases where actionable guidance matters most.
  No alternative room or time is suggested because alternative generation is out of scope.
- **Translation uses the orchestrator's existing catch point and still passes verification.** A
  caught domain error becomes a normal draft answer and captured tool evidence, then proceeds to
  the verifier like any other response. This adds neither a second exception boundary nor a path
  around the guardrail → booking → verifier workflow.

### Issue #15 — Claude Code hooks and agent-behavior skill

- **Hooks make the CLAUDE.md gates automatic inside Claude Code rather than
  discipline-dependent.** Edit/write events lint Python changes immediately; attempted commits
  run the configured tests and coverage gate. Failures name lint, tests, or coverage and include
  actionable excerpts. The hooks reduce avoidable omissions but cannot tell whether a passing
  test is weak or asserts the wrong behavior, so human review and CI remain required.
- **One skill covers the agent-behavior workflow repeated since Issue #8.** Prompt instructions,
  orchestration policies, and deterministic presentation rules all follow the same TDD shape:
  choose the agent integration point, scaffold one mocked deterministic failing test per
  scenario, then stop before implementation. A booking-tool scaffolding skill was considered and
  rejected as dead weight because all required tools were completed in Issue #7 and none remain
  to add.
- **The skill scaffolds tests, not solutions.** Inputs identify the behavior, integration point,
  observable reply, and any tool that must remain uncalled. Output is an intentionally failing
  test skeleton with no live API path. Keeping production logic out of the generator preserves
  the red-first TDD boundary and prevents boilerplate from guessing behavior requirements.

### Issue #17 — Railway deployment

- **The SQLite path is resolved once at the orchestrator composition boundary.**
  `BOOKINGS_DB_PATH` overrides the file location while the relative `bookings.db` default keeps
  local behavior backward-compatible. No environment access enters the pure domain layer and no
  path parameter is threaded through unrelated layers.
- **Railway uses native Railpack plus config as code, not a Dockerfile.** `railway.toml` versions
  the Streamlit start command and `.python-version` selects Python 3.11 to match CI. A pinned root
  `requirements.txt` triggers dependency installation after the observed Railpack build skipped
  the authoritative `pyproject.toml` declaration; it contains runtime packages only. Starting
  Streamlit through `python -m` makes the repository root importable without installing the
  project package.
- **Persistent deployment requires an explicit volume contract.** The volume is mounted at
  `/data` and `BOOKINGS_DB_PATH` points to `/data/bookings.db`; either setting without the other
  leaves bookings on ephemeral storage. The default database, logs, and generated egg-info are
  ignored so runtime data and build artifacts cannot be committed accidentally.
- **Ruff excludes `doc/`.** CI still lints the application and tests through `ruff check .`, while
  the executable documentation notebook is outside that gate.

### Issue #18 — Conversation flow and output formats

- **Creation uses mandatory five-field slot filling with deliberate conversational
  pre-validation.** Room, date, start/end, non-blank meeting title, and attendee count must all be
  supplied; no value is invented or defaulted, and declining a title means the booking cannot be
  created. The agent-layer helper catches misaligned slots, invalid duration, and invalid attendee
  count early so the user can correct them before a write. Issue #4's domain rules remain the
  authoritative guarantee and still run inside the tool. This duplication is deliberate: the
  agent copy improves UX, while the domain copy protects correctness regardless of caller.
- **Room choice always belongs to the user.** When the time range and attendee count are known but
  the room is not, the agent lists every result from `list_available_rooms` and asks the user to
  choose. It does not select the first, smallest, or only result, and it does not invent
  alternatives when none match.
- **Booking IDs are internal-only.** Deterministic adapters remove IDs from create/cancel evidence
  before it reaches user-facing generation, and authenticated listings/candidates never contain
  them. Consequently, cancellation accepts date/time, title, and/or room, matches only the
  server-bound user's bookings, invokes the existing cancel tool with the unique ID internally,
  asks the user to disambiguate multiple ID-free candidates, and reports a clear no-match state.
- **Attendee persistence is the minimal approved prerequisite, kept separate from agent
  behavior.** The original model/schema omitted attendee count, making the required four-field
  listing impossible to ground. `Booking`, SQLite, repository mapping, and tool persistence now
  carry the explicitly supplied count; legacy databases receive an `attendees` column with `1`
  only as a compatibility value for old rows whose count was never stored. New conversations
  never use that migration value as a default. No domain rule, repository method, or existing
  booking-tool signature changed.
- **User messages are verifier evidence for intent, never for state.** Issue #18's required-field
  flow often asks a clarification before any tool runs. Passing only empty tool evidence caused a
  verifier to reject a valid question when it repeated the user's room, time, title, or attendee
  count, eventually producing the safe fallback. The orchestrator now supplies the current user
  message to verification. This fixes that false rejection without
  allowing user text to establish availability, capacity, room existence, or booking status.
- **All accepted timestamps use one aware GMT-3 representation.** The model must pass the user's
  wall time with `-03:00`; missing and foreign offsets are rejected. No layer translates an
  equivalent instant from another offset, so the accepted value is identical in the tool call,
  SQLite row, and user-facing output.
- **Standalone schedule and availability requests have explicit read-only routes.** They call
  `get_room_schedule` and `list_available_rooms` respectively and do not collect creation-only
  title/attendee fields. Formatted schedule evidence retains the queried room and local date so
  the verifier can ground the model's answer; stripping that context previously caused valid
  schedule responses to fall through to the safe fallback.
- **Creation confirmation times are copied verbatim from GMT-3 tool evidence.** All users operate
  in the application's fixed GMT-3 timezone, so the booking agent must not reinterpret the
  deterministic confirmation in another zone. The evidence now labels `GMT-3`; the system prompt
  forbids conversion and the verifier rejects any date/time mismatch. This layered prompt policy
  fixes final-answer drift without moving booking
  logic into the orchestrator.
- **Fixed collection-rule corrections are valid verifier evidence without a tool call.** The agent
  must catch 30-minute misalignment, end-before-start, ranges over three hours, and attendee counts
  below one while collecting fields—even when another field such as the date is still missing.
  Treating those server-defined constraints as verifier evidence prevents a correct correction
  such as “a meeting cannot be more than 3 hours” from becoming the safe fallback. Room capacity,
  availability, existence, and booking state remain tool-grounded; this exception does not widen
  user text into evidence for mutable state.

### Issue #20 — Time offset and core-function bugfixes

- **GMT-3 is the single system-wide time standard, with no conversions.** The chosen convention is
  offset-aware ISO datetimes fixed at `-03:00`: it makes the timezone explicit while preventing
  naive/aware mixing. The creation defect occurred because its model/tool boundary admitted a UTC
  representation and then stored and echoed that shifted wall clock, while cancellation simply
  formatted stored fields. The fix removes every compensating `astimezone`/localization helper and
  rejects missing or foreign offsets. A downstream add/subtract-hours display patch was rejected:
  it would hide corrupt input while leaving storage inconsistent. The UI remains the sole clock
  reader; all other layers receive time injected.
- **Schedule retrieval lost occupied slots in agent presentation.** The raw tool already produced
  both states, but the formatter selected only `free` lines. The formatter now partitions every
  exact 30-minute slot into `Available` and `Occupied`, preserves the requested endpoints, rejects
  misaligned ranges through the existing domain alignment rule, and never includes owner, title,
  or ID data.
- **Cancellation failed in description resolution before ownership was checked.** The bound
  adapter omitted the described end time and had no omitted-date confirmation path. It now matches
  room/date/start/end/title against only the server-bound user's bookings. A missing date uses the
  injected current date and asks for confirmation; an explicit unique match alone reaches the
  unchanged ID-based ownership tool. Ambiguous and absent matches remain non-mutating and ID-free,
  and raw not-found/non-owner responses remain identical.
- **Constraint failures remain one error path with precise presentation.** `DurationError` is now
  translated separately for end-before-start and maximum duration, with the latter stating “at
  most 3 hours.” Existing conversational pre-validation no longer shadows those cases with one
  combined generic sentence: it mirrors the specific correction and includes the requested
  duration. Alignment, capacity, missing-title, and overlap messages continue to state their valid
  expected value without exposing raw exception details.
- **Over-three-hour requests terminate instead of re-entering the agent loop.** The root cause was
  the orchestrator's unbounded model → tool `while True`: conversational pre-validation returned a
  correction as a tool result, allowing the model to repeat the same rejected call indefinitely.
  A deterministic create correction now ends that loop immediately and proceeds once through the
  verifier. The remaining loop is capped at eight model steps with the existing safe fallback as
  its terminal behavior; output verification itself is a single decision.
- **The simplification pass removes code that no longer earns its place.** Deleted timezone
  conversion/localization helpers and their compensating tests, plus the dead free-only schedule
  formatter superseded by the required free/occupied renderer. The repository SQL boundary,
  server-bound tool wrappers, verifier, and conversational/domain validation pair remain: they
  currently enforce persistence, identity security, grounding, and the deliberate UX-versus-
  guarantee split rather than speculative flexibility.

### Write-grounding verifier bugfix

- **The observed failure was a missing date anchor, not missing create evidence.** With current
  date `2026-07-20`, a live request for “tomorrow” created complete evidence for `2026-07-21`, but
  the verifier rejected it verbatim because “The date '2026-07-21' does not match the
  user-supplied request for 'tomorrow'.” The verifier received the full tool record and the exact
  requested `17:00 - 18:00 GMT-3` range; it lacked only the deterministic meaning of “tomorrow.”
  `current_date` and `tomorrow_date` are now supplied as explicit evidence, just as they are in the
  booking prompt. The verifier was not weakened or bypassed for writes: genuinely unsupported
  claims still return the generic fallback.
- **Write tools return the affected `Booking`, making confirmations verifiable by construction.**
  Successful create returns the persisted entity and successful cancel returns the deleted entity.
  The agent presentation layer renders title, room, date, start/end, and attendees from that return
  value; it no longer reconstructs successful write state from conversational arguments. Internal
  IDs remain available inside the agent/tool boundary but never appear in user-facing output.
  Cancellation description resolution and the server-bound ownership check are unchanged;
  permission-denied and not-found responses remain indistinguishable.
- **Verifier rejection details are server-only diagnostics.** Each rejected decision logs the
  verifier's reason and serialized tool evidence. The user still receives only
  `I couldn't produce a reliable answer. Please try again.`, so diagnostics improve without
  exposing prompts, internal IDs, or security details.
- **Deterministic rewrite/reverification was removed.** The former retry reused identical evidence;
  in the reproduced failure it generated the same rejection twice while adding a rewrite call and
  a second verifier call. The orchestrator now verifies once and promptly returns the safe fallback
  on rejection. This deletes `_RETRY_PROMPT`, `_retry_draft`, and the second verification branch.

### Issue #22 — User-facing errors and guidance

- **Non-executable requests use three categories in three existing layers.** Typed rule violations
  stay in the deterministic Issue #14 presenter; incomplete-but-valid requests stay in the
  conversation adapter and booking prompt; understood unsupported actions stay in booking-agent
  guidance, while clear abuse, improper access, and off-domain requests retain the guardrail
  short-circuit. They were deliberately not unified because they have different evidence and
  control flow: a raised domain rule, absent inputs before a tool call, or an action for which no
  tool exists. One generic mechanism would either lose that context or duplicate existing paths.
- **Correction messages reflect the request and state the valid value.** A user can now compare
  what they supplied with the 30-minute boundary, three-hour maximum, actual tool-grounded room
  capacity, non-blank-title requirement, or occupied-range rule and see the next action directly.
  Missing-field replies ask for all absent fields together, explain non-obvious needs such as
  attendee count for fit checking, and acknowledge values already understood. This minimizes
  corrective turns without inventing defaults or alternatives.
- **Guidance is grounded output, not an exception to grounding.** Rule translations are captured
  as tool evidence; user text can support echoed request values and missing-field clarification;
  fixed supported-action boundaries can support an unsupported-action explanation. Mutable room
  and booking facts still require tool output, so adding an unsupported capacity, availability,
  or booking claim remains a verifier rejection. The fixed guardrail refusal continues to return
  before the booking agent and verifier by design and contains no mutable-state assertion.

### Review A3 — Unexpected turn failures

- **Unexpected failures complete the turn safely.** `run_turn` logs the real exception server-side and appends a generic assistant reply, preserving alternating history without exposing technical details; `BookingError` keeps its existing deterministic presentation path.

### Review A4 — Semantic cache wiring

- **The designed-and-tested semantic-cache seam remains intentionally unwired.** The optimization is not needed at this scale, and wiring it would add an embeddings-client dependency for no measured gain.
