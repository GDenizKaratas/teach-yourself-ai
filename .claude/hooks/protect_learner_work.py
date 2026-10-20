"""PreToolUse hook: the learner writes their own code.

Blocks Claude from editing:
  - tracks/*/tasks/*/solution* once it exists (Claude may create the starter once)
  - anything under workspace/ or projects/ (the learner's own space)

Fails CLOSED for those paths: if the input can't be read or checked but its raw text
mentions workspace/, projects/ or a solution file, the edit is denied. Everything else
is allowed, even when this script itself breaks.
"""
import json
import os
import re
import sys
from pathlib import Path

ADVICE = (" The learner writes this code themselves. Use the hint ladder from the task skill instead;"
          " show analogous examples in chat, never their solution.")
RAW_PROTECTED = re.compile(r"(?:workspace|projects)[\\/]|solution", re.IGNORECASE)


def deny(reason):
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": reason + ADVICE,
    }}))


def check(data):
    """Return a deny reason, or None to allow."""
    tool_input = data.get("tool_input") or {}
    raw = tool_input.get("file_path") or tool_input.get("notebook_path")
    if not raw:
        return None
    root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd") or ".").resolve()
    path = Path(raw)
    path = (path if path.is_absolute() else root / path).resolve()
    try:
        rel = path.relative_to(root).parts
    except ValueError:
        return None
    if rel and rel[0] in ("workspace", "projects"):
        return f"{'/'.join(rel)} is in the learner's own space."
    if len(rel) >= 5 and rel[0] == "tracks" and rel[2] == "tasks" and rel[-1].startswith("solution") and path.exists():
        return f"{'/'.join(rel)} is the learner's solution file (the starter already exists)."
    return None


def main():
    text = ""
    try:
        text = sys.stdin.buffer.read().decode("utf-8", errors="replace")
        reason = check(json.loads(text))
    except Exception:
        # Couldn't check this edit: block it only if it might touch the learner's work.
        if RAW_PROTECTED.search(text):
            deny("This edit could not be checked and it mentions the learner's work (workspace/, projects/ or a solution file).")
        return
    if reason:
        deny(reason)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
