# Project overview — meeting-room booking chatbot

This document explains, for a reader who has never seen the repository, what was built, how a
message travels through the system, and why the system is built the way it is. The component
diagram in this folder ([component-diagram.svg](component-diagram.svg), editable source
[component-diagram.drawio](component-diagram.drawio)) shows the same flow graphically. The
[README](../README.md) at the repository root is the developer-facing source of truth; where this
document summarizes, the README carries the full decision log and the per-module detail.

## The problem

Promtior's Cubo Itaú office has five meeting rooms, A to E, with fixed capacities of 2, 2, 4, 8
and 10 people. Two known users, User1 and User2, must be able to book a room, see which rooms are
free for a time range, inspect a room's schedule slot by slot, and cancel their own bookings, and
they must do all of it in natural language through a chat rather than a form. A booking occupies
one room for a range of 30-minute slots, may combine consecutive slots up to a maximum of three
hours, must carry a non-blank meeting title, must not exceed the room's capacity, and must not
overlap another booking in the same room; two bookings that touch at an endpoint are both valid.
The timezone is GMT-3 for everything. Bookings must survive logout: if a user signs out and
returns, every booking they made still exists, and only its owner can cancel it.

The difficult part is not the booking rules, it is trust. A language model relays the requests,
and a language model can invent facts, mishandle dates, or be talked into ignoring its
instructions. The system is therefore built so that the model never executes business logic and
never asserts a fact it did not receive from a tool: it only selects which constrained operation
to call, and every rule lives in ordinary code that runs the same way regardless of what the
model does.

## How a turn flows

The numbered arrows in the component diagram trace one turn; this is the same path in prose.

A user signs in with credentials checked against bcrypt hashes, and the authenticated username is
stored server-side in the session. From that point nothing typed into the chat can change who the
user is, because every operation that needs an identity receives the session's username, never a
value taken from the conversation. When the user sends a message, the UI reads the clock once, in
fixed GMT-3, and hands the message, the prior conversation history, the username and the current
datetime to the orchestrator. The UI is the only component that reads the clock; every other
layer receives time as data, so the model never computes a date itself.

The orchestrator runs three model roles in sequence. A guardrail classifier first decides whether
the message is ordinary booking language or clear abuse; abuse ends the turn immediately with a
fixed refusal, before any database connection is opened or any tool exists. For a safe message,
the booking agent receives a system prompt carrying the grounding rules and the injected
today/tomorrow anchors, the conversation history, and five tool schemas, and it loops
model → tool → model until it has an answer, with a hard cap of eight model steps. Create,
cancel, schedule and my-bookings calls pass through deterministic conversation adapters that
pre-validate input, resolve descriptions against only the user's own bookings, insert the
server-bound username, and format every result without internal identifiers; the availability
query is the one tool exposed raw; its output is a plain list of free rooms and contains no
identifier or owner data to strip. The
tools delegate every rule to the pure domain layer and every read or write to a parameterized
SQLite repository. Last, a verifier checks the drafted answer against the evidence of the turn —
the captured tool outputs, the user's own message, and the injected date anchors — and only a
grounded draft reaches the user. A rejected draft is replaced by one fixed fallback sentence
while the rejection reason is logged server-side.

Three paths stop a turn early, and all three are deliberate: the guardrail refusal, a domain rule
violation translated into a fixed corrective message, and a verifier rejection. A blocked turn
costs one model call; a safe turn costs three at minimum, plus one per additional tool round.

## Architecture and why each boundary exists

The code is layered so that dependencies point inward: UI → agent → tools → domain and data. The
domain layer holds the booking rules and typed rule violations and imports nothing but the
standard library, so the rules can be tested with plain assertions and survive a change of
database or model provider without being touched. The data layer is the only place SQL exists;
every query is parameterized, and the repository refuses any datetime that does not carry the
GMT-3 offset, on write and on read, so a single time representation holds end to end. The tools
are thin adapters: they parse the model's arguments, call the domain rules, call the repository,
and return either the affected booking or a plain message, holding no rules of their own. The
agent layer contains everything that involves a model — prompt construction, the guardrail, the
tool-calling loop, the verifier — plus the deterministic presentation helpers, and the
orchestrator that wires them owns no business rule itself. The UI is kept free of logic: its
session behavior lives in a separately tested helper, and the Streamlit file only renders login,
chat and logout.

The point of these boundaries is blast containment. A wrong or malicious model output can only
become one of five constrained tool calls; a schema change stays inside the data layer; a rule
change stays inside the domain; and the model-facing code can be rewritten without touching what
makes bookings correct.

## The three-agent workflow

Each user message passes through three model roles, and each exists for a different failure mode.

The **guardrail** exists for hostile input. It classifies the incoming message as safe or unsafe
and blocks prompt injection, database-dump requests and off-domain use with one neutral refusal
that reveals nothing about the system. It is deliberately a second line of defense: the primary
defense is architectural, because the model can only call parameterized tools that filter by the
authenticated user, so there is no arbitrary-SQL surface for a successful injection to reach.
The classifier defaults to safe for ordinary booking language, however unusual, so that the
booking agent — not the guardrail — explains unsupported requests.

