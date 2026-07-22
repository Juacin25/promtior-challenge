---
name: add-agent-behavior
description: Scaffold the failing deterministic test for a new or changed behavior in the existing agent layer. Use for system-prompt instructions, orchestrator control-flow/tool-suppression behavior, or deterministic presentation rules under app/agent; do not use for booking-tool scaffolding or implementation generation.
---

# Add Agent Behavior

Create only the TDD starting point for one agent behavior. Stop before production code.

## Workflow

1. Read `CLAUDE.md` and the existing agent module/tests involved.
2. Determine the integration point:
   - `prompt`: instruction or grounding policy in `app/agent/llm.py`.
   - `orchestrator`: turn ordering, short-circuiting, retries, or whether a tool may run.
   - `presentation`: deterministic wording in `app/agent/error_presentation.py`.
   Ask one concise question only when the description does not make the choice clear.
3. Split the request into observable scenarios. Generate one named test per scenario; never fold
   several scenarios into one test.
4. Run `scripts/scaffold_test.py` for each scenario. Provide `--forbid-tool` when the behavior
   requires a tool not to run.
5. Replace only the generated TODO invocation with the existing public agent entry point and
   injected mocks. Keep every LLM/agent dependency mocked and make output assertions exact and
   deterministic.
6. Run the generated test and confirm it fails for the missing behavior.
7. Report the selected integration target and failing test path. Do not implement the behavior.

## Generator

```bash
python .claude/skills/add-agent-behavior/scripts/scaffold_test.py \
  --name missing-title \
  --description "create_booking must not be called when the meeting title is missing" \
  --hook orchestrator \
  --forbid-tool create_booking \
  --user-message "Book room A tomorrow at 10:00." \
  --expected-reply "Please provide a meeting title."
```

The generator writes `tests/agent/test_<name>.py` unless `--output` is supplied. It refuses to
overwrite files. The result contains mocked LLM and booking-agent objects, deterministic expected
output, an `assert_not_called` check for each forbidden tool, and an intentionally failing
placeholder invocation.

Do not create agent implementation files, change production code, call a live model, generate a
tool scaffold, or turn the failing skeleton into a passing stub.
