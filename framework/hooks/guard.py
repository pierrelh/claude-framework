#!/usr/bin/env python3
"""PreToolUse guard for Bash — the safety net that stays active in fully automatic mode.

Blocks a short list of irreversible or out-of-workflow commands. Exit code 2 blocks the
call and sends the reason back to Claude. Keep this list small and unambiguous: it is a
seatbelt, not a policy engine.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

RULES = [
    (r"\brm\s+(-[a-zA-Z]*[rR][a-zA-Z]*\s+)+(/|~|\$HOME|/\*|\.\.)(\s|/?$)",
     "recursive delete of /, ~ or a parent directory"),
    (r"\bgit\s+push\b[^|;&]*\s(--force|-f)(\s|$)",
     "force push — use --force-with-lease on your own feature branch only"),
    (r"\bgh\s+repo\s+(delete|archive)\b", "deleting or archiving a repository"),
    (r"\bgh\s+project\s+delete\b", "deleting the GitHub project"),
    (r"\bgit\s+filter-(branch|repo)\b", "rewriting history"),
    (r"\bmkfs(\.\w+)?\b|\bdd\s+[^|;&]*of=/dev/", "writing to a block device"),
    (r"\b(drop\s+database|drop\s+schema)\b", "dropping a database"),
    (r"\bchmod\s+-R\s+777\s+/", "world-writable permissions on /"),
]


def pushes_to_main(cmd):
    """Direct pushes to main/master bypass review. Allowed only with FW_ALLOW_MAIN_PUSH=1 (initial push)."""
    if "FW_ALLOW_MAIN_PUSH=1" in cmd:
        return False
    for part in re.split(r"&&|\|\||;", cmd):
        m = re.search(r"\bgit\s+push\b(.*)", part)
        if not m:
            continue
        positional = [a for a in m.group(1).split() if not a.startswith("-")]
        if any(re.search(r"(^|:)(main|master)$", a) for a in positional[1:]):
            return True
        if len(positional) < 2:  # no explicit refspec: pushes the current branch
            branch = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True,
                                    text=True, cwd=ROOT).stdout.strip()
            if branch in ("main", "master"):
                return True
    return False


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0
    cmd = (data.get("tool_input") or {}).get("command") or ""
    for pattern, reason in RULES:
        if re.search(pattern, cmd, re.I):
            print(f"Blocked by framework guard: {reason}. If this is really needed, ask the user to run it "
                  f"themselves.", file=sys.stderr)
            return 2
    try:
        initialized = json.loads((ROOT / ".fw" / "config.json").read_text()).get("initialized")
    except (OSError, ValueError):
        initialized = False
    if initialized and pushes_to_main(cmd):
        print("Blocked by framework guard: direct push to main/master. Work on a branch and open a pull request "
              "(see framework/standards/git-workflow.md).", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