The **booking agent** exists to translate language into tool calls. Its prompt requires every
room or booking fact to come from a tool result, forbids inventing or defaulting any of the five
required booking fields (room, date, time range, title, attendee count), and pins the output
formats: discrete 30-minute slots, one per line, dates and times copied verbatim from tool
evidence, never a booking ID. When fields are missing it must ask for all of them at once,
acknowledging what it already understood.

The **verifier** exists for hallucination. After the draft answer is produced, it checks the
draft against the turn's tool outputs, the user's own message, and the injected date anchors,
with different authority for each: user text can support a clarification that repeats requested
details, but availability, capacity, room existence and booking state require tool output. An
ungrounded draft never reaches the user; the turn returns the fixed fallback instead. The
verifier is itself a model, so the fallback — not the verifier's judgment — is what guarantees a
rejected draft cannot escape.

## Technologies and why

- **Python 3.11+** — the challenge's stack; the whole system is one language, tests included.
- **OpenAI API, `gpt-4o-mini` by default** — a low-cost model with reliable tool calling, at
  temperature 0 so tool selection is as repeatable as the API permits; the model is configurable
  through an environment variable without a code change.
- **LangChain (`langchain-openai`, `langchain-core`)** — provides tool schemas, tool binding and
  typed chat messages. The agent loop itself is a small explicit function in the orchestrator,
  because the installed API exposes tool binding directly and a prebuilt agent abstraction would
  add a layer without adding control.
- **SQLite** — durable, zero-infrastructure persistence through the standard library. Bookings
  must outlive sessions; a single database file does that without a server.
- **Streamlit** — a stateful single-page chat UI. Conversation history lives in its session
  state as LangChain messages; there is no route or URL that can bypass the login gate because
  there is no second page to route to.
- **bcrypt** — the fixed challenge password is stored only as a hash, derived at load; plaintext
  is never persisted or logged.
- **pytest + coverage + ruff, enforced in CI** — the test suite mocks the model, runs
  deterministically without network access, and CI fails below 100% line and branch coverage on
  every business module; only the render-only Streamlit file is excluded.

## Design decisions that look odd on purpose

**Validation exists twice, deliberately.** The conversation adapter re-checks what the domain
rules will check again inside the tool: slot alignment, duration, attendee count, capacity. The
agent-side copy exists for the user — it aggregates every missing field into one request,
acknowledges the values already understood, and phrases corrections with the requested values in
them — while the domain copy exists for correctness and runs no matter who calls the tool.
Deleting either copy would trade away one of those properties, so the duplication is kept and
the domain remains the authority.

**Deterministic output still passes the verifier.** Corrections and confirmations produced by our
own code cannot hallucinate, and verifying them costs a model call anyway. The alternative — a
bypass channel around verification for "trusted" text — was rejected because one uniform exit
policy is simpler to reason about and leaves no path that skips the check. Every answer leaves
through the same gate.

**GMT-3 is the single time standard, with no conversions anywhere.** Datetimes are fixed-offset
`-03:00` ISO values in the tool call, in the database row and in the answer; a missing or foreign
offset is rejected at the tool and repository boundaries rather than converted. The model is
never allowed to compute dates: the current datetime and the meaning of "today" and "tomorrow"
are injected into the prompt each turn, and the verifier treats those anchors as the only valid
calendar. Rejecting instead of converting removes the class of bugs where a shifted wall clock is
stored and then echoed back as if the user had chosen it.

**Booking IDs never reach the user.** IDs exist for the database and the tools, but every
confirmation, listing and cancellation dialogue identifies a booking by title, date, time and
room. Cancellation is resolved by description against only the requesting user's bookings; if
several match, the user chooses among ID-free candidates, and if the date was omitted, the match
against today is shown and confirmed before anything is deleted. Users never need to hold a
technical token to operate on their own bookings.

**Identity is server-bound and failure is uninformative.** The username travels from the login
session into closures around the tools; no model-visible schema has a `user` or `booking_id`
argument, so the model cannot act as someone else even if instructed to. Cancelling a booking
that does not exist and cancelling a booking that belongs to the other user produce the same
generic reply, login failure does not say whether the username or the password was wrong, and an
occupied-room message never names who holds the conflicting booking. What a user cannot do, they
also cannot enumerate.

## Honest limitations

- The semantic cache in `app/cache` is implemented and tested but not wired into the turn path:
  no embedding client is constructed and nothing consults it before the model runs. It is a
  demonstrated seam for caching static room facts, not an active optimization.
- The test suite mocks the model. It verifies wiring, rules, persistence, privacy properties and
  prompt content deterministically, and it cannot verify how the real model behaves; prompt-level
  behavior such as refusing past dates rests on the prompt and the verifier, not on tests.
- Past-date handling is prompt-level guidance only. No deterministic layer rejects a start in the
  past; the prompt instructs the agent to refuse, and that instruction is the enforcement.
- Sessions are ephemeral by design: a server restart or page reload returns to login, and there
  is no session expiry or remote invalidation. This fails safe for a challenge deployment and is
  not a production session system.
- The double-booking check is application-level: the tool checks for overlap and then inserts,
  without a transaction serializing the two steps, so two exactly simultaneous writes could in
  principle both pass the check. With two users and one process this window is theoretical, but
  it is not closed.
- Conversation history within a session is unbounded, so a very long session grows prompt size
  and latency; bookings are unaffected because they live in SQLite, not in the conversation.
