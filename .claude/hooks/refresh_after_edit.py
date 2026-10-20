"""PostToolUse hook (Edit|Write|MultiEdit): keep the generated views current.

When the edited file is under tracks/ or learner/ (but is not one of the generated files themselves),
run `tools/learn refresh --quiet`: learner/export.json → learner/dashboard.html → each lesson's mini map.

Fail-safe: never blocks, never prints, always exits 0; the refresh gets a short timeout.
Turned off by TEACH_NO_DASHBOARD=1 (same switch as the engine's own auto-refresh).
"""
import json
import os
import subprocess
import sys
from pathlib import Path

GENERATED = {("learner", "export.json"), ("learner", "dashboard.html")}
TIMEOUT_S = 20


def should_refresh(data: dict, root: Path) -> bool:
    raw = (data.get("tool_input") or {}).get("file_path")
    if not raw:
        return False
    path = Path(raw)
    path = (path if path.is_absolute() else root / path).resolve()
    try:
        parts = path.relative_to(root.resolve()).parts
    except ValueError:
        return False
    if not parts or parts[0] not in ("tracks", "learner"):
        return False
    return tuple(parts[:2]) not in GENERATED


def main() -> int:
    try:
        if os.environ.get("TEACH_NO_DASHBOARD") == "1":
            return 0
        data = json.loads(sys.stdin.read() or "{}")
        root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd") or ".")
        if not should_refresh(data, root):
            return 0
        engine = Path(__file__).resolve().parents[2] / "tools" / "learn.py"
        subprocess.run([sys.executable, str(engine), "refresh", "--quiet"], cwd=root,
                       env=dict(os.environ, TEACH_ROOT=str(root.resolve())),
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=TIMEOUT_S)
    except Exception:  # noqa: BLE001 — a view refresh must never disturb the session
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
