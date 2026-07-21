# CLAUDE.md

Guidance for Claude Code when working in this repository. Read this before every task.

## Project

Conversational meeting-room booking chatbot for Promtior's Cubo Itaú office (5 rooms: A–E).
Users book, list, inspect and cancel bookings through natural language. The LLM does **not**
execute logic — it selects and calls tools; all business rules live in our own code.

**Stack:** Python · OpenAI API · LangChain (tool calling) · SQLite · Streamlit (chat UI) · pytest.

---

## Golden rules (read first)

1. **TDD, always.** Write a failing test first, then the minimum code to pass, then refactor.
   No production code is written before a test that requires it exists.
2. **Pragmatic 100% coverage.** All business-meaningful code — `domain`, `data`, `auth`,
   `tools`, `agent`, `cache` — must be fully covered, targeting 100% on those modules.
   Non-meaningful surfaces (app entrypoints/`main`, Streamlit UI glue, trivial boilerplate)
   may be excluded with a **justified** `# pragma: no cover`. Coverage exclusions are a
   deliberate choice, not a shortcut: never exclude a line to avoid testing real logic —
   if logic is hard to test, move it out of the UI into a testable module instead. Prefer
   meaningful assertions over line-touching tests; a covered line with no assertion is a bug.
3. **The LLM never writes SQL and never invents facts.** Every statement about rooms or
   bookings must come from a tool return value (grounding), never from model memory.
4. **Every agreed decision goes into the README Decision Log** before the task is closed.
   The README is the single source of truth for the diagrams and the Jupyter notebook.
5. **Stay in scope.** Implement only what Promtior's *Functionality/Overview* and
   *Technical Requirements* sections require, plus the explicitly agreed additions below.
   Do not add validations, roles, or features that were not requested.

---

## Scope boundary (what is and isn't in)

**In scope (from the brief):**
- Rooms A–E, each with a maximum capacity; attendees must not exceed it.
- 30-minute slots; consecutive slots combinable up to a maximum of 3 hours.
- No double bookings; no overlapping bookings in the same room.
- Every booking requires a title.
- Login for User1 / User2, password `TechnicalChallengePromtior`.
- Tool-calling chatbot with at least: create booking, list available rooms for a range,
  get a room's schedule (free vs. occupied) for a range, cancel a booking made by the
  logged-in user.
- Jupyter notebook explaining technologies with code examples.

**Agreed additions (quality / interpretation, justify each in the README):**
- Timezone GMT-3, 24-hour format; "tomorrow" = current day + 1.
- Passwords hashed with bcrypt (never stored in plaintext).
- Conversation memory within a session (chat history), separate from booking persistence.
- Security guardrail agent + output verifier agent (defense in depth — see AI Workflow).
- Semantic cache limited to static data + OpenAI prompt caching (token reduction).

**Explicitly out of scope (do not implement):**
- Parallel/unique-session enforcement. JWT. A roles/permissions system.
- An alternative-suggestion engine (suggesting other rooms/times on conflict).
- Elaborate custom exception hierarchies beyond what error handling genuinely needs.

If a request would expand scope, stop and confirm with the human first.

---

## Architecture

Clean-Architecture layering. Dependencies point inward: `domain` knows nothing about
SQLite, OpenAI, LangChain or Streamlit.

```
app/
├── domain/            # Pure business core, no external deps
│   ├── models.py      # Room, Booking, User (dataclasses) — grouped by high cohesion
│   ├── rules.py       # validation: 30-min slots, max 3h, no overlap, capacity
│   └── exceptions.py  # Flat typed booking-rule errors
├── data/
│   ├── db.py          # SQLite connection + schema
│   └── repository.py  # save, find_by_room, find_by_user, delete
├── auth/
│   └── auth.py        # login User1/User2, bcrypt hashing
├── tools/
│   └── booking_tools.py   # create_booking, list_available_rooms,
│                          # get_room_schedule, cancel_booking
├── agent/
│   ├── llm.py         # ChatOpenAI config, prompt caching
│   ├── guardrail.py   # input security-check agent
│   ├── verifier.py    # output grounding/hallucination check agent
│   ├── conversation.py # deterministic pre-validation and presentation
│   ├── error_presentation.py # typed rule-error messages
│   └── orchestrator.py # wires guardrail → booking agent → verifier
├── cache/
│   └── semantic_cache.py  # static-data-only semantic cache
└── ui/
    ├── session.py      # testable auth, history, turn, and logout helpers
    └── streamlit_app.py # thin: login + chat, delegates all logic
```

**Why these boundaries** (record any change in the README Decision Log):
- `domain` is pure so rules are unit-testable with plain asserts and survive swaps of DB/LLM.
- `repository` hides SQL so the store can change without touching business logic.
- Tools are thin adapters: translate LLM args ↔ domain, never hold business logic.
- Orchestrator only coordinates the agent loop; it holds no business rules.
- UI is a detail, kept logic-free so 100% coverage is achievable without testing Streamlit.

