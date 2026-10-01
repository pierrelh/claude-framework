#!/usr/bin/env python3
"""Stop / SubagentStop hook: don't let an agent finish with failing checks.

Opt-in: `fw config set gates.check_on_stop true`. When the working tree has changes (or the
branch is not main/master), runs `fw check` — the project's lint / typecheck / test / build
commands from .fw/config.json → commands. On failure, exit code 2 sends the failing output
back to the agent, which keeps working; a second stop in a row (`stop_hook_active`) is always
allowed, so the agent can still finish with `STATUS: BLOCKED` instead of looping.

A green result is cached per tree state in .fw/local/check-gate.json, so stopping again
without changes costs nothing. A timeout (`gates.check_timeout`, default 900 s) or a project
without commands never blocks.
"""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / ".fw" / "local" / "check-gate.json"


def git(*args):
    p = subprocess.run(["git", *args], cwd=ROOT, capture_output=True)
    return p.stdout if p.returncode == 0 else b""


def tree_key():
    """Identifies HEAD + uncommitted changes + untracked files (names and contents)."""
    h = hashlib.sha256(git("rev-parse", "HEAD") + git("diff", "HEAD", "--binary"))
    for name in sorted(git("ls-files", "--others", "--exclude-standard", "-z").split(b"\0")):
        path = ROOT / name.decode(errors="replace")
        if name and path.is_file():
            h.update(name + path.read_bytes())
    return h.hexdigest()


def main():
    try:
        data = json.load(sys.stdin)
    except ValueError:
        data = {}
    try:
        cfg = json.loads((ROOT / ".fw" / "config.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0
    gates = cfg.get("gates") or {}
    if not gates.get("check_on_stop") or data.get("stop_hook_active") or not (cfg.get("commands") or {}):
        return 0
    branch = git("rev-parse", "--abbrev-ref", "HEAD").decode().strip()
    dirty = bool(git("status", "--porcelain").strip())
    if not dirty and branch in ("main", "master"):
        return 0
    key = tree_key()
    try:
        if json.loads(CACHE.read_text()).get("ok_key") == key:
            return 0
    except (OSError, ValueError):
        pass

    try:
        p = subprocess.run([sys.executable, str(ROOT / "framework" / "bin" / "fw.py"), "check", "--json"],
                           cwd=ROOT, capture_output=True, text=True, timeout=float(gates.get("check_timeout", 900)))
    except subprocess.TimeoutExpired:
        print("[fw check-gate] fw check timed out — not blocking; run it yourself before finishing.")
        return 0
    if p.returncode == 2:  # not configured
        return 0
    try:
        result = json.loads(p.stdout)
    except ValueError:
        return 0
    if result.get("ok"):
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps({"ok_key": key}))
        return 0
    failed = [s for s in result.get("steps", []) if s.get("exit")]
    lines = [f"Quality gate failed — `framework/bin/fw check`: "
             + ", ".join(f"{s['name']} (exit {s['exit']})" for s in failed) + ".",
             "Fix it before finishing. If it cannot be fixed within this story, stop and report "
             "`STATUS: BLOCKED` with the failing output (never weaken or skip the tests)."]
    for s in failed:
        lines += ["", f"--- {s['name']}: {s['command']} (last lines)", s.get("output_tail", "")]
    print("\n".join(lines), file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
