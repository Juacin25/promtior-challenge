"""Generate one intentionally failing agent-behavior test skeleton."""

import argparse
import re
from pathlib import Path

TARGETS = {
    "prompt": "app/agent/llm.py system-prompt instruction",
    "orchestrator": "app/agent/orchestrator.py control flow",
    "presentation": "app/agent/error_presentation.py presentation rule",
}


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    if not slug:
        raise ValueError("Behavior name must contain a letter or number.")
    return f"behavior_{slug}" if slug[0].isdigit() else slug


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Scaffold a failing deterministic agent-behavior test."
    )
    parser.add_argument("--name", required=True)
    parser.add_argument("--description", required=True)
    parser.add_argument("--hook", required=True, choices=TARGETS)
    parser.add_argument("--forbid-tool", action="append", default=[])
    parser.add_argument("--user-message")
    parser.add_argument(
        "--expected-reply", default="TODO: replace with the exact expected reply"
    )
    parser.add_argument("--output", type=Path)
    return parser


def main() -> int:
    args = _parser().parse_args()
    name = _slug(args.name)
    output = args.output or Path("tests/agent") / f"test_{name}.py"
    if output.exists():
        raise SystemExit(f"Refusing to overwrite existing file: {output}")

    tool_names = [_slug(tool) for tool in args.forbid_tool]
    forbidden_tools = [f'    {tool} = Mock(name="{tool}")' for tool in tool_names]
    not_called = [f"    {tool}.assert_not_called()" for tool in tool_names]
    body = "\n".join(
        [
            "from unittest.mock import Mock",
            "",
            "",
            f"def test_{name}():",
            '    _llm = Mock(name="llm")',
            '    _booking_agent = Mock(name="booking_agent")',
            *forbidden_tools,
            f"    _user_message = {(args.user_message or args.description)!r}",
            f"    expected_reply = {args.expected_reply!r}",
            "",
            f"    # Integration target: {TARGETS[args.hook]}",
            "    # TODO: patch dependencies and invoke the existing public agent entry point.",
            "    actual_reply = None",
            "",
            *not_called,
            "    assert actual_reply == expected_reply",
            "",
        ]
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(body, encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
