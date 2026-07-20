"""Offline Claude Code hooks for the repository quality gates."""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

PROJECT_DIR = Path(os.environ.get("CLAUDE_PROJECT_DIR", ".")).resolve()


def _event() -> dict:
    try:
        return json.load(sys.stdin)
    except (json.JSONDecodeError, OSError):
        return {}


def _excerpt(output: str, limit: int = 60) -> str:
    lines = output.strip().splitlines()
    if len(lines) <= limit:
        return "\n".join(lines)
    half = limit // 2
    return "\n".join([*lines[:half], "... output shortened ...", *lines[-half:]])


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=PROJECT_DIR,
        capture_output=True,
        text=True,
        check=False,
    )


def _fail(label: str, command: str, output: str) -> int:
    print(
        f"{label}\nCommand: {command}\n\n{_excerpt(output)}",
        file=sys.stderr,
    )
    return 2


def _edited_python_path(event: dict) -> bool:
    file_path = event.get("tool_input", {}).get("file_path")
    if not file_path or Path(file_path).suffix != ".py":
        return False
    path = Path(file_path)
    absolute = path.resolve() if path.is_absolute() else (PROJECT_DIR / path).resolve()
    try:
        relative = absolute.relative_to(PROJECT_DIR)
    except ValueError:
        return False
    return bool(relative.parts) and relative.parts[0] in {"app", "tests"}


def lint(event: dict) -> int:
    if not _edited_python_path(event):
        return 0
    result = _run([sys.executable, "-m", "ruff", "check", "."])
    if result.returncode:
        return _fail(
            "LINT CHECK FAILED: fix the Ruff violations shown below.",
            "python -m ruff check .",
            result.stdout + result.stderr,
        )
    return 0


def pre_commit(event: dict) -> int:
    command = event.get("tool_input", {}).get("command", "")
    if not re.search(r"(?:^|[;&|]\s*)git\s+commit(?:\s|$)", command):
        return 0
    if "--no-verify" in command:
        return 0

    result = _run([sys.executable, "-m", "pytest", "--cov"])
    if not result.returncode:
        return 0

    output = result.stdout + result.stderr
    if "ERROR: Coverage failure" in output or "FAIL Required test coverage" in output:
        label = "COVERAGE CHECK FAILED: restore the configured 100% coverage gate."
    elif "= FAILURES =" in output or "= ERRORS =" in output or " failed" in output:
        label = "TEST CHECK FAILED: fix the failing tests shown below."
    else:
        label = "TEST/COVERAGE CHECK FAILED: inspect the pytest output below."
    return _fail(label, "python -m pytest --cov", output)


def main() -> int:
    event = _event()
    if len(sys.argv) != 2:
        print("Usage: checks.py lint|pre-commit", file=sys.stderr)
        return 2
    if sys.argv[1] == "lint":
        return lint(event)
    if sys.argv[1] == "pre-commit":
        return pre_commit(event)
    print(f"Unknown check: {sys.argv[1]}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
