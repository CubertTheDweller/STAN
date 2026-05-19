#!/usr/bin/env python3
"""PostToolUse hook — run ruff check on any Python file that was just edited.

Reads the agent tool-use event from stdin (JSON), identifies whether a Python
file was written, and surfaces ruff errors as a systemMessage so the agent
fixes them immediately rather than at review time.

Exit codes:
  0  — success (always; errors are surfaced as non-blocking systemMessage)
"""

import json
import subprocess
import sys
from pathlib import Path

# Tools that produce file writes
_WRITE_TOOLS = {
    "replace_string_in_file",
    "multi_replace_string_in_file",
    "create_file",
    "str_replace_editor",
}


def main() -> None:
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    tool_name = event.get("tool_name", "")
    if tool_name not in _WRITE_TOOLS:
        sys.exit(0)

    # Extract file path — field name varies by tool
    tool_input = event.get("tool_input") or {}
    file_path = (
        tool_input.get("filePath")
        or tool_input.get("file_path")
        or tool_input.get("path")
        or ""
    )

    if not file_path or not file_path.endswith(".py"):
        sys.exit(0)

    if not Path(file_path).exists():
        sys.exit(0)

    # Run ruff against the specific file so feedback is fast and scoped
    result = subprocess.run(
        [".venv/bin/ruff", "check", file_path],
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parent.parent.parent,  # repo root
    )

    if result.returncode == 0:
        sys.exit(0)

    # Surface errors as a non-blocking system message
    message = f"ruff found issues in {file_path}:\n\n{result.stdout.strip()}"
    if result.stderr.strip():
        message += f"\n{result.stderr.strip()}"

    print(json.dumps({"systemMessage": message}))
    sys.exit(0)


if __name__ == "__main__":
    main()