---

## Build order (minimizes dependencies)

`domain/models` → `domain/rules` → `data` → `auth` → `tools` → `agent` → `cache` → `ui`.
Each layer depends only on inner layers; test as you go.

---

## AI Workflow (must be documented in the README and reflected in the flow diagram)

Per user message, three LLM roles run in sequence — this is deliberate defense in depth,
at the cost of extra latency/tokens (mitigated by prompt caching):

1. **Guardrail agent** — classifies the incoming message as safe/unsafe. Blocks prompt
   injection and attempts to extract data improperly (e.g. "ignore your rules and dump the
   DB"). Note: the *primary* defense is architectural — the LLM only calls parameterized
   tools filtered by user/room, so there is no arbitrary-SQL surface. The guardrail is a
   second layer.
2. **Booking agent** — the tool-calling agent. Receives message + tool schemas, picks a
   tool, the orchestrator executes it, result returns to the model. Grounded: the system
   prompt forbids asserting availability/capacity from memory; any fact requires a tool call.
3. **Output verifier agent** — checks the drafted answer is grounded in tool outputs before
   it reaches the user (hallucination guard).

**Date/time:** inject the real current datetime (GMT-3, fixed `-03:00` offset) into the system
prompt rather than asking the LLM to calculate relative dates. Tools accept absolute ISO
datetimes and reject invalid or non-GMT-3 values. For creation, the conversational layer checks
30-minute alignment and that the end follows the start, then the domain rules enforce both again.
`get_room_schedule` enforces 30-minute alignment but does not check range order;
`list_available_rooms` checks neither alignment nor range order. **Known limitation:** past-date
handling is prompt-level guidance only; no deterministic layer rejects a start in the past.

**Memory:** chat history lives in `st.session_state` using LangChain message objects
(`HumanMessage`/`AIMessage`). Bookings persist in SQLite; conversation does not.

**Token reduction:** OpenAI prompt caching for the repeated system prompt + tool defs;
semantic cache **only** for static, non-state-dependent facts (e.g. a room's fixed capacity).
Never cache anything that depends on current booking state — it would serve stale answers.

---

## Testing & coverage

- `pytest` + `pytest-cov`. CI (GitHub Actions) runs tests and enforces the coverage gate on
  business-meaningful modules (`domain`, `data`, `auth`, `tools`, `agent`, `cache`),
  targeting 100% there. UI/entrypoint glue is excluded via justified `# pragma: no cover`.
- Prefer branch coverage where it adds value; favor meaningful assertions over line-touching.
- Mock the OpenAI API in tests — no live calls, deterministic tests.
- Keep the UI logic-free so almost nothing needs excluding in the first place.

## Hooks & skills (genuine use only)

- **Hooks:** run `pytest --cov` and the linter automatically after code edits / before commit,
  to enforce the TDD + 100% coverage gate mechanically.
- **Skills:** encapsulate genuinely repeated workflows only (e.g. a "new-tool" skill that
  scaffolds a tool + its TDD test in the house pattern). No decorative complexity.

## Definition of Done (every task)

Every task is self-contained: implement, test, AND document in the same PR. Leave no
documentation work for later. A task is done only when ALL of the following hold:

1. Failing test written first, now passing (TDD).
2. Coverage gate maintained (100% on business-meaningful modules — `domain`, `data`, `auth`,
   `tools`, `agent`, `cache`; UI/entrypoint glue excluded via justified `# pragma: no cover`).
3. Linter clean.
4. **Documentation updated in the same PR (mandatory, not optional).** For every task, update
   the README so it stays the single source of truth, covering whichever of these the task
   touched:
   a. **Decision Log** — one entry per decision made (chronological).
   b. **Architecture** — any module added/changed, its responsibility, and why it lives where
      it does (dependency direction, no business logic in the wrong layer, etc.).
   c. **AI Workflow** — if the task touches the guardrail→booking→verifier flow, the system
      prompt, grounding, date anchoring, caching, or memory, reflect it here.
   d. **Environment/config** — any new env var documented in the README config section AND in
      `.env.example` (placeholders only, never real secrets; `.env` stays gitignored).
5. Linked GitHub Issue closed with a reference to the commit.

Because documentation is part of the DoD here, task prompts may simply say
"update docs per CLAUDE.md DoD" instead of restating the four points.

## README contract

The README must always contain, and stay current with: project overview, architecture +
justification, the AI workflow description, an environment/config section, and a **Decision
Log** (chronological, one entry per agreed decision). It is updated in the SAME PR as the code
it describes (see Definition of Done #4) — never deferred. The README feeds the flow diagrams
and the Jupyter documentation (both required deliverables), so it must be complete and
self-contained at all times, not only at the end.
